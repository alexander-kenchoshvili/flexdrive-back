"""Private, read-only operational reports shared by future admin and XLSX views.

No tax recognition or deductibility is inferred. Order dates and cash event dates
are separate bases; their totals must never be added together as revenue.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Q, Exists, OuterRef, Prefetch

from .accounting_calculations import calculate_product_line
from .models import Order, OrderItem, OrderItemInventory, PaymentTransaction


TBILISI = ZoneInfo("Asia/Tbilisi")
ZERO = Decimal("0.00")
MAX_REPORT_ROWS = 10000
RECEIVED_STATUSES = ("paid", "refund_pending", "refunded")
RECEIPT_ACTIONS = ("sale", "capture")


@dataclass(frozen=True)
class ReportPeriod:
    start: date
    end: date

    def __post_init__(self):
        if type(self.start) is not date or type(self.end) is not date:
            raise ValueError("Report dates must be calendar dates.")
        if self.start > self.end or self.end == date.max:
            raise ValueError("Invalid report date range.")

    @property
    def bounds(self):
        return (
            datetime.combine(self.start, time.min, TBILISI).astimezone(timezone.utc),
            datetime.combine(self.end + timedelta(days=1), time.min, TBILISI).astimezone(timezone.utc),
        )

    @classmethod
    def months(cls, start, end):
        """Inclusive YYYY-MM month range, using the same day-range semantics."""
        try:
            first = datetime.strptime(start, "%Y-%m").date().replace(day=1)
            last = datetime.strptime(end, "%Y-%m").date().replace(day=1)
            if first.strftime("%Y-%m") != start or last.strftime("%Y-%m") != end:
                raise ValueError
            following = date(last.year + 1, 1, 1) if last.month == 12 else date(last.year, last.month + 1, 1)
            return cls(first, following - timedelta(days=1))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Use an ordered YYYY-MM month range.") from exc


def _dated(queryset, field, period):
    lower, upper = period.bounds
    return queryset.filter(**{field + "__gte": lower, field + "__lt": upper})


def _bounded(queryset, limit):
    if type(limit) is not int or not 1 <= limit <= MAX_REPORT_ROWS:
        raise ValueError("Invalid report row limit.")
    rows = list(queryset[:limit + 1])
    if len(rows) > limit:
        raise ValueError("Report is too large; select a shorter period.")
    return rows


def _search_orders(queryset, search):
    if search:
        queryset = queryset.filter(Q(order_number__icontains=search) | Q(items__internal_sku__icontains=search)
                                   | Q(items__sku__icontains=search) | Q(items__product_name__icontains=search)).distinct()
    return queryset


def order_queryset(period, search=""):
    receipts = PaymentTransaction.objects.filter(order_id=OuterRef("pk"), action__in=RECEIPT_ACTIONS,
                                                  status__in=RECEIVED_STATUSES, captured_at__isnull=False)
    refunds = PaymentTransaction.objects.filter(order_id=OuterRef("pk"), action="refund", status="refunded", refunded_at__isnull=False)
    orders = Order.objects.annotate(accounting_paid=Exists(receipts), accounting_refunded=Exists(refunds)).filter(
        Q(accounting_paid=True) | Q(accounting_refunded=True))
    return _search_orders(_dated(orders, "created_at", period), search).order_by("created_at", "pk").prefetch_related(
        Prefetch("items", queryset=OrderItem.objects.select_related("inventory")))


def event_queryset(period, search=""):
    lower, upper = period.bounds
    receipts = Q(action__in=RECEIPT_ACTIONS, status__in=RECEIVED_STATUSES,
                 captured_at__gte=lower, captured_at__lt=upper)
    refunds = Q(action="refund", status="refunded", refunded_at__gte=lower, refunded_at__lt=upper)
    queryset = PaymentTransaction.objects.filter(receipts | refunds)
    if search:
        queryset = queryset.filter(order_id__in=_search_orders(Order.objects.all(), search).values("pk"))
    return queryset.select_related("order").prefetch_related(
        Prefetch("order__items", queryset=OrderItem.objects.select_related("inventory")), "order__payment_transactions",
    ).order_by("pk")


def order_row(order, *, tax_rates=None):
    """tax_rates(item) -> (sale_rate, purchase_rate), explicit or unknown.

    A future historical tax policy resolver must also supply the SAME policy for
    original sales and their reversals; current company settings are not a policy.
    """
    issues, lines = [], []
    for item in order.items.all():
        sale_rate, purchase_rate = (None, None) if tax_rates is None else tax_rates(item)
        try:
            inventory = item.inventory
        except OrderItemInventory.DoesNotExist:
            inventory = None
        amounts = calculate_product_line(
            unit_sale_gross=item.unit_price, quantity=item.quantity,
            unit_purchase_gross=item.purchase_unit_gross if inventory is None else None,
            purchase_total_gross=inventory.purchase_total_gross if inventory is not None else None,
            sale_vat_rate=sale_rate, purchase_vat_rate=purchase_rate,
        )
        line_issues = []
        if amounts.sale.gross != item.line_total:
            line_issues.append("line_total_mismatch")
        if amounts.purchase is None:
            line_issues.append("purchase_cost_unknown")
        if sale_rate is None or purchase_rate is None:
            line_issues.append("tax_treatment_unknown")
        lines.append({
            "item_id": item.pk, "order_id": order.pk, "name": item.product_name,
            "internal_sku": item.internal_sku, "supplier_sku": item.sku,
            "quantity": item.quantity, "line_total": item.line_total,
            "purchase_source": "inventory_allocation" if inventory is not None else item.purchase_cost_source,
            "purchase_recorded_at": inventory.created_at if inventory is not None else item.purchase_cost_recorded_at,
            "amounts": amounts, "issues": tuple(line_issues),
        })
    if not lines:
        issues.append("order_items_missing")
    if sum((line["line_total"] for line in lines), ZERO) != order.subtotal:
        issues.append("subtotal_mismatch")
    if order.subtotal + order.delivery_price != order.total:
        issues.append("order_total_mismatch")
    if any("line_total_mismatch" in line["issues"] for line in lines):
        issues.append("line_total_mismatch")
    if order.delivery_provider == "easyway":
        if order.carrier_delivery_cost + order.delivery_margin != order.delivery_price:
            issues.append("delivery_total_mismatch")
        buffer = order.delivery_margin
        carrier_quote = order.carrier_delivery_cost
    elif order.delivery_provider == "internal":
        buffer, carrier_quote = ZERO, None
        if order.delivery_margin != ZERO:
            issues.append("internal_delivery_buffer_unexpected")
    else:
        buffer = carrier_quote = None
        issues.append("delivery_provider_unknown")
    return {
        "order_id": order.pk, "order_number": order.order_number,
        "created_at": order.created_at, "status": order.status,
        "payment_status": "refunded" if getattr(order, "accounting_refunded", False) else "paid", "subtotal": order.subtotal,
        "total": order.total, "delivery_price": order.delivery_price,
        "delivery_provider": order.delivery_provider, "carrier_quote": carrier_quote,
        "regional_buffer": buffer, "actual_delivery_cost": None,
        "lines": lines, "issues": tuple(issues),
    }


def build_order_report(period, *, tax_rates=None, limit=MAX_REPORT_ROWS, search=""):
    rows = [order_row(order, tax_rates=tax_rates) for order in _bounded(order_queryset(period, search), limit)]
    lines = [line for row in rows for line in row["lines"]]
    known = [line for line in lines if line["amounts"].purchase is not None]
    margins = [line for row in rows if not row["issues"] for line in row["lines"]
               if line["amounts"].net_markup is not None and not line["issues"]]
    return {"basis": "order_created_at", "period": period, "orders": rows, "summary": {
        "order_count": len(rows), "line_count": len(lines),
        "ordered_gross": sum((r["total"] for r in rows), ZERO),
        "delivery_gross": sum((r["delivery_price"] for r in rows), ZERO),
        "regional_buffer": sum((r["regional_buffer"] for r in rows if r["regional_buffer"] is not None), ZERO),
        "known_purchase_gross": sum((r["amounts"].purchase.gross for r in known), ZERO),
        "unknown_cost_line_count": len(lines) - len(known),
        "unknown_cost_sale_gross": sum((r["line_total"] for r in lines if r["amounts"].purchase is None), ZERO),
        "known_net_markup": sum((r["amounts"].net_markup for r in margins), ZERO),
        "markup_covered_line_count": len(margins),
        "net_rounding_adjustment": sum((r["amounts"].net_rounding_adjustment for r in margins), ZERO),
        "order_issue_count": sum(bool(r["issues"]) for r in rows),
        "line_issue_count": sum(bool(r["issues"]) for r in lines),
    }}


def _allocation(payment, row):
    """Allocate a full GEL payment only when its order linkage is unambiguous."""
    if row is None:
        return None, "payment_without_order"
    if row["issues"]:
        return None, "order_requires_review"
    if payment.currency != "GEL":
        return None, "order_currency_mismatch"
    transactions = list(payment.order.payment_transactions.all())
    sales = [p for p in transactions if p.action in RECEIPT_ACTIONS and p.status in RECEIVED_STATUSES]
    if len(sales) != 1:
        return None, "ambiguous_order_payments"
    sale = sales[0]
    if sale.captured_at is None or sale.amount != row["total"] or sale.currency != payment.currency:
        return None, "sale_requires_review"
    if payment.action == "refund":
        reference = payment.provider_reference
        context = reference.get("refund_request", {}) if isinstance(reference, dict) else {}
        sale_id = context.get("sale_payment_id") if isinstance(context, dict) else None
        refunds = [p for p in transactions if p.action == "refund" and p.status == "refunded"]
        if (type(sale_id) is not int or sale_id != sale.pk or payment.provider != sale.provider
                or payment.amount != sale.amount or len(refunds) != 1
                or payment.refunded_at < sale.captured_at):
            return None, "refund_allocation_requires_review"
    elif payment.pk != sale.pk:
        return None, "sale_requires_review"
    return {"product_gross": row["subtotal"], "delivery_gross": row["delivery_price"],
            "regional_buffer": row["regional_buffer"], "carrier_quote": row["carrier_quote"],
            "product_lines": row["lines"]}, None


def build_cash_report(period, *, tax_rates=None, limit=MAX_REPORT_ROWS, search=""):
    """Confirmed cash events, grouped by currency; never a VAT return or profit.

    Refund allocations are positive reversal amounts, summarized separately from
    collections. Full refunds reuse original item facts and the same explicitly
    supplied historical tax policy. Cash events cannot establish physical return
    of goods or invoice recognition. Missing tax treatment stays unknown.
    """
    events, currencies = [], {}
    for payment in _bounded(event_queryset(period, search), limit):
        refund = payment.action == "refund"
        row = order_row(payment.order, tax_rates=tax_rates) if payment.order_id else None
        allocation, issue = _allocation(payment, row)
        event = {
            "transaction_id": payment.pk, "order_id": payment.order_id,
            "kind": "refund" if refund else "receipt", "currency": payment.currency,
            "amount": payment.amount, "occurred_at": payment.refunded_at if refund else payment.captured_at,
            "allocation": allocation, "issues": (issue,) if issue else (),
        }
        events.append(event)
        totals = currencies.setdefault(payment.currency, {
            "received": ZERO, "refunded": ZERO, "net_received": ZERO,
            "delivery_received": ZERO, "delivery_refunded": ZERO,
            "buffer_received": ZERO, "buffer_refunded": ZERO,
            "product_received": ZERO, "product_refunded": ZERO,
            "known_markup_received": ZERO, "known_markup_refunded": ZERO,
            "markup_covered_lines_received": 0, "markup_covered_lines_refunded": 0,
            "rounding_adjustment_received": ZERO, "rounding_adjustment_refunded": ZERO,
            "unallocated_received": ZERO, "unallocated_refunded": ZERO,
        })
        totals["refunded" if refund else "received"] += payment.amount
        suffix = "refunded" if refund else "received"
        if allocation is None:
            totals["unallocated_" + suffix] += payment.amount
        else:
            totals["product_" + suffix] += allocation["product_gross"]
            totals["delivery_" + suffix] += allocation["delivery_gross"]
            totals["buffer_" + suffix] += allocation["regional_buffer"]
            for line in allocation["product_lines"]:
                if not line["issues"] and line["amounts"].net_markup is not None:
                    totals["known_markup_" + suffix] += line["amounts"].net_markup
                    totals["markup_covered_lines_" + suffix] += 1
                    totals["rounding_adjustment_" + suffix] += line["amounts"].net_rounding_adjustment
        totals["net_received"] = totals["received"] - totals["refunded"]
        totals["net_delivery"] = totals["delivery_received"] - totals["delivery_refunded"]
        totals["net_buffer"] = totals["buffer_received"] - totals["buffer_refunded"]
    events.sort(key=lambda e: (e["occurred_at"], e["transaction_id"]))
    return {"basis": "cash_confirmation", "period": period, "events": events,
            "currencies": currencies}
