import hashlib
import json
import logging
import uuid
from datetime import timedelta
from dataclasses import asdict, dataclass
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Prefetch, Q, Sum, When
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from catalog.models import Product, ProductImage, ProductStatus

from .images import build_product_primary_image_snapshot
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    CheckoutAttempt,
    Order,
    OrderBuyerType,
    OrderCheckoutSource,
    OrderItem,
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderStatus,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationItem,
    StockReservationStatus,
    WishlistItem,
)
from .payment_providers import get_provider_method_for_action
from .meta_conversions import send_meta_purchase_event

logger = logging.getLogger(__name__)

CART_TOKEN_COOKIE_NAME = "cart_token"
WISHLIST_TOKEN_COOKIE_NAME = "wishlist_token"
BUY_NOW_TOKEN_COOKIE_NAME = "buy_now_token"
CART_AVAILABILITY_CHANGED_CODE = "cart_availability_changed"
BUY_NOW_SOURCE = "buy_now"
BUY_NOW_PRICE_CHANGED_CODE = "buy_now_price_changed"
BUY_NOW_AVAILABILITY_CHANGED_CODE = "buy_now_availability_changed"
BUY_NOW_SESSION_NOT_FOUND_CODE = "buy_now_session_not_found"
BUY_NOW_SESSION_EXPIRED_CODE = "buy_now_session_expired"
BUY_NOW_ACTION_CONFIRM_UPDATES = "confirm_updates"
BUY_NOW_ACTION_RETURN_TO_PRODUCT = "return_to_product"
BUY_NOW_ACTION_RESTART = "restart_buy_now"
CHECKOUT_IDEMPOTENCY_CONFLICT_CODE = "checkout_idempotency_conflict"

CHECKOUT_AVAILABILITY_CHANGED_DETAIL = (
    "პროდუქტის ხელმისაწვდომობა შეიცვალა. "
    "გთხოვთ გადაამოწმოთ მარაგი და სცადოთ ხელახლა."
)
CHECKOUT_PRODUCT_UNAVAILABLE_DETAIL = CHECKOUT_AVAILABILITY_CHANGED_DETAIL
CHECKOUT_STOCK_MISMATCH_DETAIL = CHECKOUT_AVAILABILITY_CHANGED_DETAIL
BUY_NOW_PRICE_CHANGED_DETAIL = (
    "\u10de\u10e0\u10dd\u10d3\u10e3\u10e5\u10e2\u10d8\u10e1 \u10e4\u10d0\u10e1\u10d8 "
    "\u10e8\u10d4\u10d8\u10ea\u10d5\u10d0\u10da\u10d0. \u10d2\u10d0\u10d3\u10d0\u10d0\u10db\u10dd\u10ec\u10db\u10d4\u10d7 "
    "\u10d3\u10d0 \u10d3\u10d0\u10d0\u10d3\u10d0\u10e1\u10e2\u10e3\u10e0\u10d4\u10d7 \u10d2\u10d0\u10d2\u10e0\u10eb\u10d4\u10da\u10d4\u10d1\u10d0."
)
BUY_NOW_QUANTITY_MISMATCH_DETAIL = CHECKOUT_AVAILABILITY_CHANGED_DETAIL
BUY_NOW_UNAVAILABLE_DETAIL = CHECKOUT_AVAILABILITY_CHANGED_DETAIL
BUY_NOW_SESSION_INACTIVE_DETAIL = (
    "\u10e1\u10ec\u10e0\u10d0\u10e4\u10d8 \u10e7\u10d8\u10d3\u10d5\u10d8\u10e1 \u10e1\u10d4\u10e1\u10d8\u10d0 "
    "\u10d0\u10e6\u10d0\u10e0 \u10d0\u10e0\u10d8\u10e1 \u10d0\u10e5\u10e2\u10d8\u10e3\u10e0\u10d8. \u10d3\u10d0\u10d1\u10e0\u10e3\u10dc\u10d3\u10d8\u10d7 "
    "\u10de\u10e0\u10dd\u10d3\u10e3\u10e5\u10e2\u10d8\u10e1 \u10d2\u10d5\u10d4\u10e0\u10d3\u10d6\u10d4 \u10d3\u10d0 \u10d3\u10d0\u10d8\u10ec\u10e7\u10d4\u10d7 \u10d7\u10d0\u10d5\u10d8\u10d3\u10d0\u10dc."
)

