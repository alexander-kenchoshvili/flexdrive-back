"""Local Credo checkout lifecycle. No routes, credentials or bank calls here.

Observation application is for trusted server-side status reads only. A browser
return, chosen offer, local reservation timeout or operator-entered string is
never payment evidence. Cash receipts are deliberately outside this module.
"""

import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Product
from .accounting_snapshots import purchase_snapshot_fields
from .checkout_snapshots import build_checkout_snapshot, is_checkout_snapshot_intact, snapshot_hash
from .credo_status import CredoStatus, evaluate_credo_observation, parse_credo_status
from .delivery_quotes import delivery_order_fields
from .inventory import consume_order_inventory
from .models import (
    BuyNowSession, Cart, CartItem, CredoApplication, Order, OrderBuyerType,
    OrderCheckoutSource, OrderItem, OrderPaymentMethod, OrderPaymentStatus,
    OrderStatus, PaymentTransaction, StockReservation, StockReservationItem,
    StockReservationStatus,
)
from .services import (
    CheckoutIdempotencyConflict, StockReservationError, build_checkout_owner_fingerprint,
    build_checkout_request_fingerprint, build_order_number,
    create_stock_reservation_from_buy_now_session, create_stock_reservation_from_cart,
    ensure_no_active_online_payment, get_reserved_stock_quantities, lock_checkout_attempt,
    release_stock_reservation,
)


class CredoCheckoutError(Exception):
    def __init__(self, code):
        super().__init__("Credo checkout requires review.")
        self.code = code


@dataclass(frozen=True)
class PreparedCredoApplication:
    application: CredoApplication
    created: bool


def _validate_prepare_arguments(key, offer, merchant_id, ttl_seconds, is_test):
    if not isinstance(key, uuid.UUID) or key.version != 4:
        raise ValidationError({"idempotency_key": "A UUID v4 checkout key is required."})
    if offer not in CredoApplication.Offer.values:
        raise ValidationError({"requested_offer": "Unknown financing offer."})
    if not isinstance(merchant_id, str) or not re.fullmatch(r"[0-9]{1,64}", merchant_id) or int(merchant_id) < 1:
        raise CredoCheckoutError("credo_invalid_merchant_id")
    # Local stock policy is an explicit server argument, not a bank-expiry claim.
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 7 * 86400:
        raise CredoCheckoutError("credo_invalid_reservation_ttl")
    if type(is_test) is not bool:
        raise CredoCheckoutError("credo_invalid_test_flag")


def _request_fingerprint(source, validated_data, offer):
    base = build_checkout_request_fingerprint(
        source=source, validated_data={**validated_data, "payment_method": OrderPaymentMethod.CREDO},
    )
    return snapshot_hash({
        "checkout": base, "requested_offer": offer, "provider": "credo",
        "delivery_region_id": validated_data.get("delivery_region_id"),
        "delivery_city_id": validated_data.get("delivery_city_id"),
    })


def _check_owner(source_object, user):
    if source_object.user_id is not None and source_object.user_id != getattr(user, "pk", None):
        raise CheckoutIdempotencyConflict()
    return {"user": user, "guest_token": None} if user is not None else {
        "user": None, "guest_token": source_object.guest_token,
    }


def _lock_owner(user_id):
    if user_id is not None:
        # Serialize with account erasure before acquiring checkout/source locks.
        # NO KEY UPDATE still permits other providers' FK key-share checks.
        return get_user_model().objects.select_for_update(no_key=True).filter(pk=user_id).first()
    return None


def _existing_application(attempt, merchant_id, is_test):
    existing = CredoApplication.objects.select_for_update().filter(checkout_attempt=attempt).first()
    if existing is not None:
        if existing.merchant_id != merchant_id or existing.is_test != is_test:
            raise CheckoutIdempotencyConflict()
        return PreparedCredoApplication(existing, False)
    if attempt.order_id or PaymentTransaction.objects.filter(idempotency_key=attempt.key).exists():
        raise CheckoutIdempotencyConflict()
    return None


