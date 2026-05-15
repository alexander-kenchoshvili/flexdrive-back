import uuid
from datetime import timedelta
from dataclasses import asdict, dataclass
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from catalog.models import Product, ProductImage, ProductStatus

from .images import build_product_primary_image_snapshot
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    Order,
    OrderCheckoutSource,
    OrderItem,
    OrderStatus,
    WishlistItem,
)

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
    _ensure_product_is_purchasable(product)

    cart_item = CartItem.objects.select_for_update().filter(cart=cart, product=product).first()
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
        cart=cart,
        product=product,
        unit_price_snapshot=product.price,
        quantity=quantity,
    )


@transaction.atomic
def update_cart_item_quantity(cart_item, quantity):
    product = cart_item.product
    _ensure_product_is_purchasable(product)

    if quantity > product.stock_qty:
        raise ValidationError({"quantity": "Requested quantity exceeds available stock."})

    cart_item.quantity = quantity
    update_fields = ["quantity", "updated_at"]
    if cart_item.unit_price_snapshot != product.price:
        cart_item.unit_price_snapshot = product.price
        update_fields.append("unit_price_snapshot")
    cart_item.save(update_fields=update_fields)
    return cart_item


@transaction.atomic
def remove_cart_item(cart_item):
    cart_item.delete()


@transaction.atomic
def confirm_cart_item_prices(cart):
    cart_items = list(
        cart.items.select_for_update()
        .select_related("product")
        .order_by("id")
    )

    for cart_item in cart_items:
        if cart_item.unit_price_snapshot == cart_item.product.price:
            continue
        cart_item.unit_price_snapshot = cart_item.product.price
        cart_item.save(update_fields=["unit_price_snapshot", "updated_at"])


def get_buy_now_session_issue_data(session):
    return [issue.to_response_data() for issue in _build_buy_now_session_issues(session=session)]


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

    issues = _build_buy_now_session_issues(session=locked_session, product=locked_product)
    if not issues:
        return locked_session

    if any(issue.issue_type in {"out_of_stock", "unavailable"} for issue in issues):
        raise _build_buy_now_conflict_error(issues)

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


def _build_cart_availability_issues(*, cart_items, products_by_id):
    issues = []
    detail = None

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

        if item.quantity <= product.stock_qty:
            continue

        if detail is None:
            detail = CHECKOUT_STOCK_MISMATCH_DETAIL

        issue_type = "quantity_adjusted" if product.stock_qty > 0 else "out_of_stock"
        issues.append(
            CartAvailabilityIssue(
                cart_item_id=item.id,
                product_id=item.product_id,
                issue_type=issue_type,
                requested_quantity=item.quantity,
                available_quantity=product.stock_qty,
            )
        )

    return issues, detail


def _build_buy_now_session_issues(*, session, product=None):
    current_product = product or session.product
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

    if session.quantity > current_product.stock_qty:
        issue_type = "quantity_adjusted" if current_product.stock_qty > 0 else "out_of_stock"
        issues.append(
            BuyNowIssue(
                product_id=current_product.id,
                issue_type=issue_type,
                requested_quantity=session.quantity,
                available_quantity=current_product.stock_qty,
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
                available_quantity=current_product.stock_qty,
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
def create_order_from_cart(*, cart, user, validated_data):
    cart_items = list(
        cart.items.select_related("product", "product__category")
        .prefetch_related("product__images")
        .order_by("id")
    )
    if not cart_items:
        raise ValidationError({"detail": "Cart is empty."})

    product_ids = [item.product_id for item in cart_items]
    products = Product.objects.select_for_update().select_related("category").filter(id__in=product_ids)
    products_by_id = {product.id: product for product in products}

    availability_issues, availability_detail = _build_cart_availability_issues(
        cart_items=cart_items,
        products_by_id=products_by_id,
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

    order = Order.objects.create(
        user=user if user and user.is_authenticated else None,
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
    cart.items.all().delete()

    return order


@transaction.atomic
def create_order_from_buy_now_session(*, session, user, validated_data):
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

    issues = _build_buy_now_session_issues(session=locked_session, product=locked_product)
    if issues:
        raise _build_buy_now_conflict_error(issues)

    line_total = locked_product.price * locked_session.quantity

    order = Order.objects.create(
        user=user if user and user.is_authenticated else None,
        checkout_source=OrderCheckoutSource.BUY_NOW,
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

    return order


def can_cancel_order(order):
    return (
        order.status in CANCELLABLE_ORDER_STATUSES
        and order.stock_restored_at is None
    )


def can_transition_order_status(order, next_status):
    if next_status == order.status:
        return True

    if next_status == OrderStatus.CANCELLED:
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


@transaction.atomic
def transition_order_status(order, next_status):
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    validate_order_status_transition(locked_order, next_status)

    if next_status == locked_order.status:
        return locked_order

    locked_order.status = next_status
    locked_order.save(update_fields=["status", "updated_at"])
    return locked_order


@transaction.atomic
def cancel_order_and_restore_stock(order):
    locked_order = (
        Order.objects.select_for_update()
        .prefetch_related("items__product")
        .get(pk=order.pk)
    )

    if not can_cancel_order(locked_order):
        raise DjangoValidationError(
            "Only new, confirmed, or processing orders can be cancelled."
        )

    products_to_update = {}
    for item in locked_order.items.all():
        if item.product is None:
            raise DjangoValidationError(
                "Cannot restore stock because one or more order items are no longer linked to a product."
            )

        product = item.product
        if product.pk not in products_to_update:
            products_to_update[product.pk] = product
        products_to_update[product.pk].stock_qty += item.quantity

    if products_to_update:
        Product.objects.bulk_update(products_to_update.values(), ["stock_qty"])

    locked_order.status = OrderStatus.CANCELLED
    locked_order.stock_restored_at = timezone.now()
    locked_order.save(update_fields=["status", "stock_restored_at", "updated_at"])
    return locked_order


def build_order_number(order):
    return f"ORD-{timezone.now():%Y%m%d}-{order.pk:06d}"


def _parse_guest_token(raw_token):
    if not raw_token:
        return None
    try:
        return uuid.UUID(str(raw_token))
    except (TypeError, ValueError):
        return None


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


def _build_buy_now_conflict_error(issues):
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
