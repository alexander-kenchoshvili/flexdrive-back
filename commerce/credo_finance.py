"""Merchant-paid Credo fees, explicit cash evidence, and financing purchases.

The 3% forecast uses the full financed total with cent rounding; it is not proof
of a bank debit, tax treatment or net cash receipt. Actuals require a statement.
"""
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid5
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CredoApplication, CredoStatementSettlement, Order, PaymentTransaction

FEE_RATE = Decimal("0.0300")
CENT = Decimal("0.01")
TBILISI = ZoneInfo("Asia/Tbilisi")


def expected_credo_amounts(application):
    gross = application.requested_amount
    fee = (gross * application.merchant_fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"gross": gross, "fee": fee, "net": gross-fee}


def is_credo_purchase_eligible(order):
    if order.payment_method != "credo" or order.status == "cancelled" or order.stock_restored_at:
        return False
    return CredoApplication.objects.filter(
        order=order, checkout_attempt__order=order, reservation__completed_order=order,
        reservation__status="completed", bank_status=5, funding_completed_at__isnull=False,
        needs_review=False, is_test=False,
    ).exists()


def queue_credo_purchase(application):
    # Called under the application's lifecycle lock, only after valid order creation.
    if (application.purchase_queued_at or not application.order_id or application.bank_status != 5
            or application.is_test or application.needs_review or not application.order.marketing_consent):
        return
    if not (settings.META_CAPI_ENABLED and settings.META_PIXEL_ID and settings.META_CAPI_ACCESS_TOKEN):
        return
    application.purchase_queued_at = timezone.now()
    application_id = application.pk

    def dispatch():
        current = CredoApplication.objects.select_related("order").get(pk=application_id)
        if current.order_id and is_credo_purchase_eligible(current.order) and current.order.marketing_consent:
            from . import services
            services.send_meta_purchase_event(order=current.order)
    transaction.on_commit(dispatch)


def _money(value):
    try:
        if isinstance(value, (float, bool)):
            raise ValueError
        value = Decimal(value)
        if not value.is_finite() or value < 0 or value > Decimal("9999999999.99") or value != value.quantize(CENT):
            raise ValueError
        return value
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError("თანხა მიუთითეთ ლარში, მაქსიმუმ ორი ათწილადით.") from None