@transaction.atomic
def prepare_cart_credo_application(
    *, cart, user, validated_data, terms_acceptance, idempotency_key,
    requested_offer, merchant_id, reservation_ttl_seconds,
    marketing_consent=False, marketing_context=None, is_test=False,
):
    _validate_prepare_arguments(idempotency_key, requested_offer, merchant_id, reservation_ttl_seconds, is_test)
    owner = _check_owner(cart, user)
    if user is not None and _lock_owner(user.pk) is None:
        raise CheckoutIdempotencyConflict()
    attempt = lock_checkout_attempt(
        idempotency_key=idempotency_key, source=OrderCheckoutSource.CART,
        owner_fingerprint=build_checkout_owner_fingerprint(**owner),
        request_fingerprint=_request_fingerprint(OrderCheckoutSource.CART, validated_data, requested_offer),
    )
    existing = _existing_application(attempt, merchant_id, is_test)
    if existing is not None:
        if existing.application.checkout_snapshot.get("source_reference", {}).get("cart_id") != cart.pk:
            raise CheckoutIdempotencyConflict()
        return existing
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    owner = _check_owner(cart, user)
    if build_checkout_owner_fingerprint(**owner) != attempt.owner_fingerprint:
        raise CheckoutIdempotencyConflict()
    cart_items = list(cart.items.select_for_update().order_by("id"))
    ensure_no_active_online_payment(
        source=OrderCheckoutSource.CART, owner_kwargs=owner,
        product_ids=[item.product_id for item in cart_items],
    )
    reservation = create_stock_reservation_from_cart(
        cart=cart, **owner, ttl_seconds=reservation_ttl_seconds,
    )
    return _create_application(
        attempt=attempt, reservation=reservation, user=user, validated_data=validated_data,
        source_reference={"cart_id": cart.pk, "cart_item_ids": {item.product_id: item.pk for item in cart_items}},
        terms_acceptance=terms_acceptance, requested_offer=requested_offer,
        merchant_id=merchant_id, marketing_consent=marketing_consent,
        marketing_context=marketing_context, is_test=is_test,
    )


@transaction.atomic
def prepare_buy_now_credo_application(
    *, session, user, validated_data, terms_acceptance, idempotency_key,
    requested_offer, merchant_id, reservation_ttl_seconds,
    marketing_consent=False, marketing_context=None, is_test=False,
):
    _validate_prepare_arguments(idempotency_key, requested_offer, merchant_id, reservation_ttl_seconds, is_test)
    owner = _check_owner(session, user)
    if user is not None and _lock_owner(user.pk) is None:
        raise CheckoutIdempotencyConflict()
    attempt = lock_checkout_attempt(
        idempotency_key=idempotency_key, source=OrderCheckoutSource.BUY_NOW,
        owner_fingerprint=build_checkout_owner_fingerprint(**owner),
        request_fingerprint=_request_fingerprint(OrderCheckoutSource.BUY_NOW, validated_data, requested_offer),
    )
    existing = _existing_application(attempt, merchant_id, is_test)
    if existing is not None:
        if existing.application.checkout_snapshot.get("source_reference", {}).get("buy_now_session_id") != session.pk:
            raise CheckoutIdempotencyConflict()
        return existing
    session = BuyNowSession.objects.select_for_update().get(pk=session.pk)
    owner = _check_owner(session, user)
    if build_checkout_owner_fingerprint(**owner) != attempt.owner_fingerprint:
        raise CheckoutIdempotencyConflict()
    ensure_no_active_online_payment(
        source=OrderCheckoutSource.BUY_NOW, owner_kwargs=owner, product_ids=[session.product_id],
    )
    reservation = create_stock_reservation_from_buy_now_session(
        session=session, **owner, ttl_seconds=reservation_ttl_seconds,
    )
    return _create_application(
        attempt=attempt, reservation=reservation, user=user, validated_data=validated_data,
        source_reference={"buy_now_session_id": session.pk}, terms_acceptance=terms_acceptance,
        requested_offer=requested_offer, merchant_id=merchant_id,
        marketing_consent=marketing_consent, marketing_context=marketing_context, is_test=is_test,
    )


