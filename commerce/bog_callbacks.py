import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from catalog.models import Product

from .bog_payments import (
    BOG_CAPTURE_MODE,
    BOG_CURRENCY,
    BOG_PAYMENT_METHOD,
    BogPaymentDetails,
    BogPaymentsClient,
    BogResponseError,
    parse_bog_payment_details,
)
from .card_payments import is_checkout_snapshot_intact
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
)
from .services import build_order_number, transition_order_payment_status


BOG_CALLBACK_EVENT = "order_payment"
BOG_PENDING_STATUSES = frozenset({"created", "processing"})
BOG_MANUAL_CAPTURE_STATUSES = frozenset(
    {"auth_requested", "blocked", "partial_completed"}
)
BOG_SUCCESS_STATUS = "completed"
BOG_FAILURE_STATUS = "rejected"


class BogCallbackError(Exception):
    def __init__(self, *, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class BogCallbackSignatureError(BogCallbackError):
    pass


class BogCallbackPayloadError(BogCallbackError):
    pass


class BogCallbackConflict(BogCallbackError):
    pass


class BogFulfillmentError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BogCallback:
    event: str
    zoned_request_time: str
    details: BogPaymentDetails
    source: str = "callback"


@dataclass(frozen=True)
class BogCallbackResult:
    payment: PaymentTransaction
    order: Order | None
    result: str


def verify_bog_callback_signature(
    raw_body,
    signature,
    *,
    public_key_pem=None,
):
    if not isinstance(raw_body, bytes) or not raw_body:
        raise BogCallbackSignatureError(
            code="bog_callback_body_missing",
            message="Callback body is required.",
        )
    normalized_signature = str(signature or "").strip()
    if not normalized_signature or len(normalized_signature) > 4096:
        raise BogCallbackSignatureError(
            code="bog_callback_signature_missing",
            message="Callback signature is required.",
            status_code=401,
        )

    try:
        decoded_signature = base64.b64decode(
            normalized_signature,
            validate=True,
        )
    except (ValueError, binascii.Error) as error:
        raise BogCallbackSignatureError(
            code="bog_callback_signature_invalid",
            message="Callback signature is invalid.",
            status_code=401,
        ) from error

    key_text = str(
        public_key_pem
        if public_key_pem is not None
        else settings.BOG_CALLBACK_PUBLIC_KEY
    ).replace("\\n", "\n").strip()
    try:
        public_key = _load_rsa_public_key(key_text)
        public_key.verify(
            decoded_signature,
            raw_body,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as error:
        raise BogCallbackSignatureError(
            code="bog_callback_signature_invalid",
            message="Callback signature is invalid.",
            status_code=401,
        ) from error
    except (TypeError, ValueError) as error:
        raise BogCallbackSignatureError(
            code="bog_callback_public_key_invalid",
            message="Callback verification is unavailable.",
            status_code=503,
        ) from error


@lru_cache(maxsize=4)
def _load_rsa_public_key(public_key_pem):
    key = serialization.load_pem_public_key(
        public_key_pem.encode("ascii")
    )
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("BOG callback key must be an RSA public key.")
    return key


def parse_bog_callback(raw_body):
    try:
        decoded_body = raw_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BogCallbackPayloadError(
            code="bog_callback_invalid_encoding",
            message="Callback body must be UTF-8 JSON.",
        ) from error

    try:
        payload = json.loads(
            decoded_body,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (TypeError, ValueError) as error:
        raise BogCallbackPayloadError(
            code="bog_callback_invalid_json",
            message="Callback body is invalid JSON.",
        ) from error
    if not isinstance(payload, dict):
        raise BogCallbackPayloadError(
            code="bog_callback_invalid_payload",
            message="Callback payload must be an object.",
        )

    event = str(payload.get("event") or "").strip()
    if event != BOG_CALLBACK_EVENT:
        raise BogCallbackPayloadError(
            code="bog_callback_event_invalid",
            message="Unsupported callback event.",
        )
    zoned_request_time = str(
        payload.get("zoned_request_time") or ""
    ).strip()
    if not zoned_request_time:
        raise BogCallbackPayloadError(
            code="bog_callback_time_missing",
            message="Callback time is required.",
        )
    try:
        datetime.fromisoformat(
            zoned_request_time.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise BogCallbackPayloadError(
            code="bog_callback_time_invalid",
            message="Callback time is invalid.",
        ) from error
    body = payload.get("body")
    if not isinstance(body, dict):
        raise BogCallbackPayloadError(
            code="bog_callback_details_missing",
            message="Callback payment details are required.",
        )

    try:
        details = parse_bog_payment_details(body)
    except BogResponseError as error:
        raise BogCallbackPayloadError(
            code=error.code,
            message="Callback payment details are invalid.",
        ) from error
    return BogCallback(
        event=event,
        zoned_request_time=zoned_request_time,
        details=details,
    )


def reconcile_bog_payment(payment, *, client=None):
    current_payment = PaymentTransaction.objects.get(pk=payment.pk)
    if not current_payment.provider_order_id:
        raise BogCallbackConflict(
            code="bog_reconciliation_provider_order_missing",
            message="Payment has no provider order ID.",
            status_code=409,
        )
    payment_client = client or BogPaymentsClient.from_settings()
    details = payment_client.get_payment_details(
        current_payment.provider_order_id
    )
    evidence = BogCallback(
        event=BOG_CALLBACK_EVENT,
        zoned_request_time=timezone.now().isoformat(),
        details=details,
        source="payment_details",
    )
    return apply_bog_callback(evidence)


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


@transaction.atomic
def apply_bog_callback(callback):
    payment = _lock_callback_payment(callback.details)
    _validate_callback_details(payment, callback.details)
    _bind_provider_order_id(payment, callback.details.order_id)

    from .bog_refunds import has_bog_refund_activity

    if has_bog_refund_activity(callback.details):
        return _apply_refund_reconciliation(payment, callback)
    if callback.details.status == BOG_SUCCESS_STATUS:
        return _apply_completed_callback(payment, callback)
    if callback.details.status == BOG_FAILURE_STATUS:
        return _apply_rejected_callback(payment, callback)
    if callback.details.status in BOG_PENDING_STATUSES:
        return _apply_pending_callback(payment, callback)

    return _apply_reconciliation_status(payment, callback)


def _lock_callback_payment(details):
    payments = list(
        PaymentTransaction.objects.select_for_update()
        .filter(
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
            provider_order_id=details.order_id,
        )
        .order_by("pk")[:2]
    )
    if len(payments) > 1:
        raise BogCallbackConflict(
            code="bog_callback_provider_order_ambiguous",
            message="Provider order matches multiple payments.",
            status_code=409,
        )
    if payments:
        return payments[0]

    payment_token = _payment_token_from_external_order_id(
        details.external_order_id
    )
    if payment_token is None:
        raise BogCallbackConflict(
            code="bog_callback_payment_not_found",
            message="Payment attempt was not found.",
            status_code=404,
        )
    payment = (
        PaymentTransaction.objects.select_for_update()
        .filter(
            public_token=payment_token,
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
        )
        .first()
    )
    if payment is None:
        raise BogCallbackConflict(
            code="bog_callback_payment_not_found",
            message="Payment attempt was not found.",
            status_code=404,
        )
    return payment


def _payment_token_from_external_order_id(external_order_id):
    prefix = "FD-"
    if not str(external_order_id).startswith(prefix):
        return None
    try:
        return uuid.UUID(str(external_order_id)[len(prefix):])
    except (TypeError, ValueError):
        return None


def _validate_callback_details(payment, details):
    expected_external_order_id = f"FD-{payment.public_token}"
    if details.external_order_id != expected_external_order_id:
        raise BogCallbackConflict(
            code="bog_callback_external_order_mismatch",
            message="Callback external order does not match.",
            status_code=409,
        )
    if payment.provider_order_id and payment.provider_order_id != details.order_id:
        raise BogCallbackConflict(
            code="bog_callback_provider_order_mismatch",
            message="Callback provider order does not match.",
            status_code=409,
        )
    if details.industry and details.industry != "ecommerce":
        raise BogCallbackConflict(
            code="bog_callback_industry_mismatch",
            message="Callback industry does not match.",
            status_code=409,
        )
    if details.capture != BOG_CAPTURE_MODE:
        raise BogCallbackConflict(
            code="bog_callback_capture_mismatch",
            message="Callback capture mode does not match.",
            status_code=409,
        )
    if details.request_amount != payment.amount:
        raise BogCallbackConflict(
            code="bog_callback_amount_mismatch",
            message="Callback amount does not match.",
            status_code=409,
        )
    if details.currency != payment.currency or details.currency != BOG_CURRENCY:
        raise BogCallbackConflict(
            code="bog_callback_currency_mismatch",
            message="Callback currency does not match.",
            status_code=409,
        )
    if (
        details.payment_method
        and details.payment_method != BOG_PAYMENT_METHOD
    ):
        raise BogCallbackConflict(
            code="bog_callback_payment_method_mismatch",
            message="Callback payment method does not match.",
            status_code=409,
        )
    if details.refund_amount > payment.amount:
        raise BogCallbackConflict(
            code="bog_callback_refund_amount_exceeded",
            message="Callback refund amount exceeds the payment.",
            status_code=409,
        )
    if details.payment_option and details.payment_option != "direct_debit":
        raise BogCallbackConflict(
            code="bog_callback_payment_option_mismatch",
            message="Callback payment option does not match.",
            status_code=409,
        )

    if details.status == BOG_SUCCESS_STATUS:
        if details.payment_method != BOG_PAYMENT_METHOD:
            raise BogCallbackConflict(
                code="bog_callback_payment_method_missing",
                message="Completed card payment method is missing.",
                status_code=409,
            )
        if details.transfer_amount != payment.amount:
            raise BogCallbackConflict(
                code="bog_callback_transfer_amount_mismatch",
                message="Callback transferred amount does not match.",
                status_code=409,
            )
        if not details.transaction_id:
            raise BogCallbackConflict(
                code="bog_callback_transaction_id_missing",
                message="Completed payment transaction ID is missing.",
                status_code=409,
            )
        duplicate = (
            PaymentTransaction.objects.select_for_update()
            .filter(
                provider=PaymentProvider.BOG,
                provider_transaction_id=details.transaction_id,
            )
            .exclude(pk=payment.pk)
            .exists()
        )
        if duplicate:
            raise BogCallbackConflict(
                code="bog_callback_transaction_id_duplicate",
                message="Provider transaction ID is already in use.",
                status_code=409,
            )


def _bind_provider_order_id(payment, provider_order_id):
    if payment.provider_order_id == provider_order_id:
        return
    payment.provider_order_id = provider_order_id
    payment.save(update_fields=["provider_order_id", "updated_at"])


def _apply_completed_callback(payment, callback):
    if payment.status == PaymentTransactionStatus.REFUNDED:
        return BogCallbackResult(
            payment=payment,
            order=payment.order,
            result="ignored_after_refund",
        )
    if (
        payment.status == PaymentTransactionStatus.PAID
        and payment.order_id
    ):
        _update_payment_provider_evidence(
            payment,
            callback,
            clear_error=True,
        )
        return BogCallbackResult(
            payment=payment,
            order=payment.order,
            result="already_completed",
        )
    if payment.status == PaymentTransactionStatus.PAID:
        _update_payment_provider_evidence(payment, callback)
        return BogCallbackResult(
            payment=payment,
            order=None,
            result="paid_fulfillment_blocked",
        )

    if _has_newer_unresolved_or_successful_attempt(payment):
        _mark_paid_fulfillment_blocked(
            payment,
            callback,
            code="paid_older_attempt_requires_refund",
        )
        return BogCallbackResult(
            payment=payment,
            order=None,
            result="paid_fulfillment_blocked",
        )

    try:
        with transaction.atomic():
            order = _create_order_from_paid_snapshot(payment)
    except BogFulfillmentError as error:
        _mark_paid_fulfillment_blocked(
            payment,
            callback,
            code=error.code,
        )
        return BogCallbackResult(
            payment=payment,
            order=None,
            result="paid_fulfillment_blocked",
        )
    except IntegrityError:
        _mark_paid_fulfillment_blocked(
            payment,
            callback,
            code="paid_order_integrity_error",
        )
        return BogCallbackResult(
            payment=payment,
            order=None,
            result="paid_fulfillment_blocked",
        )

    now = timezone.now()
    payment.order = order
    payment.status = PaymentTransactionStatus.PAID
    payment.provider_transaction_id = callback.details.transaction_id
    payment.provider_reference = _callback_provider_reference(callback)
    payment.error_code = ""
    payment.error_message = ""
    payment.captured_at = now
    payment.save(
        update_fields=[
            "order",
            "status",
            "provider_transaction_id",
            "provider_reference",
            "error_code",
            "error_message",
            "captured_at",
            "updated_at",
        ]
    )
    transition_order_payment_status(order, OrderPaymentStatus.PAID)
    return BogCallbackResult(
        payment=payment,
        order=order,
        result="completed",
    )


def _create_order_from_paid_snapshot(payment):
    snapshot = payment.checkout_snapshot
    if not is_checkout_snapshot_intact(snapshot):
        raise BogFulfillmentError("paid_snapshot_integrity_failed")
    if snapshot.get("version") != 1:
        raise BogFulfillmentError("paid_snapshot_version_unsupported")
    if snapshot.get("owner_fingerprint") is None:
        raise BogFulfillmentError("paid_snapshot_owner_missing")

    try:
        source = OrderCheckoutSource(snapshot["source"])
        buyer_type = OrderBuyerType(snapshot["buyer"]["buyer_type"])
        total = _snapshot_money(snapshot["totals"]["total"])
        subtotal = _snapshot_money(snapshot["totals"]["subtotal"])
        currency = str(snapshot["totals"]["currency"]).upper()
        terms_accepted_at = _snapshot_datetime(
            snapshot["terms"]["accepted_at"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BogFulfillmentError("paid_snapshot_invalid") from error
    if total != payment.amount or subtotal != total or currency != "GEL":
        raise BogFulfillmentError("paid_snapshot_total_mismatch")

    reservation = (
        StockReservation.objects.select_for_update()
        .filter(pk=payment.reservation_id)
        .first()
    )
    if reservation is None or reservation.source != source:
        raise BogFulfillmentError("paid_reservation_missing")
    if snapshot.get("user_id") != reservation.user_id:
        raise BogFulfillmentError("paid_snapshot_owner_mismatch")

    checkout_attempt = (
        CheckoutAttempt.objects.select_for_update()
        .filter(key=payment.idempotency_key)
        .first()
    )
    if (
        checkout_attempt is None
        or checkout_attempt.source != source
        or checkout_attempt.owner_fingerprint
        != snapshot.get("owner_fingerprint")
        or checkout_attempt.request_fingerprint
        != snapshot.get("request_fingerprint")
    ):
        raise BogFulfillmentError("paid_checkout_attempt_mismatch")
    if checkout_attempt.order_id:
        existing_order = checkout_attempt.order
        if (
            payment.order_id in {None, existing_order.pk}
            and existing_order.payment_method == OrderPaymentMethod.CARD
            and existing_order.total == payment.amount
        ):
            return existing_order
        raise BogFulfillmentError("paid_checkout_order_conflict")

    item_snapshots = snapshot.get("items")
    if not isinstance(item_snapshots, list) or not item_snapshots:
        raise BogFulfillmentError("paid_snapshot_items_missing")
    normalized_items = _normalize_snapshot_items(item_snapshots)
    if sum(
        (item["line_total"] for item in normalized_items),
        Decimal("0.00"),
    ) != total:
        raise BogFulfillmentError("paid_snapshot_item_total_mismatch")
    expected_quantities = {
        item["product_id"]: item["quantity"]
        for item in normalized_items
    }
    expected_prices = {
        item["product_id"]: item["unit_price"]
        for item in normalized_items
    }
    reservation_items = list(
        StockReservationItem.objects.select_for_update()
        .filter(reservation=reservation)
        .order_by("product_id")
    )
    if (
        {
            item.product_id: item.quantity
            for item in reservation_items
        }
        != expected_quantities
        or {
            item.product_id: item.unit_price_snapshot
            for item in reservation_items
        }
        != expected_prices
    ):
        raise BogFulfillmentError("paid_reservation_snapshot_mismatch")

    product_ids = sorted(expected_quantities)
    products = list(
        Product.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    )
    if [product.pk for product in products] != product_ids:
        raise BogFulfillmentError("paid_product_missing")
    products_by_id = {product.pk: product for product in products}

    other_reserved = {
        row["product_id"]: row["quantity"] or 0
        for row in (
            StockReservationItem.objects.filter(
                product_id__in=product_ids,
                reservation__status=StockReservationStatus.ACTIVE,
                reservation__expires_at__gt=timezone.now(),
            )
            .exclude(reservation=reservation)
            .values("product_id")
            .annotate(quantity=Sum("quantity"))
        )
    }
    for product_id, required_quantity in expected_quantities.items():
        available_quantity = (
            products_by_id[product_id].stock_qty
            - other_reserved.get(product_id, 0)
        )
        if available_quantity < required_quantity:
            raise BogFulfillmentError("paid_stock_unavailable")

    buyer = snapshot["buyer"]
    terms = snapshot["terms"]
    marketing = snapshot.get("marketing") or {}
    order = Order.objects.create(
        user_id=reservation.user_id,
        checkout_source=source,
        buyer_type=buyer_type,
        company_name=str(buyer.get("company_name") or ""),
        company_identification_code=str(
            buyer.get("company_identification_code") or ""
        ),
        payment_method=OrderPaymentMethod.CARD,
        payment_status=OrderPaymentStatus.PENDING,
        status=OrderStatus.NEW,
        subtotal=subtotal,
        total=total,
        first_name=str(buyer["first_name"]),
        last_name=str(buyer["last_name"]),
        email=str(buyer.get("email") or ""),
        phone=str(buyer["phone"]),
        city=str(buyer["city"]),
        address_line=str(buyer["address_line"]),
        note=str(buyer.get("note") or ""),
        terms_accepted_at=terms_accepted_at,
        terms_version=str(terms.get("version") or ""),
        terms_content_hash=str(terms.get("content_hash") or ""),
        terms_content_snapshot=terms.get("content_snapshot") or {},
        terms_url=str(terms.get("url") or ""),
        terms_ip_address=terms.get("ip_address") or None,
        terms_user_agent=str(terms.get("user_agent") or ""),
        marketing_consent=bool(marketing.get("consent")),
        marketing_context=marketing.get("context") or {},
    )
    order.order_number = build_order_number(order)
    order.save(update_fields=["order_number", "updated_at"])

    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=products_by_id[item["product_id"]],
                product_name=item["product_name"],
                sku=item["sku"],
                unit_price=item["unit_price"],
                quantity=item["quantity"],
                line_total=item["line_total"],
                primary_image_snapshot=item["primary_image_snapshot"],
            )
            for item in normalized_items
        ]
    )
    now = timezone.now()
    for product in products:
        product.stock_qty -= expected_quantities[product.pk]
        product.updated_at = now
    Product.objects.bulk_update(products, ["stock_qty", "updated_at"])

    reservation.status = StockReservationStatus.COMPLETED
    reservation.completed_order = order
    reservation.completed_at = now
    reservation.released_at = None
    reservation.save(
        update_fields=[
            "status",
            "completed_order",
            "completed_at",
            "released_at",
            "updated_at",
        ]
    )
    checkout_attempt.order = order
    checkout_attempt.save(update_fields=["order", "updated_at"])
    _consume_paid_checkout_source(snapshot, normalized_items)
    return order


def _normalize_snapshot_items(item_snapshots):
    normalized_items = []
    seen_product_ids = set()
    calculated_total = Decimal("0.00")
    for item in item_snapshots:
        if not isinstance(item, dict):
            raise BogFulfillmentError("paid_snapshot_item_invalid")
        try:
            product_id = int(item["product_id"])
            quantity = int(item["quantity"])
            unit_price = _snapshot_money(item["unit_price"])
            line_total = _snapshot_money(item["line_total"])
        except (KeyError, TypeError, ValueError) as error:
            raise BogFulfillmentError("paid_snapshot_item_invalid") from error
        if (
            product_id <= 0
            or quantity <= 0
            or product_id in seen_product_ids
            or line_total != unit_price * quantity
        ):
            raise BogFulfillmentError("paid_snapshot_item_invalid")
        seen_product_ids.add(product_id)
        calculated_total += line_total
        normalized_items.append(
            {
                "product_id": product_id,
                "source_item_id": item.get("source_item_id"),
                "product_name": str(item.get("product_name") or ""),
                "sku": str(item.get("sku") or ""),
                "unit_price": unit_price,
                "quantity": quantity,
                "line_total": line_total,
                "primary_image_snapshot": (
                    item.get("primary_image_snapshot") or {}
                ),
            }
        )
    if calculated_total <= Decimal("0.00"):
        raise BogFulfillmentError("paid_snapshot_item_total_invalid")
    return normalized_items


def _snapshot_money(value):
    try:
        raw_amount = Decimal(str(value))
        amount = raw_amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Invalid snapshot amount.") from error
    if (
        not amount.is_finite()
        or raw_amount != amount
        or amount < Decimal("0.00")
    ):
        raise ValueError("Invalid snapshot amount.")
    return amount


def _snapshot_datetime(value):
    parsed = datetime.fromisoformat(str(value))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(
            parsed,
            timezone.get_current_timezone(),
        )
    return parsed


def _consume_paid_checkout_source(snapshot, normalized_items):
    source = snapshot["source"]
    source_reference = snapshot.get("source_reference") or {}
    if source == OrderCheckoutSource.CART:
        cart_id = source_reference.get("cart_id")
        if not cart_id:
            return
        cart = Cart.objects.select_for_update().filter(pk=cart_id).first()
        if cart is None:
            return
        for item in normalized_items:
            source_item_id = item.get("source_item_id")
            if not source_item_id:
                continue
            cart_item = (
                CartItem.objects.select_for_update()
                .filter(
                    pk=source_item_id,
                    cart=cart,
                    product_id=item["product_id"],
                )
                .first()
            )
            if cart_item is None:
                continue
            if cart_item.quantity <= item["quantity"]:
                cart_item.delete()
            else:
                cart_item.quantity -= item["quantity"]
                cart_item.save(
                    update_fields=["quantity", "updated_at"]
                )
        return

    if source == OrderCheckoutSource.BUY_NOW:
        session_id = source_reference.get("buy_now_session_id")
        if not session_id or len(normalized_items) != 1:
            return
        item = normalized_items[0]
        session = (
            BuyNowSession.objects.select_for_update()
            .filter(
                pk=session_id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                unit_price_snapshot=item["unit_price"],
            )
            .first()
        )
        if session is not None:
            session.delete()


def _apply_rejected_callback(payment, callback):
    if payment.status in {
        PaymentTransactionStatus.PAID,
        PaymentTransactionStatus.REFUND_PENDING,
        PaymentTransactionStatus.REFUNDED,
    } or payment.order_id:
        _update_payment_provider_evidence(payment, callback)
        return BogCallbackResult(
            payment=payment,
            order=payment.order,
            result="late_rejection_ignored",
        )

    now = timezone.now()
    payment.status = PaymentTransactionStatus.FAILED
    payment.provider_reference = _callback_provider_reference(callback)
    payment.error_code = (
        _safe_error_code(
            callback.details.response_code,
            fallback="bog_payment_rejected",
        )
        if callback.details.response_code
        else "bog_payment_rejected"
    )
    payment.error_message = "BOG card payment was rejected."
    payment.save(
        update_fields=[
            "status",
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    reservation = (
        StockReservation.objects.select_for_update()
        .filter(pk=payment.reservation_id)
        .first()
    )
    if (
        reservation is not None
        and reservation.status == StockReservationStatus.ACTIVE
    ):
        reservation.status = StockReservationStatus.RELEASED
        reservation.released_at = now
        reservation.save(
            update_fields=["status", "released_at", "updated_at"]
        )
    return BogCallbackResult(
        payment=payment,
        order=None,
        result="rejected",
    )


def _apply_pending_callback(payment, callback):
    if payment.status != PaymentTransactionStatus.PENDING:
        return BogCallbackResult(
            payment=payment,
            order=payment.order,
            result="pending_status_ignored",
        )
    payment.provider_reference = _callback_provider_reference(callback)
    payment.error_code = ""
    payment.error_message = ""
    payment.save(
        update_fields=[
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return BogCallbackResult(
        payment=payment,
        order=None,
        result="pending",
    )


def _apply_reconciliation_status(payment, callback):
    payment.provider_reference = _callback_provider_reference(callback)
    status_key = callback.details.status
    if status_key in BOG_MANUAL_CAPTURE_STATUSES:
        error_code = "bog_unexpected_manual_capture_status"
    else:
        error_code = "bog_unknown_status_requires_reconciliation"
    payment.error_code = error_code
    payment.error_message = (
        "BOG status requires manual or scheduled reconciliation."
    )
    payment.save(
        update_fields=[
            "provider_reference",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    return BogCallbackResult(
        payment=payment,
        order=payment.order,
        result="reconciliation_required",
    )


def _apply_refund_reconciliation(payment, callback):
    from .bog_refunds import reconcile_bog_refund_details

    try:
        refund_result = reconcile_bog_refund_details(
            payment,
            callback.details,
            provider_reference=_callback_provider_reference(callback),
        )
    except DjangoValidationError:
        payment.provider_reference = _callback_provider_reference(callback)
        payment.error_code = "bog_refund_requires_manual_reconciliation"
        payment.error_message = (
            "BOG reported refund activity that cannot be safely matched to "
            "the current local sale/refund state."
        )
        payment.save(
            update_fields=[
                "provider_reference",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return BogCallbackResult(
            payment=payment,
            order=payment.order,
            result="refund_reconciliation_required",
        )
    return BogCallbackResult(
        payment=payment,
        order=refund_result.order,
        result=refund_result.result,
    )


def _update_payment_provider_evidence(
    payment,
    callback,
    *,
    clear_error=False,
):
    payment.provider_reference = _callback_provider_reference(callback)
    update_fields = ["provider_reference", "updated_at"]
    if clear_error:
        payment.error_code = ""
        payment.error_message = ""
        update_fields.extend(["error_code", "error_message"])
    payment.save(update_fields=update_fields)


def _mark_paid_fulfillment_blocked(payment, callback, *, code):
    now = timezone.now()
    payment.status = PaymentTransactionStatus.PAID
    payment.provider_transaction_id = callback.details.transaction_id
    payment.provider_reference = _callback_provider_reference(callback)
    payment.error_code = code[:80]
    payment.error_message = (
        "Payment completed but order fulfillment requires staff action "
        "and a provider refund."
    )
    payment.captured_at = now
    payment.save(
        update_fields=[
            "status",
            "provider_transaction_id",
            "provider_reference",
            "error_code",
            "error_message",
            "captured_at",
            "updated_at",
        ]
    )
    reservation = (
        StockReservation.objects.select_for_update()
        .filter(pk=payment.reservation_id)
        .first()
    )
    if (
        reservation is not None
        and reservation.status == StockReservationStatus.ACTIVE
    ):
        reservation.status = StockReservationStatus.RELEASED
        reservation.released_at = now
        reservation.save(
            update_fields=["status", "released_at", "updated_at"]
        )


def _has_newer_unresolved_or_successful_attempt(payment):
    reservation = (
        StockReservation.objects.select_for_update()
        .filter(pk=payment.reservation_id)
        .first()
    )
    if reservation is None:
        return True
    owner_filter = {}
    if reservation.user_id:
        owner_filter["reservation__user_id"] = reservation.user_id
    elif reservation.guest_token:
        owner_filter["reservation__guest_token"] = reservation.guest_token
    else:
        return True
    return (
        PaymentTransaction.objects.select_for_update()
        .filter(
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
            reservation__source=reservation.source,
            status__in={
                PaymentTransactionStatus.PENDING,
                PaymentTransactionStatus.AUTHORIZED,
                PaymentTransactionStatus.PAID,
                PaymentTransactionStatus.REFUND_PENDING,
                PaymentTransactionStatus.REFUNDED,
            },
            **owner_filter,
        )
        .filter(
            Q(created_at__gt=payment.created_at)
            | Q(
                created_at=payment.created_at,
                pk__gt=payment.pk,
            )
        )
        .exclude(pk=payment.pk)
        .exists()
    )


def _callback_provider_reference(callback):
    return {
        "source": callback.source,
        "event": callback.event,
        "zoned_request_time": callback.zoned_request_time,
        "details": callback.details.provider_reference,
    }


def _safe_error_code(value, *, fallback):
    normalized = "".join(
        character
        for character in str(value or "").strip().lower()
        if character.isalnum() or character in {"_", "-"}
    )
    return f"bog_{normalized[:60]}" if normalized else fallback