@transaction.atomic
def confirm_credo_statement(*, application_id, fee_amount, net_amount, received_on, statement_reference, actor, confirmed=False):
    if (not actor or not actor.is_active or not actor.is_staff
            or not actor.has_perm("commerce.add_credostatementsettlement")):
        raise PermissionDenied
    if confirmed is not True:
        raise ValidationError("დაადასტურეთ საბანკო ამონაწერთან გადამოწმება.")
    fee, net = _money(fee_amount), _money(net_amount)
    if type(received_on) is not date or received_on > timezone.localdate(timezone=TBILISI):
        raise ValidationError("მიუთითეთ ამონაწერის რეალური თარიღი; მომავალი თარიღი დაუშვებელია.")
    if not isinstance(statement_reference, str) or not statement_reference.strip() or len(statement_reference) > 120:
        raise ValidationError("მიუთითეთ ამონაწერის ჩანაწერის მითითება, პირადი ნომრის გარეშე.")
    # Match the lifecycle's owner -> attempt -> application -> order lock ordering.
    from .credo_checkout import _lock_owner
    from .models import CheckoutAttempt, StockReservation
    stub = CredoApplication.objects.get(pk=application_id)
    owner_id = StockReservation.objects.filter(pk=stub.reservation_id).values_list("user_id", flat=True).first()
    _lock_owner(owner_id)
    CheckoutAttempt.objects.select_for_update().get(pk=stub.checkout_attempt_id)
    application = CredoApplication.objects.select_for_update().get(pk=application_id)
    existing = CredoStatementSettlement.objects.filter(application=application).first()
    if existing:
        if (existing.fee_amount, existing.net_amount, existing.received_on, existing.statement_reference) != (fee, net, received_on, statement_reference.strip()):
            raise ValidationError("ამ განაცხადის ჩარიცხვა უკვე სხვა მონაცემებითაა დადასტურებული.")
        return existing
    if not application.order_id or application.needs_review or application.is_test or application.bank_status != 5:
        raise ValidationError("საჭიროა დასრულებული, უპრობლემო რეალური დაფინანსება და დაკავშირებული შეკვეთა.")
    order = Order.objects.select_for_update().get(pk=application.order_id)
    if not is_credo_purchase_eligible(order) or order.payment_status != "pending" or net <= 0 or fee+net != application.requested_amount or order.total != application.requested_amount:
        raise ValidationError("ამონაწერის თანხები ან შეკვეთის მდგომარეობა შესაჯერებელია.")
    if received_on < application.created_at.astimezone(TBILISI).date() or (application.signed_at and received_on < application.signed_at.astimezone(TBILISI).date()):
        raise ValidationError("ჩარიცხვა ხელმოწერამდე ვერ დაფიქსირდება.")
    if order.payment_transactions.exists():
        raise ValidationError("ამ შეკვეთაზე უკვე არსებობს ფინანსური მოძრაობა; საჭიროა გადამოწმება.")
    # Bank statement supplies a calendar date, not a bank timestamp. This is a
    # normalized Tbilisi day boundary, marked date-only in every display/export.
    cash_date = datetime.combine(received_on, time.min, TBILISI)
    payment = PaymentTransaction.objects.create(
        idempotency_key=uuid5(application.public_token, "credo-statement"), order=order,
        reservation=application.reservation, provider="credo", payment_method="credo", action="sale", status="paid",
        amount=application.requested_amount, currency="GEL", provider_order_id=application.order_code,
        captured_at=cash_date, provider_reference={"kind": "statement_confirmed", "date_precision": "date"},
    )
    settlement = CredoStatementSettlement.objects.create(
        application=application, payment=payment, gross_amount=application.requested_amount,
        fee_amount=fee, net_amount=net, received_on=received_on,
        statement_reference=statement_reference.strip(), confirmed_by=actor,
    )
    order.payment_status = "paid"
    order.save(update_fields=["payment_status", "updated_at"])
    return settlement


def credo_financing_report(period, search=""):
    lower, upper = period.bounds
    qs = CredoApplication.objects.filter(created_at__gte=lower, created_at__lt=upper, is_test=False,
        order__isnull=False).select_related("order", "statement_settlement").order_by("created_at", "pk")
    if search:
        qs = qs.filter(Q(order__items__internal_sku__icontains=search) | Q(order__items__product_name__icontains=search)
                       | Q(order__items__sku__icontains=search)).distinct()
    from .accounting_reports import _bounded, MAX_REPORT_ROWS
    rows = []
    for app in _bounded(qs, MAX_REPORT_ROWS):
        expected = expected_credo_amounts(app)
        settlement = getattr(app, "statement_settlement", None)
        rows.append({"created_at": app.created_at, "order_number": app.order.order_number,
            "order_code": app.order_code, "offer": app.get_requested_offer_display(),
            "gross": expected["gross"], "expected_fee": expected["fee"], "expected_net": expected["net"],
            "bank_completed": app.bank_status == 5, "needs_review": app.needs_review,
            "actual_fee": settlement.fee_amount if settlement else None,
            "actual_net": settlement.net_amount if settlement else None,
            "received_on": settlement.received_on if settlement else None})
    return {"rows": rows, "expected_fee": sum((r["expected_fee"] for r in rows), Decimal(0)),
            "pending_expected_net": sum((r["expected_net"] for r in rows if r["actual_net"] is None), Decimal(0)),
            "confirmed_net": sum((r["actual_net"] for r in rows if r["actual_net"] is not None), Decimal(0))}
