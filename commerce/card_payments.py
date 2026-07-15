import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .bog_payments import (
    BogAuthenticationError,
    BogConfigurationError,
    BogPaymentError,
    BogPaymentsClient,
    BogResponseError,
    BogTransportError,
    BogValidationError,
)
from .images import build_product_primary_image_snapshot
from .delivery_quotes import delivery_order_fields, resolve_checkout_delivery
from .models import (
    BuyNowSession,
    Cart,
    OrderCheckoutSource,
    OrderPaymentMethod,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationItem,
    StockReservationStatus,
)
from .services import (
    StockReservationError,
    build_buy_now_conflict_error,
    build_buy_now_session_issues,
    create_payment_transaction,
    create_stock_reservation_from_buy_now_session,
    create_stock_reservation_from_cart,
    lock_checkout_attempt,
)


CHECKOUT_SNAPSHOT_VERSION = 1
CARD_PAYMENT_ACTIVE_CODE = "card_payment_already_active"
CARD_PAYMENT_DISABLED_CODE = "card_payments_disabled"
CARD_PAYMENT_START_FAILED_CODE = "card_payment_start_failed"
CARD_PAYMENT_START_PENDING_CODE = "card_payment_start_pending"


class CardPaymentError(Exception):
    def __init__(
        self,
        *,
        detail,
        code,
        payment=None,
        retryable=False,
    ):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.payment = payment
        self.retryable = retryable


class CardPaymentsDisabled(CardPaymentError):
    def __init__(self):
        super().__init__(
            detail="ბარათით გადახდა დროებით მიუწვდომელია.",
            code=CARD_PAYMENT_DISABLED_CODE,
        )


class ActiveCardPaymentExists(CardPaymentError):
    def __init__(self, payment):
        super().__init__(
            detail=(
                "ამ შეკვეთისთვის ონლაინ გადახდა უკვე დაწყებულია. "
                "გააგრძელეთ არსებული გადახდა ან დაელოდეთ მის დასრულებას."
            ),
            code=CARD_PAYMENT_ACTIVE_CODE,
            payment=payment,
        )


class CardPaymentStartPending(CardPaymentError):
    def __init__(self, payment, *, retryable=True):
        super().__init__(
            detail=(
                "ბანკთან კავშირი დროებით ვერ დადასტურდა. "
                "იგივე გადახდის მცდელობა ხელახლა სცადეთ."
            ),
            code=CARD_PAYMENT_START_PENDING_CODE,
            payment=payment,
            retryable=retryable,
        )


class CardPaymentStartFailed(CardPaymentError):
    def __init__(self, payment):
        super().__init__(
            detail=(
                "ონლაინ გადახდის დაწყება ვერ მოხერხდა. "
                "თანხა არ ჩამოჭრილა."
            ),
            code=CARD_PAYMENT_START_FAILED_CODE,
            payment=payment,
        )


@dataclass(frozen=True)
class PreparedCardPayment:
    payment: PaymentTransaction
    created: bool


@dataclass(frozen=True)
class CardPaymentStartResult:
    payment: PaymentTransaction
    created: bool


def ensure_card_payments_enabled():
    if not settings.BOG_PAYMENTS_ENABLED:
        raise CardPaymentsDisabled()


def start_cart_card_payment(
    *,
    cart,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key,
    owner_fingerprint,
    request_fingerprint,
    marketing_consent=False,
    marketing_context=None,
    client=None,
):
    ensure_card_payments_enabled()
    prepared = _prepare_cart_card_payment(
        cart=cart,
        user=user,
        validated_data=validated_data,
        terms_acceptance=terms_acceptance,
        idempotency_key=idempotency_key,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
        marketing_consent=marketing_consent,
        marketing_context=marketing_context,
    )
    payment = _start_prepared_bog_payment(
        prepared.payment,
        client=client,
    )
    return CardPaymentStartResult(
        payment=payment,
        created=prepared.created,
    )


def start_buy_now_card_payment(
    *,
    session,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key,
    owner_fingerprint,
    request_fingerprint,
    marketing_consent=False,
    marketing_context=None,
    client=None,
):
    ensure_card_payments_enabled()
    prepared = _prepare_buy_now_card_payment(
        session=session,
        user=user,
        validated_data=validated_data,
        terms_acceptance=terms_acceptance,
        idempotency_key=idempotency_key,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
        marketing_consent=marketing_consent,
        marketing_context=marketing_context,
    )
    payment = _start_prepared_bog_payment(
        prepared.payment,
        client=client,
    )
    return CardPaymentStartResult(
        payment=payment,
        created=prepared.created,
    )


