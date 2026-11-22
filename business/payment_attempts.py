"""Private, read-only payment explanations from existing saved facts, never click tracking."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import re

from django.db.models import Q

from commerce.models import PaymentTransaction

WINDOW = timedelta(hours=24)
MAX_CANDIDATES = 400
MAX_HISTORY = 12
DELIVERY_LABELS = {"fast": "სწრაფი მიტანა", "standard": "სტანდარტული მიტანა"}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
        if number.is_finite() and 0 <= number <= Decimal("9999999999.99") and number == number.quantize(Decimal("0.01")):
            return format(number, ".2f")
    except (InvalidOperation, ValueError):
        pass
    return None


def checkout_summary(payment):
    snapshot = _dict(payment.checkout_snapshot)
    totals = _dict(snapshot.get("totals"))
    values = {key: _amount(totals.get(key)) for key in ("subtotal", "delivery", "total")}
    if (any(value is None for value in values.values()) or totals.get("currency") != payment.currency
            or values["total"] != _amount(payment.amount)
            or Decimal(values["subtotal"]) + Decimal(values["delivery"]) != Decimal(values["total"])):
        return None
    service = _dict(snapshot.get("delivery")).get("service_slug")
    service = service if isinstance(service, str) else None
    return {**values, "service": service if service in DELIVERY_LABELS else None,
            "service_label": DELIVERY_LABELS.get(service, "მიტანის ტიპი არ არის შენახული")}


def failure_reason(payment):
    if payment.status != "failed":
        return None
    details = _dict(_dict(payment.provider_reference).get("details"))
    code = str(_dict(details.get("payment_detail")).get("code") or "")
    code = code if re.fullmatch(r"[0-9]{1,6}", code) else None
    rejected = _dict(details.get("order_status")).get("key") == "rejected"
    reason = details.get("reject_reason")
    # Never return free-form provider errors, card details or unknown error text.
    if rejected and code == "108" and reason == "Authentication Declined":
        return {"kind": "authentication_declined", "code": code,
                "label": "ბანკის ავთენტიფიკაცია არ დადასტურდა",
                "detail": "ბანკის პასუხია Authentication Declined. კონკრეტული SMS-ის, აპის ან სხვა შემოწმების მიზეზი ამ პასუხით არ განისაზღვრება."}
    if rejected and code == "109":
        return {"kind": "bank_technical", "code": code,
                "label": "ბანკმა ტექნიკური შეცდომა დააფიქსირა",
                "detail": "ბანკის პასუხში დაფიქსირდა ტექნიკური ხარვეზი."}
    if rejected and (reason == "expiration" or code == "110"):
        return {"kind": "expired", "code": code, "label": "ბანკში გადახდის ვადა ამოიწურა",
                "detail": "ბანკის შენახული პასუხია expiration; ეს ბარათის მოქმედების ვადის გასვლას არ ადასტურებს."}
    if rejected:
        return {"kind": "bank_rejected", "code": code, "label": "ბანკმა გადახდა უარყო",
                "detail": "კონკრეტული მიზეზის განმარტება ამ ანგარიშში არ არის. საჭიროებისას გადაამოწმეთ ბანკთან."}
    if not payment.provider_order_id:
        return {"kind": "start_unconfirmed", "code": None, "label": "გადახდის დაწყება ვერ დადასტურდა",
                "detail": "ბანკის გადახდის ჩანაწერი არ არის მიბმული; ეს მომხმარებლის ბარათის უარყოფას თავისთავად არ ადასტურებს."}
    return {"kind": "unknown", "code": None, "label": "წარუმატებლობის მიზეზი არ არის დადასტურებული",
            "detail": "ბანკის შესაბამისი პასუხი ან მიზეზი ამ ანგარიშისთვის არ არის შენახული."}


def _identity(payment, *, max_items=100):
    if payment.provider != "bog" or payment.action != "sale" or payment.currency != "GEL":
        return None
    snapshot = _dict(payment.checkout_snapshot)
    owner = snapshot.get("owner_fingerprint")
    source = snapshot.get("source")
    reference_key = "cart_id" if source == "cart" else "buy_now_session_id"
    reference = _dict(snapshot.get("source_reference")).get(reference_key)
    items = snapshot.get("items")
    summary = checkout_summary(payment)
    if (not isinstance(owner, str) or not re.fullmatch(r"[a-f0-9]{64}", owner)
            or not isinstance(source, str) or source not in {"cart", "buy_now"} or not isinstance(items, list)
            or type(reference) is not int or reference <= 0 or not items
            or (max_items is not None and len(items) > max_items) or summary is None):
        return None
    basket, subtotal = [], Decimal(0)
    for raw_item in items:
        item = _dict(raw_item)
        product, quantity, price = item.get("product_id"), item.get("quantity"), _amount(item.get("unit_price"))
        if (type(product) is not int or product <= 0 or type(quantity) is not int
                or not 1 <= quantity <= 10000 or price is None):
            return None
        basket.append((product, quantity, price))
        subtotal += Decimal(price) * quantity
    if subtotal != Decimal(summary["subtotal"]):
        return None
    return owner, source, reference, tuple(sorted(basket)), payment.currency


def _entry(payment, labels):
    return {"id": payment.pk, "status": payment.status,
            "status_label": labels.get(payment.status, "მდგომარეობა უცნობია"),
            "amount": format(payment.amount, ".2f"), "currency": payment.currency,
            "created_at": payment.created_at.isoformat(), "updated_at": payment.updated_at.isoformat(),
            "confirmed_at": payment.captured_at.isoformat() if payment.captured_at else None,
            "order_number": payment.order.order_number if payment.order_id else None,
            "settlement_label": (labels.get(payment.order.payment_status)
                if payment.order_id and payment.order.payment_status in {"refunded", "partially_refunded", "refund_pending"} else None),
            "checkout": checkout_summary(payment), "failure": failure_reason(payment)}


def payment_contexts(payments, labels):
    """One bounded related-record query per report page; identities stay server-side."""
    eligible = [payment for payment in payments if payment.provider == "bog" and payment.action == "sale"]
    contexts = {payment.pk: {"checkout": checkout_summary(payment), "failure": failure_reason(payment),
        "bank_order_created": bool(payment.provider_order_id), "history": [], "history_limited": False,
        "match_basis": None, "later_success": None} for payment in eligible}
    identities = {payment.pk: identity for payment in eligible if (identity := _identity(payment)) is not None}
    if not identities:
        return contexts
    windows = Q()
    for payment in eligible:
        if payment.pk in identities:
            owner, source, reference, _, _ = identities[payment.pk]
            reference_key = "cart_id" if source == "cart" else "buy_now_session_id"
            windows |= Q(checkout_snapshot__owner_fingerprint=owner, checkout_snapshot__source=source,
                         created_at__gte=payment.created_at - WINDOW, created_at__lte=payment.created_at + WINDOW,
                         **{f"checkout_snapshot__source_reference__{reference_key}": reference})
    candidates = list(PaymentTransaction.objects.filter(windows, provider="bog", action="sale", currency="GEL")
        .select_related("order").only("id", "provider", "action", "status", "amount", "currency",
            "created_at", "updated_at", "captured_at", "provider_order_id", "provider_reference",
            "checkout_snapshot", "order_id", "order__order_number", "order__payment_status")
        .order_by("created_at", "pk")[:MAX_CANDIDATES + 1])
    limited = len(candidates) > MAX_CANDIDATES
    candidates = candidates[:MAX_CANDIDATES]
    indexed = {}
    for candidate in candidates:
        identity = _identity(candidate)
        if identity is not None:
            indexed.setdefault(identity, {})[candidate.pk] = candidate
    for payment in eligible:
        identity = identities.get(payment.pk)
        if identity is None:
            continue
        matches = dict(indexed.get(identity, {}))
        matches[payment.pk] = payment
        related = sorted((row for row in matches.values() if abs(row.created_at - payment.created_at) <= WINDOW),
                         key=lambda row: (row.created_at, row.pk))
        later = next((row for row in related if (row.created_at, row.pk) > (payment.created_at, payment.pk)
                      and row.status == "paid" and row.order_id and row.captured_at), None)
        nearest = sorted(related, key=lambda row: (abs(row.created_at - payment.created_at), row.pk))[:MAX_HISTORY]
        if later and later not in nearest:
            nearest[-1] = later
        contexts[payment.pk].update(
            history=[_entry(row, labels) for row in sorted(nearest, key=lambda row: (row.created_at, row.pk))],
            history_limited=limited or len(related) > MAX_HISTORY,
            match_basis="same_checkout_and_basket_24h", later_success=_entry(later, labels) if later else None)
    return contexts