def _create_application(
    *, attempt, reservation, user, validated_data, source_reference, terms_acceptance,
    requested_offer, merchant_id, marketing_consent, marketing_context, is_test,
):
    snapshot = build_checkout_snapshot(
        reservation=reservation, source=attempt.source, source_reference=source_reference,
        user=user, validated_data=validated_data, terms_acceptance=terms_acceptance,
        owner_fingerprint=attempt.owner_fingerprint, request_fingerprint=attempt.request_fingerprint,
        provider_expires_at=None, marketing_consent=marketing_consent and not is_test,
        marketing_context={} if is_test else marketing_context,
    )
    snapshot.pop("integrity_hash")
    snapshot["financing"] = {
        "provider": "credo", "merchant_id": merchant_id, "requested_offer": requested_offer, "is_test": is_test,
        "fee_payer": "merchant", "merchant_fee_rate": "0.0300", "customer_surcharge": "0.00",
    }
    snapshot["integrity_hash"] = snapshot_hash(snapshot)
    application = CredoApplication(
        checkout_attempt=attempt, reservation=reservation, merchant_id=merchant_id,
        order_code="FD" + attempt.key.hex, requested_offer=requested_offer,
        requested_amount=Decimal(snapshot["totals"]["total"]), currency="GEL",
        checkout_snapshot=snapshot, snapshot_digest=snapshot["integrity_hash"], is_test=is_test,
    )
    application.full_clean()
    application.save()
    return PreparedCredoApplication(application, True)


@transaction.atomic
def apply_credo_observation(application_id, observed_status, *, check_token=None):
    """Apply a trusted bank read atomically. Never call with browser evidence."""
    stub = CredoApplication.objects.only("checkout_attempt_id", "reservation_id", "checkout_snapshot").get(pk=application_id)
    owner_id = StockReservation.objects.filter(pk=stub.reservation_id).values_list("user_id", flat=True).first()
    _lock_owner(owner_id)
    # Match preparation's lock order: owner, checkout attempt, source, application,
    # hold, then products. Do not lock nullable joined relations on PostgreSQL.
    from .models import CheckoutAttempt
    attempt = CheckoutAttempt.objects.select_for_update().get(pk=stub.checkout_attempt_id)
    _lock_source(stub.checkout_snapshot)
    application = CredoApplication.objects.select_for_update().get(pk=application_id)
    if check_token is not None and application.bank_check_token != check_token:
        raise CredoCheckoutError("credo_stale_status_read")
    if check_token is None:
        # An explicit newer read supersedes an outstanding background response.
        application.bank_check_token = None
        application.bank_check_lock_until = None
    reservation = StockReservation.objects.select_for_update().get(pk=application.reservation_id)
    now = timezone.now()
    application.bank_checked_at = now
    try:
        observed = parse_credo_status(observed_status)
    except ValueError:
        application.last_observed_status = observed_status if type(observed_status) is int and -(2**31) <= observed_status < 2**31 else None
        application.needs_review = True
        application.last_issue = "credo_unknown_application_status"
        application.save()
        return application
    prior_issue = application.last_issue if application.needs_review else ""
    decision = evaluate_credo_observation(
        application.bank_status, observed, review_required=application.needs_review,
    )
    application.last_observed_status = observed
    application.bank_status = decision.effective_status
    application.needs_review = decision.requires_review
    application.last_issue = prior_issue or decision.issue
    application.submission_state = CredoApplication.SubmissionState.SUBMITTED
    if not decision.requires_review:
        if observed == CredoStatus.SIGNED and application.signed_at is None:
            application.signed_at = now
        if observed == CredoStatus.COMPLETED and application.funding_completed_at is None:
            application.funding_completed_at = now
        if decision.fulfillment_allowed:
            try:
                with transaction.atomic():
                    application.order = _create_order(application, attempt, reservation)
            except (CredoCheckoutError, DjangoValidationError, IntegrityError) as error:
                application.needs_review = True
                application.last_issue = error.code if isinstance(error, CredoCheckoutError) else "credo_fulfillment_blocked"
            except (KeyError, ValueError, TypeError, InvalidOperation):
                application.needs_review = True
                application.last_issue = "credo_snapshot_invalid"
        elif observed in (CredoStatus.REJECTED, CredoStatus.CANCELLED):
            if application.order_id:
                application.needs_review = True
                application.last_issue = "credo_order_cancellation_requires_review"
            else:
                release_stock_reservation(reservation)
    from .credo_finance import queue_credo_purchase
    queue_credo_purchase(application)
    application.save()
    return application