ALLOWED_ORDER_STATUS_TRANSITIONS = {
    OrderStatus.NEW: {OrderStatus.CONFIRMED, OrderStatus.PROCESSING},
    OrderStatus.CONFIRMED: {OrderStatus.PROCESSING},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

CANCELLABLE_ORDER_STATUSES = {
    OrderStatus.NEW,
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
}

PAYMENT_TRANSACTION_ORDER_STATUS_MAP = {
    PaymentTransactionStatus.PENDING: OrderPaymentStatus.PENDING,
    PaymentTransactionStatus.AUTHORIZED: OrderPaymentStatus.AUTHORIZED,
    PaymentTransactionStatus.PAID: OrderPaymentStatus.PAID,
    PaymentTransactionStatus.FAILED: OrderPaymentStatus.FAILED,
    PaymentTransactionStatus.CANCELLED: OrderPaymentStatus.CANCELLED,
    PaymentTransactionStatus.REFUND_PENDING: OrderPaymentStatus.REFUND_PENDING,
    PaymentTransactionStatus.REFUNDED: OrderPaymentStatus.REFUNDED,
}

ACTIVE_PAYMENT_ATTEMPT_STATUSES = {
    PaymentTransactionStatus.PENDING,
    PaymentTransactionStatus.AUTHORIZED,
}

STRONG_PAYMENT_STATUSES = {
    PaymentTransactionStatus.AUTHORIZED,
    PaymentTransactionStatus.PAID,
    PaymentTransactionStatus.REFUND_PENDING,
    PaymentTransactionStatus.REFUNDED,
}

ALLOWED_ORDER_PAYMENT_STATUS_TRANSITIONS = {
    OrderPaymentStatus.PENDING: {
        OrderPaymentStatus.AUTHORIZED,
        OrderPaymentStatus.PAID,
        OrderPaymentStatus.FAILED,
        OrderPaymentStatus.CANCELLED,
    },
    OrderPaymentStatus.AUTHORIZED: {
        OrderPaymentStatus.PAID,
        OrderPaymentStatus.FAILED,
        OrderPaymentStatus.CANCELLED,
    },
    OrderPaymentStatus.PAID: {
        OrderPaymentStatus.REFUND_PENDING,
        OrderPaymentStatus.REFUNDED,
    },
    OrderPaymentStatus.FAILED: {
        OrderPaymentStatus.PENDING,
        OrderPaymentStatus.AUTHORIZED,
        OrderPaymentStatus.PAID,
    },
    OrderPaymentStatus.CANCELLED: {
        OrderPaymentStatus.PENDING,
        OrderPaymentStatus.AUTHORIZED,
        OrderPaymentStatus.PAID,
    },
    OrderPaymentStatus.REFUND_PENDING: {
        OrderPaymentStatus.PAID,
        OrderPaymentStatus.REFUNDED,
    },
    OrderPaymentStatus.REFUNDED: set(),
}


class StockReservationError(Exception):
    def __init__(self, *, detail, issues=None):
        super().__init__(detail)
        self.detail = detail
        self.issues = issues or []


class CheckoutIdempotencyConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = CHECKOUT_IDEMPOTENCY_CONFLICT_CODE

    def __init__(self):
        super().__init__(
            {
                "detail": (
                    "ეს checkout მცდელობა სხვა შეკვეთის მონაცემებთან არის დაკავშირებული. "
                    "გთხოვთ, დაიწყოთ ახალი მცდელობა."
                ),
                "code": self.default_code,
            }
        )


class CheckoutPaymentInProgress(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "card_payment_already_active"

    def __init__(self):
        super().__init__(
            {
                "detail": (
                    "ამ შეკვეთისთვის ონლაინ გადახდა უკვე დაწყებულია. "
                    "დაასრულეთ არსებული გადახდა ან დაელოდეთ მის დასრულებას."
                ),
                "code": self.default_code,
            }
        )


@dataclass(frozen=True)
class OrderCreationResult:
    order: Order
    created: bool


def parse_checkout_idempotency_key(raw_value):
    if not raw_value:
        return None

    try:
        return uuid.UUID(str(raw_value).strip())
    except (TypeError, ValueError):
        raise ValidationError(
            {"idempotency_key": "Idempotency-Key must be a valid UUID."}
        )


def build_checkout_owner_fingerprint(*, user=None, guest_token=None):
    if user is not None and getattr(user, "is_authenticated", True):
        owner_value = f"user:{user.pk}"
    elif guest_token is not None:
        owner_value = f"guest:{guest_token}"
    else:
        raise ValueError("Checkout owner is required.")

    return hashlib.sha256(owner_value.encode("utf-8")).hexdigest()


def build_checkout_request_fingerprint(*, source, validated_data):
    fields = (
        "buyer_type",
        "company_name",
        "company_identification_code",
        "first_name",
        "last_name",
        "email",
        "phone",
        "city",
        "address_line",
        "note",
        "payment_method",
    )
    payload = {
        "source": source,
        **{
            field: str(validated_data.get(field, "") or "")
            for field in fields
        },
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def get_completed_idempotent_order(
    *,
    idempotency_key,
    source,
    owner_fingerprint,
    request_fingerprint,
):
    if idempotency_key is None:
        return None

    attempt = (
        CheckoutAttempt.objects.select_related("order")
        .prefetch_related("order__items")
        .filter(key=idempotency_key)
        .first()
    )
    if attempt is None:
        return None

    _validate_checkout_attempt(
        attempt=attempt,
        source=source,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    return attempt.order


def lock_checkout_attempt(
    *,
    idempotency_key,
    source,
    owner_fingerprint,
    request_fingerprint,
):
    if idempotency_key is None:
        return None

    attempt, _ = CheckoutAttempt.objects.get_or_create(
        key=idempotency_key,
        defaults={
            "source": source,
            "owner_fingerprint": owner_fingerprint,
            "request_fingerprint": request_fingerprint,
        },
    )
    # Lock only the checkout-attempt row. Joining the nullable order relation
    # here makes PostgreSQL reject the query because FOR UPDATE cannot lock the
    # nullable side of an outer join.
    attempt = CheckoutAttempt.objects.select_for_update().get(pk=attempt.pk)
    _validate_checkout_attempt(
        attempt=attempt,
        source=source,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    return attempt


def _validate_checkout_attempt(
    *,
    attempt,
    source,
    owner_fingerprint,
    request_fingerprint,
):
    if (
        attempt.source != source
        or attempt.owner_fingerprint != owner_fingerprint
        or attempt.request_fingerprint != request_fingerprint
    ):
        raise CheckoutIdempotencyConflict()


def build_cart_price_change_message(price_change_count):
    if price_change_count == 1:
        return (
            "კალათაში არსებული პროდუქტის ფასი შეიცვალა. "
            "გადაამოწმეთ ახალი ფასი და დაადასტურეთ გაგრძელება."
        )
    return (
        "კალათაში არსებული პროდუქტების ფასები შეიცვალა. "
        "გადაამოწმეთ ახალი ფასები და დაადასტურეთ გაგრძელება."
    )


def get_product_availability_issue(product):
    if product.status != ProductStatus.PUBLISHED or not product.category.is_active:
        return "unavailable"
    if not product.price_available:
        return "unavailable"
    if product.stock_qty <= 0:
        return "out_of_stock"
    return "available"


def get_cart_item_availability_issue(cart_item):
    return get_product_availability_issue(cart_item.product)


class CartPriceChanged(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "cart_price_changed"

    def __init__(self, *, price_change_count):
        super().__init__(
            {
                "detail": build_cart_price_change_message(price_change_count),
                "code": self.default_code,
                "price_change_count": price_change_count,
            }
        )


@dataclass(frozen=True)
class CartAvailabilityIssue:
    cart_item_id: int
    product_id: int
    issue_type: str
    requested_quantity: int
    available_quantity: int


class CartAvailabilityChangedError(Exception):
    def __init__(self, *, detail, issues):
        super().__init__(detail)
        self.detail = detail
        self.code = CART_AVAILABILITY_CHANGED_CODE
        self.issues = issues

    def to_response_data(self):
        return {
            "detail": self.detail,
            "code": self.code,
            "cart_issues": [asdict(issue) for issue in self.issues],
        }


@dataclass(frozen=True)
class BuyNowIssue:
    product_id: int
    issue_type: str
    requested_quantity: int
    available_quantity: int
    price_snapshot: Decimal
    current_price: Decimal

    def to_response_data(self):
        return {
            "product_id": self.product_id,
            "issue_type": self.issue_type,
            "requested_quantity": self.requested_quantity,
            "available_quantity": self.available_quantity,
            "price_snapshot": f"{self.price_snapshot:.2f}",
            "current_price": f"{self.current_price:.2f}",
        }


class BuyNowConflictError(Exception):
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, *, detail, code, recommended_action, issues):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.source = BUY_NOW_SOURCE
        self.recommended_action = recommended_action
        self.issues = issues

    def to_response_data(self):
        return {
            "detail": self.detail,
            "code": self.code,
            "source": self.source,
            "recommended_action": self.recommended_action,
            "buy_now_issues": [issue.to_response_data() for issue in self.issues],
        }


class BuyNowSessionStateError(Exception):
    def __init__(self, *, detail, code, status_code, recommended_action, clear_guest_token=False):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code
        self.source = BUY_NOW_SOURCE
        self.recommended_action = recommended_action
        self.clear_guest_token = clear_guest_token

    def to_response_data(self):
        return {
            "detail": self.detail,
            "code": self.code,
            "source": self.source,
            "recommended_action": self.recommended_action,
        }


@dataclass
class ResolvedCart:
    cart: Cart
    guest_token: uuid.UUID | None = None
    clear_guest_token: bool = False


@dataclass
class ResolvedWishlist:
    user: object | None = None
    guest_token: uuid.UUID | None = None
    clear_guest_token: bool = False


@dataclass
class ResolvedBuyNowSession:
    session: BuyNowSession | None = None
    guest_token: uuid.UUID | None = None
    clear_guest_token: bool = False


def get_cart_queryset():
    return Cart.objects.prefetch_related(
        Prefetch(
            "items",
            queryset=CartItem.objects.select_related("product", "product__category").prefetch_related(
                Prefetch(
                    "product__images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                )
            ),
        )
    )


def get_buy_now_session_queryset():
    return BuyNowSession.objects.select_related("product", "product__category").prefetch_related(
        Prefetch(
            "product__images",
            queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
        )
    )


def get_wishlist_queryset(*, user=None, guest_token=None):
    if user is None and guest_token is None:
        return WishlistItem.objects.none()

    if user is not None:
        owner_filters = {"user": user, "guest_token__isnull": True}
    else:
        owner_filters = {"user__isnull": True, "guest_token": guest_token}

    return (
        WishlistItem.objects.filter(
            **owner_filters,
            product__status=ProductStatus.PUBLISHED,
            product__category__is_active=True,
        )
        .select_related("product", "product__category")
        .prefetch_related(
            Prefetch(
                "product__images",
                queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
            )
        )
        .order_by("-created_at", "-id")
    )


def resolve_cart(request):
    user = request.user if request.user.is_authenticated else None
    raw_guest_token = request.COOKIES.get(CART_TOKEN_COOKIE_NAME)
    guest_token = _parse_guest_token(raw_guest_token)

    if user:
        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(user=user, is_active=True, defaults={"guest_token": None})
            if guest_token:
                guest_cart = _claim_guest_cart_for_merge(guest_token=guest_token)
                if guest_cart and guest_cart.pk != cart.pk:
                    _merge_carts(target_cart=cart, source_cart=guest_cart)
            return ResolvedCart(cart=cart, clear_guest_token=bool(raw_guest_token))

    if guest_token:
        cart = Cart.objects.filter(
            guest_token=guest_token,
            user__isnull=True,
            is_active=True,
        ).first()
        if cart:
            return ResolvedCart(cart=cart, guest_token=guest_token)

    new_token = uuid.uuid4()
    cart = Cart.objects.create(guest_token=new_token, is_active=True)
    return ResolvedCart(cart=cart, guest_token=new_token)


def resolve_wishlist(request):
    user = request.user if request.user.is_authenticated else None
    raw_guest_token = request.COOKIES.get(WISHLIST_TOKEN_COOKIE_NAME)
    guest_token = _parse_guest_token(raw_guest_token)

    if user:
        if guest_token:
            _merge_wishlists(user=user, guest_token=guest_token)
        return ResolvedWishlist(user=user, clear_guest_token=bool(raw_guest_token))

    if guest_token:
        return ResolvedWishlist(guest_token=guest_token)

    return ResolvedWishlist(guest_token=uuid.uuid4())


def resolve_buy_now_session(request, create=False):
    user = request.user if request.user.is_authenticated else None
    raw_guest_token = request.COOKIES.get(BUY_NOW_TOKEN_COOKIE_NAME)
    guest_token = _parse_guest_token(raw_guest_token)
    clear_guest_token = bool(raw_guest_token and guest_token is None)
    expired_detected = False

    if user:
        with transaction.atomic():
            user_session = BuyNowSession.objects.select_for_update().filter(user=user).first()
            if user_session and _is_buy_now_session_expired(user_session):
                user_session.delete()
                user_session = None
                expired_detected = True

            if guest_token:
                guest_session = (
                    BuyNowSession.objects.select_for_update()
                    .filter(guest_token=guest_token, user__isnull=True)
                    .first()
                )
                if guest_session:
                    if _is_buy_now_session_expired(guest_session):
                        guest_session.delete()
                        expired_detected = True
                        clear_guest_token = True
                    else:
                        if user_session and user_session.pk != guest_session.pk:
                            user_session.delete()
                        guest_session.user = user
                        guest_session.guest_token = None
                        guest_session.save(update_fields=["user", "guest_token", "updated_at"])
                        return ResolvedBuyNowSession(
                            session=guest_session,
                            clear_guest_token=bool(raw_guest_token),
                        )

            if user_session:
                return ResolvedBuyNowSession(
                    session=user_session,
                    clear_guest_token=bool(raw_guest_token),
                )

            if create:
                return ResolvedBuyNowSession(clear_guest_token=bool(raw_guest_token))

        if expired_detected:
            raise _build_buy_now_session_expired_error(clear_guest_token=bool(raw_guest_token))
        raise _build_buy_now_session_not_found_error(clear_guest_token=bool(raw_guest_token))

    if guest_token:
        with transaction.atomic():
            guest_session = (
                BuyNowSession.objects.select_for_update()
                .filter(guest_token=guest_token, user__isnull=True)
                .first()
            )
            if guest_session:
                if _is_buy_now_session_expired(guest_session):
                    guest_session.delete()
                    expired_detected = True
                else:
                    return ResolvedBuyNowSession(
                        session=guest_session,
                        guest_token=guest_token,
                    )

        if create:
            return ResolvedBuyNowSession(guest_token=guest_token)

    if create:
        return ResolvedBuyNowSession(guest_token=guest_token or uuid.uuid4())

    if expired_detected:
        raise _build_buy_now_session_expired_error(clear_guest_token=bool(raw_guest_token))
    raise _build_buy_now_session_not_found_error(clear_guest_token=bool(raw_guest_token))


def get_cart_item_for_update(cart, item_id):
    item = (
        CartItem.objects.select_related("product", "product__category")
        .filter(cart=cart, id=item_id)
        .first()
    )
    if not item:
        raise ValidationError({"detail": "Cart item not found."})
    return item


@transaction.atomic
def add_product_to_cart(cart, product, quantity):
    locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
    _ensure_product_is_purchasable(product)

    cart_item = (
        CartItem.objects.select_for_update()
        .filter(cart=locked_cart, product=product)
        .first()
    )
    desired_quantity = quantity + (cart_item.quantity if cart_item else 0)

    if desired_quantity > product.stock_qty:
        raise ValidationError({"quantity": "Requested quantity exceeds available stock."})

    if cart_item:
        cart_item.quantity = desired_quantity
        update_fields = ["quantity", "updated_at"]
        if cart_item.unit_price_snapshot != product.price:
            cart_item.unit_price_snapshot = product.price
            update_fields.append("unit_price_snapshot")
        cart_item.save(update_fields=update_fields)
        return cart_item

    return CartItem.objects.create(
        cart=locked_cart,
        product=product,
        unit_price_snapshot=product.price,
        quantity=quantity,
    )


@transaction.atomic
def update_cart_item_quantity(cart_item, quantity):
    Cart.objects.select_for_update().get(pk=cart_item.cart_id)
    locked_cart_item = (
        CartItem.objects.select_for_update()
        .select_related("product", "product__category")
        .get(pk=cart_item.pk)
    )
    product = locked_cart_item.product
    _ensure_product_is_purchasable(product)

    if quantity > product.stock_qty:
        raise ValidationError({"quantity": "Requested quantity exceeds available stock."})

    locked_cart_item.quantity = quantity
    update_fields = ["quantity", "updated_at"]
    if locked_cart_item.unit_price_snapshot != product.price:
        locked_cart_item.unit_price_snapshot = product.price
        update_fields.append("unit_price_snapshot")
    locked_cart_item.save(update_fields=update_fields)
    return locked_cart_item


@transaction.atomic
def remove_cart_item(cart_item):
    Cart.objects.select_for_update().get(pk=cart_item.cart_id)
    CartItem.objects.select_for_update().get(pk=cart_item.pk).delete()


@transaction.atomic
def confirm_cart_item_prices(cart):
    locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
    cart_items = list(
        locked_cart.items.select_for_update()
        .select_related("product")
        .order_by("id")
    )

    for cart_item in cart_items:
        if cart_item.unit_price_snapshot == cart_item.product.price:
            continue
        cart_item.unit_price_snapshot = cart_item.product.price
        cart_item.save(update_fields=["unit_price_snapshot", "updated_at"])


def get_buy_now_session_issue_data(session):
    return [
        issue.to_response_data()
        for issue in build_buy_now_session_issues(session=session)
    ]


@transaction.atomic
def create_or_replace_buy_now_session(*, session=None, user=None, guest_token=None, product, quantity):
    _ensure_product_is_purchasable(product)

    if quantity > product.stock_qty:
        raise ValidationError({"quantity": "Requested quantity exceeds available stock."})

    locked_session = session
    owner_kwargs = _get_buy_now_owner_kwargs(user=user, guest_token=guest_token)

    if locked_session is None:
        locked_session = BuyNowSession.objects.select_for_update().filter(**owner_kwargs).first()

    if locked_session:
        locked_session.product = product
        locked_session.quantity = quantity
        locked_session.unit_price_snapshot = product.price
        locked_session.save(update_fields=["product", "quantity", "unit_price_snapshot", "updated_at"])
        return locked_session

    return BuyNowSession.objects.create(
        product=product,
        quantity=quantity,
        unit_price_snapshot=product.price,
        **owner_kwargs,
    )


@transaction.atomic
def delete_buy_now_session(session):
    session.delete()


@transaction.atomic
def confirm_buy_now_session_updates(session):
    locked_session = (
        BuyNowSession.objects.select_for_update()
        .select_related("product", "product__category")
        .prefetch_related("product__images")
        .get(pk=session.pk)
    )
    if _is_buy_now_session_expired(locked_session):
        clear_guest_token = locked_session.user_id is None
        locked_session.delete()
        raise _build_buy_now_session_expired_error(clear_guest_token=clear_guest_token)

    locked_product = (
        Product.objects.select_for_update()
        .select_related("category")
        .prefetch_related("images")
        .get(pk=locked_session.product_id)
    )
    locked_session.product = locked_product

    issues = build_buy_now_session_issues(
        session=locked_session,
        product=locked_product,
    )
    if not issues:
        return locked_session

    if any(issue.issue_type in {"out_of_stock", "unavailable"} for issue in issues):
        raise build_buy_now_conflict_error(issues)

    update_fields = []
    quantity_issue = next((issue for issue in issues if issue.issue_type == "quantity_adjusted"), None)
    if quantity_issue and locked_session.quantity != quantity_issue.available_quantity:
        locked_session.quantity = quantity_issue.available_quantity
        update_fields.append("quantity")

    if any(issue.issue_type == "price_changed" for issue in issues):
        locked_session.unit_price_snapshot = locked_product.price
        update_fields.append("unit_price_snapshot")

    if update_fields:
        locked_session.save(update_fields=[*update_fields, "updated_at"])

    return locked_session


@transaction.atomic
def add_product_to_wishlist(*, user=None, guest_token=None, product):
    owner_kwargs = _get_wishlist_owner_kwargs(user=user, guest_token=guest_token)
    wishlist_item, _ = WishlistItem.objects.get_or_create(product=product, **owner_kwargs)
    return wishlist_item


@transaction.atomic
def remove_product_from_wishlist(*, user=None, guest_token=None, product_id):
    owner_kwargs = _get_wishlist_owner_kwargs(user=user, guest_token=guest_token)
    WishlistItem.objects.filter(product_id=product_id, **owner_kwargs).delete()


def _build_cart_availability_issues(
    *,
    cart_items,
    products_by_id,
    available_quantities=None,
):
    issues = []
    detail = None
    available_quantities = available_quantities or {}

    for item in cart_items:
        product = products_by_id.get(item.product_id)

        if not product:
            if detail is None:
                detail = CHECKOUT_PRODUCT_UNAVAILABLE_DETAIL
            issues.append(
                CartAvailabilityIssue(
                    cart_item_id=item.id,
                    product_id=item.product_id,
                    issue_type="unavailable",
                    requested_quantity=item.quantity,
                    available_quantity=0,
                )
            )
            continue

        availability_issue = get_product_availability_issue(product)
        if availability_issue == "unavailable":
            if detail is None:
                detail = CHECKOUT_PRODUCT_UNAVAILABLE_DETAIL
            issues.append(
                CartAvailabilityIssue(
                    cart_item_id=item.id,
                    product_id=item.product_id,
                    issue_type="unavailable",
                    requested_quantity=item.quantity,
                    available_quantity=0,
                )
            )
            continue

        available_quantity = available_quantities.get(
            product.pk,
            product.stock_qty,
        )
        if item.quantity <= available_quantity:
            continue

        if detail is None:
            detail = CHECKOUT_STOCK_MISMATCH_DETAIL

        issue_type = (
            "quantity_adjusted"
            if available_quantity > 0
            else "out_of_stock"
        )
        issues.append(
            CartAvailabilityIssue(
                cart_item_id=item.id,
                product_id=item.product_id,
                issue_type=issue_type,
                requested_quantity=item.quantity,
                available_quantity=available_quantity,
            )
        )

    return issues, detail


def build_buy_now_session_issues(
    *,
    session,
    product=None,
    available_quantity=None,
):
    current_product = product or session.product
    if available_quantity is None:
        available_quantity = current_product.stock_qty
    issues = []
    availability_issue = get_product_availability_issue(current_product)

    if availability_issue == "unavailable":
        return [
            BuyNowIssue(
                product_id=current_product.id,
                issue_type="unavailable",
                requested_quantity=session.quantity,
                available_quantity=0,
                price_snapshot=session.unit_price_snapshot,
                current_price=current_product.price,
            )
        ]

    if session.quantity > available_quantity:
        issue_type = (
            "quantity_adjusted"
            if available_quantity > 0
            else "out_of_stock"
        )
        issues.append(
            BuyNowIssue(
                product_id=current_product.id,
                issue_type=issue_type,
                requested_quantity=session.quantity,
                available_quantity=available_quantity,
                price_snapshot=session.unit_price_snapshot,
                current_price=current_product.price,
            )
        )
        if issue_type == "out_of_stock":
            return issues

    if session.unit_price_snapshot != current_product.price:
        issues.append(
            BuyNowIssue(
                product_id=current_product.id,
                issue_type="price_changed",
                requested_quantity=session.quantity,
                available_quantity=available_quantity,
                price_snapshot=session.unit_price_snapshot,
                current_price=current_product.price,
            )
        )

    return issues


@transaction.atomic
def sync_cart_availability_issues(*, cart, issues):
    adjustable_quantities = {
        issue.cart_item_id: issue.available_quantity
        for issue in issues
        if issue.issue_type == "quantity_adjusted" and issue.available_quantity > 0
    }
    if not adjustable_quantities:
        return

    cart_items = (
        CartItem.objects.select_for_update()
        .filter(cart=cart, id__in=adjustable_quantities.keys())
    )

    for cart_item in cart_items:
        next_quantity = adjustable_quantities.get(cart_item.id)
        if not next_quantity or cart_item.quantity == next_quantity:
            continue
        cart_item.quantity = next_quantity
        cart_item.save(update_fields=["quantity", "updated_at"])


@transaction.atomic
def create_order_from_cart(
    *,
    cart,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key=None,
    owner_fingerprint="",
    request_fingerprint="",
):
    checkout_attempt = lock_checkout_attempt(
        idempotency_key=idempotency_key,
        source=OrderCheckoutSource.CART,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    if checkout_attempt and checkout_attempt.order_id:
        return OrderCreationResult(order=checkout_attempt.order, created=False)

    locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
    cart_items = list(
        locked_cart.items.select_for_update()
        .select_related("product", "product__category")
        .prefetch_related("product__images")
        .order_by("id")
    )
    if not cart_items:
        raise ValidationError({"detail": "Cart is empty."})

    product_ids = [item.product_id for item in cart_items]
    products = (
        Product.objects.select_for_update()
        .select_related("category")
        .filter(id__in=product_ids)
        .order_by("id")
    )
    products_by_id = {product.id: product for product in products}
    reservation_owner = _get_reservation_owner_kwargs(
        user=user,
        guest_token=locked_cart.guest_token,
    )
    ensure_no_active_online_payment(
        source=OrderCheckoutSource.CART,
        owner_kwargs=reservation_owner,
        product_ids=product_ids,
    )
    checkout_reservation_ids = _get_existing_active_reservation_ids(
        source=OrderCheckoutSource.CART,
        owner_kwargs=reservation_owner,
        exclude_active_online_payments=True,
    )
    reserved_quantities = get_reserved_stock_quantities(
        product_ids=product_ids,
        exclude_reservation_ids=checkout_reservation_ids,
    )
    available_quantities = {
        product_id: max(
            product.stock_qty - reserved_quantities.get(product_id, 0),
            0,
        )
        for product_id, product in products_by_id.items()
    }

    availability_issues, availability_detail = _build_cart_availability_issues(
        cart_items=cart_items,
        products_by_id=products_by_id,
        available_quantities=available_quantities,
    )
    if availability_issues:
        raise CartAvailabilityChangedError(
            detail=availability_detail or CHECKOUT_STOCK_MISMATCH_DETAIL,
            issues=availability_issues,
        )

    price_change_count = 0

    for item in cart_items:
        product = products_by_id[item.product_id]
        if item.unit_price_snapshot != product.price:
            price_change_count += 1

    if price_change_count:
        raise CartPriceChanged(price_change_count=price_change_count)

    snapshots = []
    subtotal = Decimal("0.00")

    for item in cart_items:
        product = products_by_id[item.product_id]
        line_total = product.price * item.quantity
        subtotal += line_total
        snapshots.append(
            {
                "product": product,
                "product_name": product.name,
                "sku": product.sku,
                "unit_price": product.price,
                "quantity": item.quantity,
                "line_total": line_total,
                "primary_image_snapshot": build_product_primary_image_snapshot(item.product),
            }
        )

    terms_fields = terms_acceptance.to_order_fields()
    order = Order.objects.create(
        user=user if user and user.is_authenticated else None,
        buyer_type=validated_data.get("buyer_type", OrderBuyerType.INDIVIDUAL),
        company_name=validated_data.get("company_name", ""),
        company_identification_code=validated_data.get(
            "company_identification_code",
            "",
        ),
        payment_method=validated_data["payment_method"],
        status=OrderStatus.NEW,
        subtotal=subtotal,
        total=subtotal,
        first_name=validated_data["first_name"],
        last_name=validated_data["last_name"],
        email=validated_data.get("email", ""),
        phone=validated_data["phone"],
        city=validated_data["city"],
        address_line=validated_data["address_line"],
        note=validated_data.get("note", ""),
        **terms_fields,
    )
    order.order_number = build_order_number(order)
    order.save(update_fields=["order_number", "updated_at"])

    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=snapshot["product"],
                product_name=snapshot["product_name"],
                sku=snapshot["sku"],
                unit_price=snapshot["unit_price"],
                quantity=snapshot["quantity"],
                line_total=snapshot["line_total"],
                primary_image_snapshot=snapshot["primary_image_snapshot"],
            )
            for snapshot in snapshots
        ]
    )

    locked_products = []
    for snapshot in snapshots:
        product = snapshot["product"]
        product.stock_qty -= snapshot["quantity"]
        locked_products.append(product)

    Product.objects.bulk_update(locked_products, ["stock_qty"])
    locked_cart.items.all().delete()
    _finalize_checkout_reservations(
        reservation_ids=checkout_reservation_ids,
        order=order,
        expected_quantities={
            snapshot["product"].pk: snapshot["quantity"]
            for snapshot in snapshots
        },
    )

    if checkout_attempt:
        checkout_attempt.order = order
        checkout_attempt.save(update_fields=["order", "updated_at"])

    return OrderCreationResult(order=order, created=True)


@transaction.atomic
def create_order_from_buy_now_session(
    *,
    session,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key=None,
    owner_fingerprint="",
    request_fingerprint="",
):
    checkout_attempt = lock_checkout_attempt(
        idempotency_key=idempotency_key,
        source=OrderCheckoutSource.BUY_NOW,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    if checkout_attempt and checkout_attempt.order_id:
        return OrderCreationResult(order=checkout_attempt.order, created=False)

    locked_session = (
        BuyNowSession.objects.select_for_update()
        .select_related("product", "product__category")
        .prefetch_related("product__images")
        .get(pk=session.pk)
    )
    if _is_buy_now_session_expired(locked_session):
        clear_guest_token = locked_session.user_id is None
        locked_session.delete()
        raise _build_buy_now_session_expired_error(clear_guest_token=clear_guest_token)

    locked_product = (
        Product.objects.select_for_update()
        .select_related("category")
        .prefetch_related("images")
        .get(pk=locked_session.product_id)
    )
    locked_session.product = locked_product
    reservation_owner = _get_reservation_owner_kwargs(
        user=user if user is not None else locked_session.user,
        guest_token=locked_session.guest_token,
    )
    ensure_no_active_online_payment(
        source=OrderCheckoutSource.BUY_NOW,
        owner_kwargs=reservation_owner,
        product_ids=[locked_product.pk],
    )
    checkout_reservation_ids = _get_existing_active_reservation_ids(
        source=OrderCheckoutSource.BUY_NOW,
        owner_kwargs=reservation_owner,
        exclude_active_online_payments=True,
    )
    reserved_quantity = get_reserved_stock_quantities(
        product_ids=[locked_product.pk],
        exclude_reservation_ids=checkout_reservation_ids,
    ).get(locked_product.pk, 0)
    available_quantity = max(
        locked_product.stock_qty - reserved_quantity,
        0,
    )

    issues = build_buy_now_session_issues(
        session=locked_session,
        product=locked_product,
        available_quantity=available_quantity,
    )
    if issues:
        raise build_buy_now_conflict_error(issues)

    line_total = locked_product.price * locked_session.quantity

    terms_fields = terms_acceptance.to_order_fields()
    order = Order.objects.create(
        user=user if user and user.is_authenticated else None,
        checkout_source=OrderCheckoutSource.BUY_NOW,
        buyer_type=validated_data.get("buyer_type", OrderBuyerType.INDIVIDUAL),
        company_name=validated_data.get("company_name", ""),
        company_identification_code=validated_data.get(
            "company_identification_code",
            "",
        ),
        payment_method=validated_data["payment_method"],
        status=OrderStatus.NEW,
        subtotal=line_total,
        total=line_total,
        first_name=validated_data["first_name"],
        last_name=validated_data["last_name"],
        email=validated_data.get("email", ""),
        phone=validated_data["phone"],
        city=validated_data["city"],
        address_line=validated_data["address_line"],
        note=validated_data.get("note", ""),
        **terms_fields,
    )
    order.order_number = build_order_number(order)
    order.save(update_fields=["order_number", "updated_at"])

    OrderItem.objects.create(
        order=order,
        product=locked_product,
        product_name=locked_product.name,
        sku=locked_product.sku,
        unit_price=locked_product.price,
        quantity=locked_session.quantity,
        line_total=line_total,
        primary_image_snapshot=build_product_primary_image_snapshot(locked_product),
    )

    locked_product.stock_qty -= locked_session.quantity
    locked_product.save(update_fields=["stock_qty", "updated_at"])
    locked_session.delete()
    _finalize_checkout_reservations(
        reservation_ids=checkout_reservation_ids,
        order=order,
        expected_quantities={
            locked_product.pk: locked_session.quantity,
        },
    )

    if checkout_attempt:
        checkout_attempt.order = order
        checkout_attempt.save(update_fields=["order", "updated_at"])

    return OrderCreationResult(order=order, created=True)


def get_reserved_stock_quantities(*, product_ids, now=None, exclude_reservation_ids=None):
    now = now or timezone.now()
    queryset = StockReservationItem.objects.filter(
        product_id__in=product_ids,
        reservation__status=StockReservationStatus.ACTIVE,
        reservation__expires_at__gt=now,
    )
    if exclude_reservation_ids:
        queryset = queryset.exclude(reservation_id__in=exclude_reservation_ids)

    return {
        row["product_id"]: row["reserved_quantity"] or 0
        for row in queryset.values("product_id").annotate(reserved_quantity=Sum("quantity"))
    }


def get_available_stock_quantity(*, product, now=None, exclude_reservation_ids=None):
    reserved_quantity = get_reserved_stock_quantities(
        product_ids=[product.pk],
        now=now,
        exclude_reservation_ids=exclude_reservation_ids,
    ).get(product.pk, 0)
    return max(product.stock_qty - reserved_quantity, 0)


@transaction.atomic
def create_stock_reservation_from_cart(*, cart, user=None, guest_token=None, ttl_seconds=None):
    owner_kwargs = _get_reservation_owner_kwargs(user=user, guest_token=guest_token)
    cart_items = list(
        cart.items.select_related("product", "product__category")
        .select_for_update()
        .order_by("id")
    )
    if not cart_items:
        raise ValidationError({"detail": "Cart is empty."})

    product_ids = [item.product_id for item in cart_items]
    products = (
        Product.objects.select_for_update()
        .select_related("category")
        .filter(id__in=product_ids)
        .order_by("id")
    )
    products_by_id = {product.id: product for product in products}
    existing_reservation_ids = _get_existing_active_reservation_ids(
        source=OrderCheckoutSource.CART,
        owner_kwargs=owner_kwargs,
        exclude_active_online_payments=True,
    )
    reserved_quantities = get_reserved_stock_quantities(
        product_ids=product_ids,
        exclude_reservation_ids=existing_reservation_ids,
    )

    snapshots = []
    issues = []
    price_change_count = 0

    for item in cart_items:
        product = products_by_id.get(item.product_id)
        issue = _build_reservation_item_issue(
            product=product,
            requested_quantity=item.quantity,
            reserved_quantity=reserved_quantities.get(item.product_id, 0),
        )
        if issue:
            issue["cart_item_id"] = item.id
            issues.append(issue)
            continue

        if item.unit_price_snapshot != product.price:
            price_change_count += 1
            continue

        snapshots.append(
            {
                "product": product,
                "quantity": item.quantity,
                "unit_price_snapshot": product.price,
            }
        )

    if issues:
        raise StockReservationError(detail=CHECKOUT_AVAILABILITY_CHANGED_DETAIL, issues=issues)

    if price_change_count:
        raise CartPriceChanged(price_change_count=price_change_count)

    return _create_stock_reservation(
        source=OrderCheckoutSource.CART,
        owner_kwargs=owner_kwargs,
        snapshots=snapshots,
        ttl_seconds=ttl_seconds,
        release_reservation_ids=existing_reservation_ids,
    )


@transaction.atomic
def create_stock_reservation_from_buy_now_session(*, session, user=None, guest_token=None, ttl_seconds=None):
    owner_kwargs = _get_reservation_owner_kwargs(
        user=user if user is not None else session.user,
        guest_token=guest_token if guest_token is not None else session.guest_token,
    )
    locked_session = (
        BuyNowSession.objects.select_for_update()
        .select_related("product", "product__category")
        .get(pk=session.pk)
    )
    if _is_buy_now_session_expired(locked_session):
        raise _build_buy_now_session_expired_error(clear_guest_token=locked_session.user_id is None)

    product = (
        Product.objects.select_for_update()
        .select_related("category")
        .get(pk=locked_session.product_id)
    )
    existing_reservation_ids = _get_existing_active_reservation_ids(
        source=OrderCheckoutSource.BUY_NOW,
        owner_kwargs=owner_kwargs,
        exclude_active_online_payments=True,
    )
    reserved_quantity = get_reserved_stock_quantities(
        product_ids=[product.pk],
        exclude_reservation_ids=existing_reservation_ids,
    ).get(product.pk, 0)

    issue = _build_reservation_item_issue(
        product=product,
        requested_quantity=locked_session.quantity,
        reserved_quantity=reserved_quantity,
    )
    if issue:
        raise StockReservationError(detail=CHECKOUT_AVAILABILITY_CHANGED_DETAIL, issues=[issue])

    if locked_session.unit_price_snapshot != product.price:
        raise build_buy_now_conflict_error(
            [
                BuyNowIssue(
                    product_id=product.id,
                    issue_type="price_changed",
                    requested_quantity=locked_session.quantity,
                    available_quantity=product.stock_qty,
                    price_snapshot=locked_session.unit_price_snapshot,
                    current_price=product.price,
                )
            ]
        )

    return _create_stock_reservation(
        source=OrderCheckoutSource.BUY_NOW,
        owner_kwargs=owner_kwargs,
        snapshots=[
            {
                "product": product,
                "quantity": locked_session.quantity,
                "unit_price_snapshot": product.price,
            }
        ],
        ttl_seconds=ttl_seconds,
        release_reservation_ids=existing_reservation_ids,
    )


@transaction.atomic
def release_stock_reservation(reservation):
    locked_reservation = StockReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked_reservation.status != StockReservationStatus.ACTIVE:
        return locked_reservation

    locked_reservation.status = StockReservationStatus.RELEASED
    locked_reservation.released_at = timezone.now()
    locked_reservation.save(update_fields=["status", "released_at", "updated_at"])
    return locked_reservation


@transaction.atomic
def complete_stock_reservation(*, reservation, order):
    locked_reservation = StockReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked_reservation.status != StockReservationStatus.ACTIVE:
        raise StockReservationError(detail="Only active reservations can be completed.")
    if locked_reservation.expires_at <= timezone.now():
        raise StockReservationError(detail="Expired reservations cannot be completed.")

    locked_reservation.status = StockReservationStatus.COMPLETED
    locked_reservation.completed_order = order
    locked_reservation.completed_at = timezone.now()
    locked_reservation.save(
        update_fields=["status", "completed_order", "completed_at", "updated_at"]
    )
    return locked_reservation


@transaction.atomic
def expire_stock_reservations(*, now=None):
    now = now or timezone.now()
    return StockReservation.objects.filter(
        status=StockReservationStatus.ACTIVE,
        expires_at__lte=now,
    ).update(status=StockReservationStatus.EXPIRED, released_at=now, updated_at=now)


@transaction.atomic
def create_payment_transaction(
    *,
    order=None,
    reservation=None,
    amount,
    provider=PaymentProvider.MOCK,
    payment_method=OrderPaymentMethod.CARD,
    action=PaymentTransactionAction.AUTHORIZE,
    status=PaymentTransactionStatus.PENDING,
    currency="GEL",
    public_token=None,
    idempotency_key=None,
    provider_order_id="",
    provider_transaction_id="",
    provider_action_id="",
    provider_reference=None,
    checkout_snapshot=None,
    redirect_url="",
    expires_at=None,
):
    if order is None and reservation is None:
        raise ValueError("Payment transaction must belong to an order or reservation.")

    normalized_amount = Decimal(str(amount))
    if normalized_amount <= Decimal("0.00"):
        raise ValueError("Payment transaction amount must be greater than zero.")

    normalized_currency = str(currency or "").strip().upper()
    if normalized_currency != "GEL":
        raise ValueError("Only GEL payment transactions are supported.")

    PaymentProvider(provider)
    OrderPaymentMethod(payment_method)
    PaymentTransactionAction(action)
    PaymentTransactionStatus(status)

    if provider_reference is not None and not isinstance(provider_reference, dict):
        raise ValueError("Provider reference must be an object.")
    if checkout_snapshot is not None and not isinstance(checkout_snapshot, dict):
        raise ValueError("Checkout snapshot must be an object.")

    create_kwargs = {
        "order": order,
        "reservation": reservation,
        "provider": provider,
        "payment_method": payment_method,
        "action": action,
        "status": status,
        "amount": normalized_amount,
        "currency": normalized_currency,
        "provider_order_id": str(provider_order_id or "").strip(),
        "provider_transaction_id": str(provider_transaction_id or "").strip(),
        "provider_action_id": str(provider_action_id or "").strip(),
        "provider_reference": provider_reference or {},
        "checkout_snapshot": checkout_snapshot or {},
        "redirect_url": str(redirect_url or "").strip(),
        "expires_at": expires_at,
    }
    if public_token is not None:
        create_kwargs["public_token"] = public_token
    if idempotency_key is not None:
        create_kwargs["idempotency_key"] = idempotency_key

    return PaymentTransaction.objects.create(
        **create_kwargs,
    )


def authorize_payment(**kwargs):
    return _process_payment_transaction(action=PaymentTransactionAction.AUTHORIZE, **kwargs)


def capture_payment(**kwargs):
    return _process_payment_transaction(action=PaymentTransactionAction.CAPTURE, **kwargs)


def sale_payment(**kwargs):
    return _process_payment_transaction(action=PaymentTransactionAction.SALE, **kwargs)


def cancel_payment(**kwargs):
    return _process_payment_transaction(action=PaymentTransactionAction.CANCEL, **kwargs)


def refund_payment(**kwargs):
    return _process_payment_transaction(action=PaymentTransactionAction.REFUND, **kwargs)


def _process_payment_transaction(*, action, **kwargs):
    payment_transaction = _create_validated_payment_transaction(
        action=action,
        **kwargs,
    )
    provider_method = get_provider_method_for_action(payment_transaction.provider, action)
    try:
        provider_response = provider_method(transaction=payment_transaction)
    except Exception as error:
        try:
            record_payment_processing_exception(
                payment_transaction,
                error,
                error_code="provider_exception",
            )
        except Exception:
            logger.exception(
                "Failed to persist payment provider exception.",
                extra={"payment_transaction_id": payment_transaction.pk},
            )
        raise
    try:
        return apply_payment_provider_response(payment_transaction, provider_response)
    except Exception as error:
        try:
            record_payment_processing_exception(
                payment_transaction,
                error,
                error_code="provider_response_apply_exception",
            )
        except Exception:
            logger.exception(
                "Failed to persist payment response application exception.",
                extra={"payment_transaction_id": payment_transaction.pk},
            )
        raise


@transaction.atomic
def _create_validated_payment_transaction(
    *,
    action,
    order=None,
    reservation=None,
    **kwargs,
):
    locked_order = None
    locked_reservation = None
    if order is not None:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
    if reservation is not None:
        locked_reservation = StockReservation.objects.select_for_update().get(
            pk=reservation.pk
        )

    _validate_payment_operation(
        action=action,
        order=locked_order,
        reservation=locked_reservation,
        **kwargs,
    )
    return create_payment_transaction(
        action=action,
        order=locked_order,
        reservation=locked_reservation,
        **kwargs,
    )


def _validate_payment_operation(
    *,
    action,
    order=None,
    reservation=None,
    amount,
    provider=PaymentProvider.MOCK,
    payment_method=OrderPaymentMethod.CARD,
    currency="GEL",
    **kwargs,
):
    normalized_amount = Decimal(str(amount))
    if normalized_amount <= Decimal("0.00"):
        raise DjangoValidationError("Payment amount must be greater than zero.")
    if str(currency or "").strip().upper() != "GEL":
        raise DjangoValidationError("Only GEL payments are supported.")
    if payment_method != OrderPaymentMethod.CARD:
        raise DjangoValidationError("Payment transactions require card payment.")
    if order is None and reservation is None:
        raise DjangoValidationError(
            "Payment transaction must belong to an order or reservation."
        )

    active_target_filter = Q()
    if order is not None:
        active_target_filter |= Q(order=order)
    if reservation is not None:
        active_target_filter |= Q(reservation=reservation)

    if action in {
        PaymentTransactionAction.AUTHORIZE,
        PaymentTransactionAction.SALE,
    }:
        if _has_active_payment_attempt(
            target_filter=active_target_filter,
            provider=provider,
            payment_method=payment_method,
        ):
            raise DjangoValidationError(
                "An active payment attempt already exists for this checkout."
            )

    if reservation is not None:
        current_reservation = reservation
        if (
            current_reservation.status != StockReservationStatus.ACTIVE
            or current_reservation.expires_at <= timezone.now()
        ):
            raise DjangoValidationError(
                "Payment cannot start for an inactive or expired reservation."
            )

    if order is None:
        if action in {
            PaymentTransactionAction.CAPTURE,
            PaymentTransactionAction.REFUND,
        }:
            raise DjangoValidationError(
                "Capture and refund operations require an order."
            )
        return

    current_order = order
    if current_order.payment_method != OrderPaymentMethod.CARD:
        raise DjangoValidationError(
            "Payment operations require an order configured for card payment."
        )
    if normalized_amount > current_order.total:
        raise DjangoValidationError(
            "Payment amount cannot exceed the order total."
        )

    if action in {
        PaymentTransactionAction.AUTHORIZE,
        PaymentTransactionAction.SALE,
    }:
        if current_order.payment_status not in {
            OrderPaymentStatus.PENDING,
            OrderPaymentStatus.FAILED,
            OrderPaymentStatus.CANCELLED,
        }:
            raise DjangoValidationError(
                "A new payment attempt cannot start from the current payment status."
            )
    elif action == PaymentTransactionAction.CAPTURE:
        if current_order.payment_status != OrderPaymentStatus.AUTHORIZED:
            raise DjangoValidationError(
                "Only an authorized payment can be captured."
            )
        matching_authorization_exists = PaymentTransaction.objects.filter(
            order=current_order,
            provider=provider,
            payment_method=payment_method,
            action=PaymentTransactionAction.AUTHORIZE,
            status=PaymentTransactionStatus.AUTHORIZED,
            amount__gte=normalized_amount,
        ).exists()
        if not matching_authorization_exists:
            raise DjangoValidationError(
                "Capture requires a matching authorized payment transaction."
            )
    elif action == PaymentTransactionAction.CANCEL:
        if current_order.payment_status not in {
            OrderPaymentStatus.PENDING,
            OrderPaymentStatus.AUTHORIZED,
        }:
            raise DjangoValidationError(
                "Only a pending or authorized payment can be cancelled."
            )
    elif action == PaymentTransactionAction.REFUND:
        if current_order.payment_status not in {
            OrderPaymentStatus.PAID,
            OrderPaymentStatus.REFUND_PENDING,
        }:
            raise DjangoValidationError(
                "Only a paid payment can be refunded."
            )
        refundable_amount = _get_order_refundable_amount(current_order)
        if normalized_amount > refundable_amount:
            raise DjangoValidationError(
                "Refund amount cannot exceed the remaining refundable amount."
            )
        if normalized_amount != refundable_amount:
            raise DjangoValidationError(
                "Partial refunds are not enabled for this payment flow."
            )


def _get_order_refundable_amount(order):
    reserved_refund_amount = (
        PaymentTransaction.objects.filter(
            order=order,
            action=PaymentTransactionAction.REFUND,
            status__in=(
                PaymentTransactionStatus.REFUND_PENDING,
                PaymentTransactionStatus.REFUNDED,
            ),
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return max(order.total - reserved_refund_amount, Decimal("0.00"))


def _has_active_payment_attempt(*, target_filter, provider, payment_method):
    latest_attempt = (
        PaymentTransaction.objects.filter(
            target_filter,
            provider=provider,
            payment_method=payment_method,
            action__in=(
                PaymentTransactionAction.AUTHORIZE,
                PaymentTransactionAction.SALE,
            ),
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    if (
        latest_attempt is None
        or latest_attempt.status not in ACTIVE_PAYMENT_ATTEMPT_STATUSES
    ):
        return False

    later_successful_cancel_exists = PaymentTransaction.objects.filter(
        target_filter,
        provider=provider,
        payment_method=payment_method,
        action=PaymentTransactionAction.CANCEL,
        status=PaymentTransactionStatus.CANCELLED,
    ).filter(
        Q(created_at__gt=latest_attempt.created_at)
        | Q(
            created_at=latest_attempt.created_at,
            pk__gt=latest_attempt.pk,
        )
    ).exists()
    return not later_successful_cancel_exists


@transaction.atomic
def record_payment_processing_exception(
    payment_transaction,
    error,
    *,
    error_code,
):
    locked_transaction = PaymentTransaction.objects.select_for_update().get(
        pk=payment_transaction.pk
    )
    locked_transaction.error_code = error_code
    locked_transaction.error_message = str(error).strip()[:2000]
    locked_transaction.save(
        update_fields=["error_code", "error_message", "updated_at"]
    )
    return locked_transaction


def can_cancel_order(order):
    if (
        order.payment_method != OrderPaymentMethod.CASH_ON_DELIVERY
        and order.payment_status
        in {
            OrderPaymentStatus.AUTHORIZED,
            OrderPaymentStatus.PAID,
            OrderPaymentStatus.REFUND_PENDING,
        }
    ):
        return False
    return (
        order.status in CANCELLABLE_ORDER_STATUSES
        and order.stock_restored_at is None
    )


def can_transition_order_status(order, next_status):
    if next_status == order.status:
        return True

    if next_status == OrderStatus.CANCELLED:
        return False

    if (
        order.payment_method != OrderPaymentMethod.CASH_ON_DELIVERY
        and next_status
        in {
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        }
        and order.payment_status != OrderPaymentStatus.PAID
    ):
        return False

    return next_status in ALLOWED_ORDER_STATUS_TRANSITIONS.get(order.status, set())


def validate_order_status_transition(order, next_status):
    if next_status == order.status:
        return

    if next_status == OrderStatus.CANCELLED:
        raise DjangoValidationError(
            "Use the dedicated 'Cancel and restore stock' action to cancel this order."
        )

    if not can_transition_order_status(order, next_status):
        raise DjangoValidationError(
            f"Cannot change status from '{order.get_status_display()}' to "
            f"'{OrderStatus(next_status).label}'."
        )


def can_transition_order_payment_status(order, next_status):
    if next_status == order.payment_status:
        return True
    return next_status in ALLOWED_ORDER_PAYMENT_STATUS_TRANSITIONS.get(
        order.payment_status,
        set(),
    )


def validate_order_payment_status_transition(order, next_status):
    if can_transition_order_payment_status(order, next_status):
        return

    raise DjangoValidationError(
        f"Cannot change payment status from "
        f"'{order.get_payment_status_display()}' to "
        f"'{OrderPaymentStatus(next_status).label}'."
    )


@transaction.atomic
def transition_order_payment_status(order, next_status):
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    validate_order_payment_status_transition(locked_order, next_status)

    if next_status == locked_order.payment_status:
        return locked_order

    locked_order.payment_status = next_status
    locked_order.save(update_fields=["payment_status", "updated_at"])
    if next_status == OrderPaymentStatus.PAID:
        _send_purchase_event_if_eligible(locked_order)
    return locked_order


@transaction.atomic
def transition_order_status(order, next_status):
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    validate_order_status_transition(locked_order, next_status)

    if next_status == locked_order.status:
        return locked_order

    locked_order.status = next_status
    locked_order.save(update_fields=["status", "updated_at"])
    if (
        locked_order.payment_method == OrderPaymentMethod.CASH_ON_DELIVERY
        and next_status == OrderStatus.DELIVERED
    ):
        _send_purchase_event_if_eligible(locked_order)
    return locked_order


def _send_purchase_event_if_eligible(order):
    if (
        not order.marketing_consent
        or not settings.META_CAPI_ENABLED
        or not settings.META_PIXEL_ID
        or not settings.META_CAPI_ACCESS_TOKEN
    ):
        return
    is_cod_purchase = (
        order.payment_method == OrderPaymentMethod.CASH_ON_DELIVERY
        and order.status == OrderStatus.DELIVERED
    )
    is_online_purchase = (
        order.payment_method != OrderPaymentMethod.CASH_ON_DELIVERY
        and order.payment_status == OrderPaymentStatus.PAID
    )
    if not (is_cod_purchase or is_online_purchase):
        return
    transaction.on_commit(lambda: send_meta_purchase_event(order=order))


@transaction.atomic
def cancel_order_and_restore_stock(order):
    locked_order = (
        Order.objects.select_for_update()
        .get(pk=order.pk)
    )

    if not can_cancel_order(locked_order):
        if (
            locked_order.payment_method != OrderPaymentMethod.CASH_ON_DELIVERY
            and locked_order.payment_status
            in {
                OrderPaymentStatus.AUTHORIZED,
                OrderPaymentStatus.PAID,
                OrderPaymentStatus.REFUND_PENDING,
            }
        ):
            raise DjangoValidationError(
                "Authorized or paid card orders require the payment refund/cancel flow."
            )
        raise DjangoValidationError(
            "Only new, confirmed, or processing orders can be cancelled."
        )

    return _restore_order_stock_and_cancel(locked_order)


@transaction.atomic
def cancel_refunded_order_and_restore_stock(order):
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    if locked_order.payment_status != OrderPaymentStatus.REFUNDED:
        raise DjangoValidationError(
            "Stock can be restored only after the card refund is confirmed."
        )
    if (
        locked_order.status not in CANCELLABLE_ORDER_STATUSES
        or locked_order.stock_restored_at is not None
    ):
        raise DjangoValidationError(
            "Only new, confirmed, or processing refunded orders can restore stock."
        )

    return _restore_order_stock_and_cancel(locked_order)


def _restore_order_stock_and_cancel(locked_order):
    stock_restoration_rows = list(
        locked_order.items.order_by("product_id")
        .values("product_id")
        .annotate(quantity=Sum("quantity"))
    )
    if any(row["product_id"] is None for row in stock_restoration_rows):
        raise DjangoValidationError(
            "Cannot restore stock because one or more order items are no longer linked to a product."
        )

    product_ids = [row["product_id"] for row in stock_restoration_rows]
    locked_product_ids = list(
        Product.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if locked_product_ids != product_ids:
        raise DjangoValidationError(
            "Cannot restore stock because one or more order items are no longer linked to a product."
        )

    if stock_restoration_rows:
        quantity_increment = Case(
            *[
                When(pk=row["product_id"], then=row["quantity"])
                for row in stock_restoration_rows
            ],
            default=0,
            output_field=IntegerField(),
        )
        Product.objects.filter(pk__in=product_ids).update(
            stock_qty=F("stock_qty") + quantity_increment,
            updated_at=timezone.now(),
        )

    locked_order.status = OrderStatus.CANCELLED
    locked_order.stock_restored_at = timezone.now()
    locked_order.save(update_fields=["status", "stock_restored_at", "updated_at"])
    return locked_order


def build_order_number(order):
    return f"ORD-{timezone.now():%Y%m%d}-{order.pk:06d}"


def _get_stock_reservation_ttl_seconds(ttl_seconds=None):
    if ttl_seconds is not None:
        return max(int(ttl_seconds), 0)
    return max(int(settings.STOCK_RESERVATION_TTL_SECONDS), 0)


def _get_reservation_owner_kwargs(*, user=None, guest_token=None):
    if user is not None and getattr(user, "is_authenticated", True):
        return {"user": user, "guest_token": None}
    if guest_token is not None:
        return {"user": None, "guest_token": guest_token}
    raise ValueError("Stock reservation owner is required.")


def _get_existing_active_reservation_ids(
    *,
    source,
    owner_kwargs,
    exclude_active_online_payments=False,
):
    queryset = StockReservation.objects.select_for_update().filter(
        source=source,
        status=StockReservationStatus.ACTIVE,
        expires_at__gt=timezone.now(),
        **owner_kwargs,
    )
    if exclude_active_online_payments:
        active_online_reservation_ids = PaymentTransaction.objects.filter(
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
            status=PaymentTransactionStatus.PENDING,
            reservation_id__isnull=False,
        ).values("reservation_id")
        queryset = queryset.exclude(
            pk__in=active_online_reservation_ids,
        )
    return list(queryset.values_list("id", flat=True))


def ensure_no_active_online_payment(*, source, owner_kwargs, product_ids=None):
    payment_owner_filter = {}
    if owner_kwargs.get("user") is not None:
        payment_owner_filter["reservation__user"] = owner_kwargs["user"]
    elif owner_kwargs.get("guest_token") is not None:
        payment_owner_filter["reservation__guest_token"] = owner_kwargs[
            "guest_token"
        ]
    else:
        return

    active_payments = PaymentTransaction.objects.filter(
        provider=PaymentProvider.BOG,
        action=PaymentTransactionAction.SALE,
        status=PaymentTransactionStatus.PENDING,
        reservation__source=source,
        **payment_owner_filter,
    )
    if product_ids is not None:
        normalized_product_ids = {
            int(product_id)
            for product_id in product_ids
            if product_id is not None
        }
        if not normalized_product_ids:
            return
        active_payments = active_payments.filter(
            reservation_id__in=StockReservationItem.objects.filter(
                product_id__in=normalized_product_ids,
            ).values("reservation_id"),
        )

    if active_payments.exists():
        raise CheckoutPaymentInProgress()


def _finalize_checkout_reservations(
    *,
    reservation_ids,
    order,
    expected_quantities,
):
    if not reservation_ids:
        return

    reservation_quantities = {}
    for reservation_id, product_id, quantity in (
        StockReservationItem.objects.filter(
            reservation_id__in=reservation_ids,
        )
        .order_by("reservation_id", "product_id")
        .values_list("reservation_id", "product_id", "quantity")
    ):
        reservation_quantities.setdefault(reservation_id, {})[product_id] = quantity

    now = timezone.now()
    matching_ids = [
        reservation_id
        for reservation_id in reservation_ids
        if reservation_quantities.get(reservation_id, {}) == expected_quantities
    ]
    stale_ids = [
        reservation_id
        for reservation_id in reservation_ids
        if reservation_id not in matching_ids
    ]

    if matching_ids:
        StockReservation.objects.filter(
            id__in=matching_ids,
            status=StockReservationStatus.ACTIVE,
        ).update(
            status=StockReservationStatus.COMPLETED,
            completed_order=order,
            completed_at=now,
            updated_at=now,
        )

    if stale_ids:
        StockReservation.objects.filter(
            id__in=stale_ids,
            status=StockReservationStatus.ACTIVE,
        ).update(
            status=StockReservationStatus.RELEASED,
            released_at=now,
            updated_at=now,
        )


def _create_stock_reservation(*, source, owner_kwargs, snapshots, ttl_seconds=None, release_reservation_ids=None):
    if not snapshots:
        raise StockReservationError(detail=CHECKOUT_AVAILABILITY_CHANGED_DETAIL)

    now = timezone.now()
    if release_reservation_ids:
        StockReservation.objects.filter(id__in=release_reservation_ids).update(
            status=StockReservationStatus.RELEASED,
            released_at=now,
            updated_at=now,
        )

    reservation = StockReservation.objects.create(
        source=source,
        expires_at=now + timedelta(seconds=_get_stock_reservation_ttl_seconds(ttl_seconds)),
        **owner_kwargs,
    )
    StockReservationItem.objects.bulk_create(
        [
            StockReservationItem(
                reservation=reservation,
                product=snapshot["product"],
                quantity=snapshot["quantity"],
                unit_price_snapshot=snapshot["unit_price_snapshot"],
            )
            for snapshot in snapshots
        ]
    )
    return reservation


def _build_reservation_item_issue(*, product, requested_quantity, reserved_quantity):
    if product is None:
        return {
            "product_id": None,
            "issue_type": "unavailable",
            "requested_quantity": requested_quantity,
            "available_quantity": 0,
        }

    availability_issue = get_product_availability_issue(product)
    if availability_issue == "unavailable":
        return {
            "product_id": product.pk,
            "issue_type": "unavailable",
            "requested_quantity": requested_quantity,
            "available_quantity": 0,
        }

    available_quantity = max(product.stock_qty - reserved_quantity, 0)
    if requested_quantity <= available_quantity:
        return None

    return {
        "product_id": product.pk,
        "issue_type": "quantity_adjusted" if available_quantity > 0 else "out_of_stock",
        "requested_quantity": requested_quantity,
        "available_quantity": available_quantity,
    }


@transaction.atomic
def apply_payment_provider_response(payment_transaction, provider_response):
    payment_transaction = PaymentTransaction.objects.select_for_update().get(
        pk=payment_transaction.pk
    )
    locked_order = None
    if payment_transaction.order_id:
        locked_order = Order.objects.select_for_update().get(
            pk=payment_transaction.order_id
        )
    elif payment_transaction.reservation_id:
        StockReservation.objects.select_for_update().get(
            pk=payment_transaction.reservation_id
        )

    try:
        PaymentTransactionStatus(provider_response.status)
    except ValueError as error:
        raise DjangoValidationError(
            f"Unsupported provider payment status: {provider_response.status}"
        ) from error
    if not isinstance(provider_response.provider_reference, dict):
        raise DjangoValidationError("Provider reference must be an object.")

    provider_order_id = str(provider_response.provider_order_id or "").strip()
    provider_transaction_id = str(provider_response.provider_transaction_id or "").strip()
    provider_action_id = str(provider_response.provider_action_id or "").strip()

    duplicate_transaction = _find_duplicate_provider_response(
        payment_transaction=payment_transaction,
        provider_transaction_id=provider_transaction_id,
        provider_action_id=provider_action_id,
    )
    if duplicate_transaction:
        payment_transaction.status = PaymentTransactionStatus.CANCELLED
        payment_transaction.error_code = "duplicate_provider_response"
        payment_transaction.error_message = (
            "Provider response is already linked to another local transaction."
        )
        payment_transaction.provider_order_id = provider_order_id
        payment_transaction.provider_reference = provider_response.provider_reference
        payment_transaction.cancelled_at = timezone.now()
        payment_transaction.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "provider_order_id",
                "provider_reference",
                "cancelled_at",
                "updated_at",
            ]
        )
        return duplicate_transaction

    now = timezone.now()
    payment_transaction.status = provider_response.status
    payment_transaction.provider_order_id = provider_order_id
    payment_transaction.provider_transaction_id = provider_transaction_id
    payment_transaction.provider_action_id = provider_action_id
    payment_transaction.provider_reference = provider_response.provider_reference
    payment_transaction.error_code = provider_response.error_code
    payment_transaction.error_message = provider_response.error_message

    update_fields = [
        "status",
        "provider_order_id",
        "provider_transaction_id",
        "provider_action_id",
        "provider_reference",
        "error_code",
        "error_message",
        "updated_at",
    ]
    if provider_response.status == PaymentTransactionStatus.AUTHORIZED:
        payment_transaction.authorized_at = now
        update_fields.append("authorized_at")
    elif provider_response.status == PaymentTransactionStatus.PAID:
        payment_transaction.captured_at = now
        update_fields.append("captured_at")
    elif provider_response.status == PaymentTransactionStatus.CANCELLED:
        payment_transaction.cancelled_at = now
        update_fields.append("cancelled_at")
    elif provider_response.status == PaymentTransactionStatus.REFUNDED:
        payment_transaction.refunded_at = now
        update_fields.append("refunded_at")

    payment_transaction.save(update_fields=update_fields)
    _sync_order_payment_status(
        payment_transaction,
        locked_order=locked_order,
    )
    return payment_transaction


def _find_duplicate_provider_response(
    *,
    payment_transaction,
    provider_transaction_id,
    provider_action_id,
):
    identity_filters = Q()
    if provider_transaction_id:
        identity_filters |= Q(provider_transaction_id=provider_transaction_id)
    if provider_action_id:
        identity_filters |= Q(provider_action_id=provider_action_id)
    if not identity_filters:
        return None

    matching_transactions = list(
        PaymentTransaction.objects.select_for_update()
        .filter(identity_filters, provider=payment_transaction.provider)
        .exclude(pk=payment_transaction.pk)
        .order_by("pk")[:2]
    )
    if len(matching_transactions) > 1:
        raise DjangoValidationError(
            "Provider response identifiers point to different payment actions."
        )
    existing_transaction = matching_transactions[0] if matching_transactions else None
    if not existing_transaction:
        return None

    if (
        existing_transaction.order_id != payment_transaction.order_id
        or existing_transaction.reservation_id != payment_transaction.reservation_id
        or existing_transaction.action != payment_transaction.action
        or existing_transaction.amount != payment_transaction.amount
        or existing_transaction.currency != payment_transaction.currency
    ):
        raise DjangoValidationError(
            "Provider response identity is already linked to another payment action."
        )
    return existing_transaction


def _sync_order_payment_status(payment_transaction, *, locked_order=None):
    if not payment_transaction.order_id:
        return False

    next_status = PAYMENT_TRANSACTION_ORDER_STATUS_MAP.get(payment_transaction.status)
    if not next_status:
        return False

    if locked_order is None:
        locked_order = Order.objects.select_for_update().get(
            pk=payment_transaction.order_id
        )

    if next_status in {
        OrderPaymentStatus.FAILED,
        OrderPaymentStatus.CANCELLED,
    }:
        newer_strong_transaction_exists = PaymentTransaction.objects.filter(
            order=locked_order,
            status__in=STRONG_PAYMENT_STATUSES,
        ).filter(
            Q(created_at__gt=payment_transaction.created_at)
            | Q(
                created_at=payment_transaction.created_at,
                pk__gt=payment_transaction.pk,
            )
        ).exists()
        if newer_strong_transaction_exists:
            return False

    if not can_transition_order_payment_status(locked_order, next_status):
        return False

    if locked_order.payment_status == next_status:
        return True

    locked_order.payment_status = next_status
    locked_order.save(update_fields=["payment_status", "updated_at"])
    if next_status == OrderPaymentStatus.PAID:
        _send_purchase_event_if_eligible(locked_order)
    return True


def _parse_guest_token(raw_token):
    if not raw_token:
        return None
    try:
        return uuid.UUID(str(raw_token))
    except (TypeError, ValueError):
        return None


def parse_guest_token(raw_token):
    return _parse_guest_token(raw_token)


def _build_buy_now_session_not_found_error(*, clear_guest_token=False):
    return BuyNowSessionStateError(
        detail=BUY_NOW_SESSION_INACTIVE_DETAIL,
        code=BUY_NOW_SESSION_NOT_FOUND_CODE,
        status_code=status.HTTP_404_NOT_FOUND,
        recommended_action=BUY_NOW_ACTION_RESTART,
        clear_guest_token=clear_guest_token,
    )


def _build_buy_now_session_expired_error(*, clear_guest_token=False):
    return BuyNowSessionStateError(
        detail=BUY_NOW_SESSION_INACTIVE_DETAIL,
        code=BUY_NOW_SESSION_EXPIRED_CODE,
        status_code=status.HTTP_410_GONE,
        recommended_action=BUY_NOW_ACTION_RESTART,
        clear_guest_token=clear_guest_token,
    )


def build_buy_now_conflict_error(issues):
    issue_types = {issue.issue_type for issue in issues}

    if "unavailable" in issue_types or "out_of_stock" in issue_types:
        return BuyNowConflictError(
            detail=BUY_NOW_UNAVAILABLE_DETAIL,
            code=BUY_NOW_AVAILABILITY_CHANGED_CODE,
            recommended_action=BUY_NOW_ACTION_RETURN_TO_PRODUCT,
            issues=issues,
        )

    if "quantity_adjusted" in issue_types:
        return BuyNowConflictError(
            detail=BUY_NOW_QUANTITY_MISMATCH_DETAIL,
            code=BUY_NOW_AVAILABILITY_CHANGED_CODE,
            recommended_action=BUY_NOW_ACTION_CONFIRM_UPDATES,
            issues=issues,
        )

    return BuyNowConflictError(
        detail=BUY_NOW_PRICE_CHANGED_DETAIL,
        code=BUY_NOW_PRICE_CHANGED_CODE,
        recommended_action=BUY_NOW_ACTION_CONFIRM_UPDATES,
        issues=issues,
    )


def _get_buy_now_expiry_cutoff():
    ttl_seconds = max(int(settings.BUY_NOW_SESSION_TTL_SECONDS), 0)
    return timezone.now() - timedelta(seconds=ttl_seconds)


def _is_buy_now_session_expired(session):
    return session.updated_at < _get_buy_now_expiry_cutoff()


def _ensure_product_is_purchasable(product):
    if product.status != ProductStatus.PUBLISHED or not product.category.is_active:
        raise ValidationError({"product_id": "Product is not available."})
    if not product.price_available:
        raise ValidationError({"product_id": "Product price is not available."})
    if product.stock_qty <= 0:
        raise ValidationError({"quantity": "Product is out of stock."})


@transaction.atomic
def _merge_carts(*, target_cart, source_cart):
    source_items = list(source_cart.items.select_for_update().select_related("product").order_by("id"))
    existing_items = {
        item.product_id: item
        for item in target_cart.items.select_for_update().select_related("product")
    }

    for source_item in source_items:
        target_item = existing_items.get(source_item.product_id)
        stock_qty = source_item.product.stock_qty
        merged_quantity = source_item.quantity + (target_item.quantity if target_item else 0)
        merged_quantity = min(merged_quantity, stock_qty)

        if merged_quantity <= 0:
            if target_item:
                target_item.delete()
            continue

        if target_item:
            target_item.quantity = merged_quantity
            target_item.save(update_fields=["quantity", "updated_at"])
            continue

        existing_items[source_item.product_id] = CartItem.objects.create(
            cart=target_cart,
            product=source_item.product,
            unit_price_snapshot=source_item.unit_price_snapshot,
            quantity=merged_quantity,
        )

    source_cart.items.all().delete()
    source_cart.is_active = False
    source_cart.save(update_fields=["is_active", "updated_at"])


@transaction.atomic
def _claim_guest_cart_for_merge(*, guest_token):
    guest_cart = (
        Cart.objects.select_for_update()
        .filter(
            guest_token=guest_token,
            user__isnull=True,
            is_active=True,
        )
        .first()
    )
    if not guest_cart:
        return None

    # Mark the guest cart inactive before merging so repeated authenticated
    # loads with the same stale cookie cannot merge the same quantities twice.
    guest_cart.is_active = False
    guest_cart.save(update_fields=["is_active", "updated_at"])
    return guest_cart


@transaction.atomic
def _merge_wishlists(*, user, guest_token):
    guest_items = list(
        WishlistItem.objects.filter(user__isnull=True, guest_token=guest_token)
        .order_by("-created_at", "-id")
        .values_list("product_id", flat=True)
    )
    if not guest_items:
        return

    # Concurrent authenticated loads can attempt the same guest-to-user merge
    # before the stale guest cookie is cleared in the browser. Let the unique
    # constraint de-duplicate the inserts instead of surfacing a 500.
    WishlistItem.objects.bulk_create(
        [WishlistItem(user=user, product_id=product_id) for product_id in guest_items],
        ignore_conflicts=True,
    )

    WishlistItem.objects.filter(user__isnull=True, guest_token=guest_token).delete()


def _get_wishlist_owner_kwargs(*, user=None, guest_token=None):
    if user is not None:
        return {"user": user, "guest_token": None}
    if guest_token is not None:
        return {"user": None, "guest_token": guest_token}
    raise ValueError("Wishlist owner is required.")


def _get_buy_now_owner_kwargs(*, user=None, guest_token=None):
    if user is not None:
        return {"user": user, "guest_token": None}
    if guest_token is not None:
        return {"user": None, "guest_token": guest_token}
    raise ValueError("Buy now owner is required.")