@transaction.atomic
def _prepare_cart_card_payment(
    *,
    cart,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key,
    owner_fingerprint,
    request_fingerprint,
    marketing_consent,
    marketing_context,
):
    checkout_attempt = lock_checkout_attempt(
        idempotency_key=idempotency_key,
        source=OrderCheckoutSource.CART,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
    existing_payment = _get_existing_payment(idempotency_key)
    if existing_payment is not None:
        return PreparedCardPayment(payment=existing_payment, created=False)
    if checkout_attempt and checkout_attempt.order_id:
        raise CardPaymentStartFailed(payment=None)

    owner_filter = _reservation_owner_filter(
        user=user,
        guest_token=locked_cart.guest_token,
    )
    product_ids = list(
        locked_cart.items.select_for_update().values_list(
            "product_id",
            flat=True,
        )
    )
    _raise_if_unresolved_payment_exists(
        source=OrderCheckoutSource.CART,
        owner_filter=owner_filter,
        product_ids=product_ids,
    )

    reservation = create_stock_reservation_from_cart(
        cart=locked_cart,
        user=user,
        guest_token=locked_cart.guest_token,
        ttl_seconds=settings.BOG_STOCK_RESERVATION_TTL_SECONDS,
    )
    cart_item_ids = {
        item.product_id: item.pk
        for item in locked_cart.items.select_for_update().order_by("id")
    }
    return _create_prepared_payment(
        reservation=reservation,
        source=OrderCheckoutSource.CART,
        source_reference={
            "cart_id": locked_cart.pk,
            "cart_item_ids": cart_item_ids,
        },
        user=user,
        validated_data=validated_data,
        terms_acceptance=terms_acceptance,
        idempotency_key=idempotency_key,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
        marketing_consent=marketing_consent,
        marketing_context=marketing_context,
    )


@transaction.atomic
def _prepare_buy_now_card_payment(
    *,
    session,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key,
    owner_fingerprint,
    request_fingerprint,
    marketing_consent,
    marketing_context,
):
    checkout_attempt = lock_checkout_attempt(
        idempotency_key=idempotency_key,
        source=OrderCheckoutSource.BUY_NOW,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    locked_session = (
        BuyNowSession.objects.select_for_update()
        .select_related("product")
        .get(pk=session.pk)
    )
    existing_payment = _get_existing_payment(idempotency_key)
    if existing_payment is not None:
        return PreparedCardPayment(payment=existing_payment, created=False)
    if checkout_attempt and checkout_attempt.order_id:
        raise CardPaymentStartFailed(payment=None)

    owner_filter = _reservation_owner_filter(
        user=user if user is not None else locked_session.user,
        guest_token=locked_session.guest_token,
    )
    _raise_if_unresolved_payment_exists(
        source=OrderCheckoutSource.BUY_NOW,
        owner_filter=owner_filter,
        product_ids=[locked_session.product_id],
    )

    try:
        reservation = create_stock_reservation_from_buy_now_session(
            session=locked_session,
            user=user,
            guest_token=locked_session.guest_token,
            ttl_seconds=settings.BOG_STOCK_RESERVATION_TTL_SECONDS,
        )
    except StockReservationError as error:
        available_quantity = 0
        if error.issues:
            available_quantity = int(
                error.issues[0].get("available_quantity", 0)
            )
        issues = build_buy_now_session_issues(
            session=locked_session,
            product=locked_session.product,
            available_quantity=available_quantity,
        )
        raise build_buy_now_conflict_error(issues) from error
    return _create_prepared_payment(
        reservation=reservation,
        source=OrderCheckoutSource.BUY_NOW,
        source_reference={
            "buy_now_session_id": locked_session.pk,
        },
        user=user,
        validated_data=validated_data,
        terms_acceptance=terms_acceptance,
        idempotency_key=idempotency_key,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
        marketing_consent=marketing_consent,
        marketing_context=marketing_context,
    )


def _create_prepared_payment(
    *,
    reservation,
    source,
    source_reference,
    user,
    validated_data,
    terms_acceptance,
    idempotency_key,
    owner_fingerprint,
    request_fingerprint,
    marketing_consent,
    marketing_context,
):
    provider_expires_at = timezone.now() + timedelta(
        minutes=settings.BOG_ORDER_TTL_MINUTES
    )
    snapshot = _build_checkout_snapshot(
        reservation=reservation,
        source=source,
        source_reference=source_reference,
        user=user,
        validated_data=validated_data,
        terms_acceptance=terms_acceptance,
        owner_fingerprint=owner_fingerprint,
        request_fingerprint=request_fingerprint,
        provider_expires_at=provider_expires_at,
        marketing_consent=marketing_consent,
        marketing_context=marketing_context,
    )
    payment = create_payment_transaction(
        reservation=reservation,
        amount=Decimal(snapshot["totals"]["total"]),
        provider=PaymentProvider.BOG,
        payment_method=OrderPaymentMethod.CARD,
        action=PaymentTransactionAction.SALE,
        status=PaymentTransactionStatus.PENDING,
        currency="GEL",
        idempotency_key=idempotency_key,
        checkout_snapshot=snapshot,
        expires_at=reservation.expires_at,
    )
    return PreparedCardPayment(payment=payment, created=True)


def _start_prepared_bog_payment(payment, *, client=None):
    payment = PaymentTransaction.objects.select_related(
        "reservation",
        "order",
    ).get(pk=payment.pk)
    if payment.status == PaymentTransactionStatus.FAILED:
        raise CardPaymentStartFailed(payment)
    if payment.status != PaymentTransactionStatus.PENDING:
        return payment
    if payment.provider_order_id and payment.redirect_url:
        return payment
    if _provider_order_has_expired(payment):
        raise CardPaymentStartPending(payment, retryable=False)

    snapshot = payment.checkout_snapshot
    try:
        payment_client = client or BogPaymentsClient.from_settings()
        result = payment_client.create_order(
            callback_url=settings.BOG_CALLBACK_PUBLIC_URL,
            success_url=_payment_result_url(
                settings.BOG_FRONTEND_SUCCESS_URL,
                payment.public_token,
            ),
            fail_url=_payment_result_url(
                settings.BOG_FRONTEND_FAIL_URL,
                payment.public_token,
            ),
            external_order_id=f"FD-{payment.public_token}",
            basket=[
                {
                    "product_id": item["provider_product_id"],
                    "description": item["product_name"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                }
                for item in snapshot["items"]
            ],
            total_amount=snapshot["totals"]["total"],
            delivery_amount=snapshot["totals"]["delivery"],
            idempotency_key=payment.idempotency_key,
            ttl_minutes=settings.BOG_ORDER_TTL_MINUTES,
        )
    except BogTransportError as error:
        payment = _record_start_pending(payment, error)
        raise CardPaymentStartPending(payment) from error
    except BogAuthenticationError as error:
        if error.retryable:
            payment = _record_start_pending(payment, error)
            raise CardPaymentStartPending(payment) from error
        payment = _record_start_failure(payment, error)
        raise CardPaymentStartFailed(payment) from error
    except BogResponseError as error:
        if error.retryable:
            payment = _record_start_pending(payment, error)
            raise CardPaymentStartPending(payment) from error
        payment = _record_start_failure(payment, error)
        raise CardPaymentStartFailed(payment) from error
    except (BogConfigurationError, BogValidationError) as error:
        payment = _record_start_failure(payment, error)
        raise CardPaymentStartFailed(payment) from error
    except BogPaymentError as error:
        payment = _record_start_pending(payment, error)
        raise CardPaymentStartPending(payment) from error

    return _record_bog_order_created(payment, result)


@transaction.atomic
def _record_bog_order_created(payment, result):
    locked_payment = PaymentTransaction.objects.select_for_update().get(
        pk=payment.pk
    )
    if locked_payment.status != PaymentTransactionStatus.PENDING:
        return locked_payment
    if (
        locked_payment.provider_order_id
        and locked_payment.provider_order_id != result.order_id
    ):
        raise CardPaymentStartPending(locked_payment, retryable=False)

    locked_payment.provider_order_id = result.order_id
    locked_payment.redirect_url = result.redirect_url
    locked_payment.provider_reference = result.provider_reference
    locked_payment.error_code = ""
    locked_payment.error_message = ""
    locked_payment.save(
        update_fields=[
            "provider_order_id",
            "redirect_url",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return locked_payment


@transaction.atomic
def _record_start_pending(payment, error):
    locked_payment = PaymentTransaction.objects.select_for_update().get(
        pk=payment.pk
    )
    if locked_payment.status != PaymentTransactionStatus.PENDING:
        return locked_payment
    locked_payment.error_code = str(error.code or CARD_PAYMENT_START_PENDING_CODE)[:80]
    locked_payment.error_message = (
        "BOG order creation is pending safe retry or reconciliation."
    )
    locked_payment.save(
        update_fields=["error_code", "error_message", "updated_at"]
    )
    return locked_payment


@transaction.atomic
def _record_start_failure(payment, error):
    locked_payment = PaymentTransaction.objects.select_for_update().get(
        pk=payment.pk
    )
    if locked_payment.status != PaymentTransactionStatus.PENDING:
        return locked_payment

    now = timezone.now()
    locked_payment.status = PaymentTransactionStatus.FAILED
    locked_payment.error_code = str(error.code or CARD_PAYMENT_START_FAILED_CODE)[:80]
    locked_payment.error_message = "BOG order creation was rejected."
    locked_payment.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    reservation = (
        StockReservation.objects.select_for_update()
        .filter(pk=locked_payment.reservation_id)
        .first()
    )
    _release_reservation(reservation, now=now)
    return locked_payment


def get_public_card_payment(public_token):
    return (
        PaymentTransaction.objects.select_related("order")
        .filter(
            public_token=public_token,
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
        )
        .first()
    )


def get_provider_order_expires_at(payment):
    raw_value = (payment.checkout_snapshot or {}).get(
        "provider_order_expires_at"
    )
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def can_retry_card_payment_start(payment):
    provider_expires_at = get_provider_order_expires_at(payment)
    return (
        payment.status == PaymentTransactionStatus.PENDING
        and not payment.redirect_url
        and provider_expires_at is not None
        and provider_expires_at > timezone.now()
    )


def can_redirect_to_bog(payment):
    provider_expires_at = get_provider_order_expires_at(payment)
    return (
        payment.status == PaymentTransactionStatus.PENDING
        and bool(payment.redirect_url)
        and provider_expires_at is not None
        and provider_expires_at > timezone.now()
    )


def get_public_payment_result(payment):
    if (
        payment.status == PaymentTransactionStatus.PENDING
        and _provider_order_has_expired(payment)
    ):
        return "verification_pending"
    return payment.status


def is_checkout_snapshot_intact(snapshot):
    if not isinstance(snapshot, dict):
        return False
    expected_hash = str(snapshot.get("integrity_hash") or "").strip()
    if not expected_hash:
        return False
    hash_payload = {
        key: value
        for key, value in snapshot.items()
        if key != "integrity_hash"
    }
    return _snapshot_hash(hash_payload) == expected_hash


def _build_checkout_snapshot(
    *,
    reservation,
    source,
    source_reference,
    user,
    validated_data,
    terms_acceptance,
    owner_fingerprint,
    request_fingerprint,
    provider_expires_at,
    marketing_consent,
    marketing_context,
):
    reservation_items = list(
        reservation.items.select_related("product", "product__category")
        .prefetch_related("product__images")
        .order_by("id")
    )
    items = []
    subtotal = Decimal("0.00")
    cart_item_ids = source_reference.get("cart_item_ids", {})
    persisted_source_reference = {
        key: value
        for key, value in source_reference.items()
        if key != "cart_item_ids"
    }

    for reservation_item in reservation_items:
        product = reservation_item.product
        line_total = (
            reservation_item.unit_price_snapshot * reservation_item.quantity
        )
        subtotal += line_total
        items.append(
            {
                "product_id": product.pk,
                "provider_product_id": str(product.sku or product.pk),
                "source_item_id": cart_item_ids.get(product.pk),
                "product_name": product.name,
                "sku": product.sku,
                "unit_price": _decimal_string(
                    reservation_item.unit_price_snapshot
                ),
                "quantity": reservation_item.quantity,
                "line_total": _decimal_string(line_total),
                "primary_image_snapshot": build_product_primary_image_snapshot(
                    product
                ),
            }
        )

    delivery_quote = resolve_checkout_delivery(
        validated_data=validated_data,
        source=source,
        items=reservation_items,
    )
    delivery_fields = delivery_order_fields(delivery_quote)
    delivery_price = delivery_fields["delivery_price"]
    terms_fields = terms_acceptance.to_order_fields()
    snapshot = {
        "version": CHECKOUT_SNAPSHOT_VERSION,
        "source": source,
        "source_reference": persisted_source_reference,
        "owner_fingerprint": owner_fingerprint,
        "request_fingerprint": request_fingerprint,
        "user_id": (
            user.pk
            if user is not None and getattr(user, "is_authenticated", True)
            else None
        ),
        "buyer": {
            "buyer_type": validated_data.get("buyer_type", "individual"),
            "company_name": validated_data.get("company_name", ""),
            "company_identification_code": validated_data.get(
                "company_identification_code",
                "",
            ),
            "first_name": validated_data["first_name"],
            "last_name": validated_data["last_name"],
            "email": validated_data.get("email", ""),
            "phone": validated_data["phone"],
            "city": delivery_fields["delivery_city_name"],
            "address_line": validated_data["address_line"],
            "note": validated_data.get("note", ""),
        },
        "items": items,
        "delivery": delivery_quote,
        "totals": {
            "subtotal": _decimal_string(subtotal),
            "delivery": _decimal_string(delivery_price),
            "total": _decimal_string(subtotal + delivery_price),
            "currency": "GEL",
        },
        "terms": {
            "accepted_at": terms_fields["terms_accepted_at"].isoformat(),
            "version": terms_fields["terms_version"],
            "content_hash": terms_fields["terms_content_hash"],
            "content_snapshot": terms_fields["terms_content_snapshot"],
            "url": terms_fields["terms_url"],
            "ip_address": terms_fields["terms_ip_address"],
            "user_agent": terms_fields["terms_user_agent"],
        },
        "marketing": {
            "consent": bool(marketing_consent),
            "context": marketing_context or {},
        },
        "provider_order_expires_at": provider_expires_at.isoformat(),
        "reservation_expires_at": reservation.expires_at.isoformat(),
    }
    snapshot["integrity_hash"] = _snapshot_hash(snapshot)
    return snapshot


def _snapshot_hash(snapshot):
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decimal_string(value):
    return f"{Decimal(value):.2f}"


def _get_existing_payment(idempotency_key):
    payment = (
        PaymentTransaction.objects.select_for_update()
        .filter(idempotency_key=idempotency_key)
        .first()
    )
    if payment is None:
        return None
    if (
        payment.provider != PaymentProvider.BOG
        or payment.action != PaymentTransactionAction.SALE
    ):
        raise CardPaymentStartFailed(payment=None)
    return payment


def _reservation_owner_filter(*, user=None, guest_token=None):
    if user is not None and getattr(user, "is_authenticated", True):
        return {"reservation__user": user}
    if guest_token is not None:
        return {"reservation__guest_token": guest_token}
    raise ValueError("Card payment owner is required.")


def _raise_if_unresolved_payment_exists(*, source, owner_filter, product_ids=None):
    active_payment = (
        PaymentTransaction.objects.select_for_update()
        .filter(
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
            status=PaymentTransactionStatus.PENDING,
            reservation__source=source,
            **owner_filter,
        )
    )
    if product_ids is not None:
        normalized_product_ids = {
            int(product_id)
            for product_id in product_ids
            if product_id is not None
        }
        if not normalized_product_ids:
            return
        active_payment = active_payment.filter(
            reservation_id__in=StockReservationItem.objects.filter(
                product_id__in=normalized_product_ids,
            ).values("reservation_id"),
        )
    active_payment = active_payment.order_by("-created_at", "-pk").first()
    if active_payment is not None:
        raise ActiveCardPaymentExists(active_payment)


def _provider_order_has_expired(payment):
    provider_expires_at = get_provider_order_expires_at(payment)
    return (
        provider_expires_at is not None
        and provider_expires_at <= timezone.now()
    )


def _payment_result_url(base_url, payment_token):
    parsed = urlsplit(str(base_url))
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query = [
        (key, value)
        for key, value in query
        if key != "payment_token"
    ]
    query.append(("payment_token", str(payment_token)))
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def _release_reservation(reservation, *, now):
    if (
        reservation is None
        or reservation.status != StockReservationStatus.ACTIVE
    ):
        return
    StockReservation.objects.filter(
        pk=reservation.pk,
        status=StockReservationStatus.ACTIVE,
    ).update(
        status=StockReservationStatus.RELEASED,
        released_at=now,
        updated_at=now,
    )
