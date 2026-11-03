"""One recorded return expense per case, independent of the bank refund outcome."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Q, Subquery

from .accounting_reports import MAX_REPORT_ROWS, _bounded, _search_orders
from .models import Order, OrderReturn, PaymentTransaction
from .refund_terms import settlement_for_refund


def return_cost_report(period, *, search=""):
    # The first frozen attempt is the expense record. Failed/unknown bank requests
    # retain it; retries cannot create another expense or move it to a later month.
    first = PaymentTransaction.objects.filter(order_id=OuterRef("order_id"), action="refund", provider="bog",
        provider_reference__refund_request__return_case_id__isnull=False,
        provider_reference__refund_request__settlement__kind="whole_order_return").order_by("created_at", "pk")
    lower, upper = period.bounds
    cases = OrderReturn.objects.filter(disposition="from_customer", receipt_status="received").annotate(
        cost_payment_id=Subquery(first.values("pk")[:1]), cost_recorded_at=Subquery(first.values("created_at")[:1]))
    cases = cases.filter(Q(cost_recorded_at__gte=lower, cost_recorded_at__lt=upper)
        | Q(cost_payment_id__isnull=True, received_at__gte=lower, received_at__lt=upper)).select_related("order").order_by("pk")
    if search:
        cases = cases.filter(order_id__in=_search_orders(Order.objects.all(), search).values("pk"))
    cases = _bounded(cases, MAX_REPORT_ROWS)
    payments = PaymentTransaction.objects.in_bulk([case.cost_payment_id for case in cases if case.cost_payment_id])
    rows, total, unknown = [], Decimal("0.00"), 0
    for case in cases:
        payment = payments.get(case.cost_payment_id)
        try:
            terms = settlement_for_refund(payment, total=case.order.total) if payment else None
        except ValidationError:
            terms = None
        if payment and payment.provider_reference.get("refund_request", {}).get("return_case_id") != case.pk:
            terms = None
        cost = Decimal(terms["return_delivery_cost"]) if terms else None
        total += cost or Decimal("0.00")
        unknown += int(cost is None)
        rows.append({"order_number": case.order.order_number, "recorded_at": case.cost_recorded_at or case.received_at,
            "cost": cost, "payment_status": case.order.payment_status,
            "payer": terms["return_delivery_payer"] if terms else None})
    return {"rows": rows, "known_total": total, "total": None if unknown else total, "unknown": unknown}