def _lock_source(snapshot):
    reference = snapshot.get("source_reference", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(reference, dict):
        return
    for model, field in ((Cart, "cart_id"), (BuyNowSession, "buy_now_session_id")):
        source_id = reference.get(field)
        if type(source_id) is int:
            model.objects.select_for_update().filter(pk=source_id).first()


def _money(value):
    try:
        if isinstance(value, (float, bool)):
            raise ValueError
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
            raise ValueError
        return amount
    except (ValueError, TypeError, InvalidOperation):
        raise CredoCheckoutError("credo_snapshot_amount_invalid") from None


def _normalized_items(snapshot):
    raw_items = snapshot.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise CredoCheckoutError("credo_snapshot_items_invalid")
    items, seen = [], set()
    for item in raw_items:
        if not isinstance(item, dict):
            raise CredoCheckoutError("credo_snapshot_items_invalid")
        product_id, quantity = item.get("product_id"), item.get("quantity")
        if type(product_id) is not int or product_id < 1 or product_id in seen or type(quantity) is not int or quantity < 1:
            raise CredoCheckoutError("credo_snapshot_items_invalid")
        price, total = _money(item.get("unit_price")), _money(item.get("line_total"))
        if total != price * quantity:
            raise CredoCheckoutError("credo_snapshot_items_invalid")
        seen.add(product_id)
        items.append({**item, "unit_price": price, "line_total": total})
    return items


def _create_order(application, attempt, reservation):
    snapshot = application.checkout_snapshot
    if (not is_checkout_snapshot_intact(snapshot)
            or not hmac.compare_digest(snapshot.get("integrity_hash", ""), application.snapshot_digest)):
        raise CredoCheckoutError("credo_snapshot_integrity_failed")
    if (snapshot.get("version") != 1 or snapshot.get("source") != attempt.source
            or reservation.source != attempt.source or snapshot.get("user_id") != reservation.user_id
            or snapshot.get("owner_fingerprint") != attempt.owner_fingerprint
            or snapshot.get("request_fingerprint") != attempt.request_fingerprint):
        raise CredoCheckoutError("credo_checkout_context_mismatch")
    if snapshot.get("financing") != {
        "provider": "credo", "merchant_id": application.merchant_id,
        "requested_offer": application.requested_offer, "is_test": application.is_test,
        "fee_payer": "merchant", "merchant_fee_rate": format(application.merchant_fee_rate, ".4f"), "customer_surcharge": "0.00",
    }:
        raise CredoCheckoutError("credo_financing_context_mismatch")
    if not isinstance(snapshot.get("source_reference"), dict):
        raise CredoCheckoutError("credo_snapshot_source_invalid")
    total, subtotal, delivery = (_money(snapshot["totals"][key]) for key in ("total", "subtotal", "delivery"))
    if (snapshot["totals"].get("currency") != "GEL" or application.currency != "GEL"
            or total != application.requested_amount or subtotal + delivery != total):
        raise CredoCheckoutError("credo_snapshot_total_mismatch")
    if attempt.order_id or application.order_id:
        if (attempt.order_id == reservation.completed_order_id
                and application.order_id in (None, attempt.order_id)
                and reservation.status == StockReservationStatus.COMPLETED):
            order = Order.objects.select_for_update().get(pk=attempt.order_id)
            if order.payment_method == OrderPaymentMethod.CREDO and order.total == total:
                return order
        raise CredoCheckoutError("credo_checkout_order_conflict")
    if reservation.status == StockReservationStatus.COMPLETED:
        raise CredoCheckoutError("credo_reservation_order_conflict")
    items = _normalized_items(snapshot)
    if sum((item["line_total"] for item in items), Decimal("0.00")) != subtotal:
        raise CredoCheckoutError("credo_snapshot_items_total_mismatch")
    holds = list(reservation.items.select_for_update().order_by("product_id"))
    expected = {item["product_id"]: (item["quantity"], item["unit_price"]) for item in items}
    if {item.product_id: (item.quantity, item.unit_price_snapshot) for item in holds} != expected:
        raise CredoCheckoutError("credo_reservation_snapshot_mismatch")
    products = {product.pk: product for product in Product.objects.select_for_update().filter(pk__in=expected).order_by("pk")}
    others = get_reserved_stock_quantities(product_ids=expected, exclude_reservation_ids=[reservation.pk])
    if set(products) != set(expected) or any(
        products[pk].customer_available_stock_qty - others.get(pk, 0) < quantity
        for pk, (quantity, _) in expected.items()
    ):
        raise CredoCheckoutError("credo_stock_unavailable")
    buyer, terms = snapshot["buyer"], snapshot["terms"]
    accepted_at = datetime.fromisoformat(terms["accepted_at"])
    if timezone.is_naive(accepted_at):
        raise CredoCheckoutError("credo_snapshot_terms_invalid")
    buyer_type = OrderBuyerType(buyer["buyer_type"])
    delivery_fields = delivery_order_fields(snapshot["delivery"])
    if delivery_fields["delivery_price"] != delivery:
        raise CredoCheckoutError("credo_snapshot_delivery_mismatch")
    marketing = snapshot.get("marketing") or {}
    order = Order.objects.create(
        user_id=reservation.user_id, checkout_source=attempt.source, buyer_type=buyer_type,
        payment_method=OrderPaymentMethod.CREDO, payment_status=OrderPaymentStatus.PENDING,
        status=OrderStatus.NEW, subtotal=subtotal, total=total,
        first_name=buyer["first_name"], last_name=buyer["last_name"], email=buyer.get("email", ""),
        phone=buyer["phone"], city=buyer["city"], address_line=buyer["address_line"], note=buyer.get("note", ""),
        personal_number=buyer.get("personal_number", "") if buyer_type == OrderBuyerType.INDIVIDUAL else "",
        company_name=buyer.get("company_name", ""), company_identification_code=buyer.get("company_identification_code", ""),
        company_is_vat_registered=buyer.get("company_is_vat_registered"),
        terms_accepted_at=accepted_at, terms_version=terms.get("version", ""),
        terms_content_hash=terms.get("content_hash", ""), terms_content_snapshot=terms.get("content_snapshot", {}),
        terms_url=terms.get("url", ""), terms_ip_address=terms.get("ip_address"),
        terms_user_agent=terms.get("user_agent", ""), marketing_consent=bool(marketing.get("consent")) and not application.is_test,
        marketing_context={} if application.is_test else marketing.get("context", {}), **delivery_fields,
    )
    order.order_number = build_order_number(order)
    order.save(update_fields=["order_number", "updated_at"])
    OrderItem.objects.bulk_create([
        OrderItem(order=order, product=products[item["product_id"]], product_name=item["product_name"],
                  sku=item.get("sku", ""), internal_sku=item.get("internal_sku", ""),
                  unit_price=item["unit_price"], quantity=item["quantity"], line_total=item["line_total"],
                  primary_image_snapshot=item.get("primary_image_snapshot", {}),
                  **purchase_snapshot_fields(item.get("accounting")))
        for item in items
    ])
    consume_order_inventory(order=order)
    reservation.status = StockReservationStatus.COMPLETED
    reservation.completed_order = order
    reservation.completed_at = timezone.now()
    reservation.released_at = None
    reservation.save(update_fields=["status", "completed_order", "completed_at", "released_at", "updated_at"])
    attempt.order = order
    attempt.save(update_fields=["order", "updated_at"])
    _consume_source(snapshot, items)
    return order


def _consume_source(snapshot, items):
    reference = snapshot["source_reference"]
    if snapshot["source"] == OrderCheckoutSource.CART:
        for item in items:
            row = CartItem.objects.select_for_update().filter(
                pk=item.get("source_item_id"), cart_id=reference.get("cart_id"), product_id=item["product_id"],
            ).first()
            if row is not None:
                if row.quantity <= item["quantity"]:
                    row.delete()
                else:
                    row.quantity -= item["quantity"]
                    row.save(update_fields=["quantity", "updated_at"])
    elif len(items) == 1:
        item = items[0]
        BuyNowSession.objects.filter(pk=reference.get("buy_now_session_id"), product_id=item["product_id"],
                                     quantity=item["quantity"], unit_price_snapshot=item["unit_price"]).delete()
