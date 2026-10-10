"""Read-only dashboard facts. No provider calls, current-price guesses or tax returns."""
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Prefetch
from django.utils import timezone

from commerce.accounting_calculations import split_vat_inclusive
from commerce.accounting_reports import (
    MAX_REPORT_ROWS, ReportPeriod, TBILISI, _allocation, _bounded, event_queryset, order_row,
)
from commerce.models import OrderReturnLine, OwnedStockLot

ZERO = Decimal("0.00")
VAT = Decimal(18)
MONEY_KEYS = (
    "received", "refunded", "net_received", "product_received", "product_refunded",
    "net_product_received", "delivery_received", "delivery_refunded", "net_delivery_received",
    "product_sales_net", "product_cost_net", "product_rounding_net", "product_profit_net",
    "courier_payable", "buffer_received",
    "buffer_refunded", "net_buffer", "internal_delivery_received", "internal_delivery_refunded",
    "net_internal_delivery", "unsaleable_cost_net", "average_order",
)
COUNT_KEYS = (
    "paid_orders", "refunded_orders", "sold_units", "returned_units", "net_units",
    "regional_orders", "buffer_orders", "internal_orders", "unsaleable_units",
    "unallocated_events", "unknown_cost_lines", "unknown_loss_lines",
)
ALLOCATED_KEYS = (
    "product_received", "product_refunded", "net_product_received", "delivery_received",
    "delivery_refunded", "net_delivery_received", "product_sales_net", "product_cost_net",
    "product_rounding_net", "product_profit_net",
    "buffer_received", "buffer_refunded", "net_buffer", "internal_delivery_received",
    "internal_delivery_refunded", "net_internal_delivery", "sold_units", "returned_units", "net_units",
)


def previous_period(period):
    """Calendar-month comparison for month-to-date/full month; equal days otherwise."""
    if period.start.day == 1 and period.start.month == period.end.month and period.start.year == period.end.year:
        last = period.start - timedelta(days=1)
        end_day = last.day if period.end.day == monthrange(period.end.year, period.end.month)[1] else min(period.end.day, last.day)
        return ReportPeriod(last.replace(day=1), last.replace(day=end_day))
    length = (period.end - period.start).days + 1
    return ReportPeriod(period.start - timedelta(days=length), period.start - timedelta(days=1))


def _summary():
    return {**dict.fromkeys(MONEY_KEYS, ZERO), **dict.fromkeys(COUNT_KEYS, 0)}


def _money(value):
    return None if value is None else format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def _serialize(summary):
    return {key: _money(value) if key in MONEY_KEYS else value for key, value in summary.items()}


def _loss_cost(line):
    """Rejects inherit the cost layers left after the existing FIFO receipt service."""
    item = line.order_item
    try:
        inventory = item.inventory
    except AttributeError:
        total = None if item.purchase_unit_gross is None else item.purchase_unit_gross * item.quantity
    else:
        total = inventory.purchase_total_gross
    lots = list(line.stock_lots.all())
    if (total is None or any(lot.purchase_unit_gross is None for lot in lots)
            or sum(lot.quantity for lot in lots) != line.saleable_quantity
            or line.saleable_quantity + line.unsaleable_quantity != item.quantity):
        return None
    cost = total - sum((lot.purchase_unit_gross * lot.quantity for lot in lots), ZERO)
    if cost < ZERO:
        return None
    return split_vat_inclusive(cost, vat_rate=VAT).net


def _collect(period):
    summary = _summary()
    daily = {}
    current = period.start
    while current <= period.end:
        daily[current.isoformat()] = _summary()
        current += timedelta(days=1)
    products, deliveries, losses, rows = {}, [], [], {}
    paid_ids, refund_ids, courier_ids, internal_ids = set(), set(), set(), set()
    daily_orders = {key: {"paid": set(), "refunded": set()} for key in daily}
    events = _bounded(event_queryset(period).filter(currency="GEL").select_related("order__return_case"), MAX_REPORT_ROWS)
    for payment in events:
        refund = payment.action == "refund"
        occurred = payment.refunded_at if refund else payment.captured_at
        day = daily[occurred.astimezone(TBILISI).date().isoformat()]
        targets = (summary, day)
        for target in targets:
            target["refunded" if refund else "received"] += payment.amount
        if payment.order_id:
            (refund_ids if refund else paid_ids).add(payment.order_id)
            kind = "refunded" if refund else "paid"
            orders_today = daily_orders[occurred.astimezone(TBILISI).date().isoformat()][kind]
            orders_today.add(payment.order_id)
            day[f"{kind}_orders"] = len(orders_today)
        if payment.order_id not in rows:
            try:
                rows[payment.order_id] = order_row(payment.order, tax_rates=lambda item: (VAT, VAT)) if payment.order_id else None
            except (ValueError, ArithmeticError):
                rows[payment.order_id] = None
        row = rows[payment.order_id]
        allocation, _ = _allocation(payment, row)
        if allocation is None:
            for target in targets:
                target["unallocated_events"] += 1
            continue
        sign = -1 if refund else 1
        suffix = "refunded" if refund else "received"
        for target in targets:
            target[f"product_{suffix}"] += allocation["product_gross"]
            target[f"delivery_{suffix}"] += allocation["delivery_gross"]
            target[f"buffer_{suffix}"] += allocation["regional_buffer"]
            if not refund:
                target["buffer_orders"] += int(allocation["regional_buffer"] > ZERO)
            if row["delivery_provider"] == "internal":
                target[f"internal_delivery_{suffix}"] += row["delivery_price"]
        if not refund and row["delivery_provider"] == "internal":
            internal_ids.add(payment.order_id)
        # A quote is counted once per paid regional order, never once per item.
        # A completed pre-dispatch cancellation incurs no outward carrier charge;
        # a dispatched return must not erase the original carrier quote.
        if not refund and row["delivery_provider"] == "easyway" and payment.order_id not in courier_ids:
            order = payment.order
            case = getattr(order, "return_case", None)
            dispatched = bool(order.easyway_submitted_at or order.easyway_order_id
                              or order.status in ("shipped", "delivered")
                              or case and case.disposition == "from_customer")
            cancelled_before_dispatch = not dispatched and any(
                tx.action == "refund" and tx.status == "refunded" and tx.refunded_at
                for tx in order.payment_transactions.all()
            )
            if not cancelled_before_dispatch:
                courier_ids.add(payment.order_id)
                for target in targets:
                    target["courier_payable"] += allocation["carrier_quote"]
                    target["regional_orders"] += 1
                deliveries.append({"order_number": order.order_number, "date": occurred.astimezone(TBILISI).date().isoformat(),
                                   "carrier": _money(allocation["carrier_quote"]), "buffer": _money(allocation["regional_buffer"]),
                                   "delivery": _money(row["delivery_price"])})
        for line in allocation["product_lines"]:
            amount = line["amounts"]
            key = line["internal_sku"] or f"item:{line['item_id']}"
            product = products.setdefault(key, {"sku": line["internal_sku"], "name": line["name"],
                                                "sold_units": 0, "returned_units": 0, "received": ZERO,
                                                "refunded": ZERO, "profit": ZERO})
            product["returned_units" if refund else "sold_units"] += line["quantity"]
            product[suffix] += amount.sale.gross
            for target in targets:
                target["returned_units" if refund else "sold_units"] += line["quantity"]
                target["product_sales_net"] += amount.sale.net * sign
                if amount.net_markup is None:
                    target["unknown_cost_lines"] += 1
                else:
                    target["product_cost_net"] += amount.purchase.net * sign
                    # Profit is rounded from unrounded VAT-exclusive amounts.
                    # Expose the signed cents needed to reconcile displayed totals:
                    # sales_net - cost_net + rounding_net == profit_net.
                    target["product_rounding_net"] -= amount.net_rounding_adjustment * sign
                    target["product_profit_net"] += amount.net_markup * sign
            if amount.net_markup is None:
                product["profit"] = None
            elif product["profit"] is not None:
                product["profit"] += amount.net_markup * sign

    lower, upper = period.bounds
    rejected = OrderReturnLine.objects.filter(
        return_case__receipt_status="received", inspected_at__gte=lower, inspected_at__lt=upper,
        unsaleable_quantity__gt=0,
    ).select_related("order_item__inventory", "return_case__order").prefetch_related(
        Prefetch("stock_lots", queryset=OwnedStockLot.objects.only("return_line_id", "quantity", "purchase_unit_gross")),
    ).order_by("pk")
    for line in _bounded(rejected, MAX_REPORT_ROWS):
        cost = _loss_cost(line)
        summary["unsaleable_units"] += line.unsaleable_quantity
        if cost is None:
            summary["unknown_loss_lines"] += 1
        else:
            summary["unsaleable_cost_net"] += cost
        losses.append({"order_number": line.return_case.order.order_number, "sku": line.order_item.internal_sku,
                       "name": line.order_item.product_name, "quantity": line.unsaleable_quantity,
                       "date": line.inspected_at.astimezone(TBILISI).date().isoformat(), "cost_net": _money(cost)})

    for target in (summary, *daily.values()):
        target["net_received"] = target["received"] - target["refunded"]
        target["net_product_received"] = target["product_received"] - target["product_refunded"]
        target["net_delivery_received"] = target["delivery_received"] - target["delivery_refunded"]
        target["net_buffer"] = target["buffer_received"] - target["buffer_refunded"]
        target["net_internal_delivery"] = target["internal_delivery_received"] - target["internal_delivery_refunded"]
        target["net_units"] = target["sold_units"] - target["returned_units"]
        if target["unknown_cost_lines"]:
            target["product_profit_net"] = target["product_cost_net"] = target["product_rounding_net"] = None
        if target["unallocated_events"]:
            for key in ALLOCATED_KEYS:
                target[key] = None
        if target["unknown_loss_lines"]:
            target["unsaleable_cost_net"] = None
    summary["paid_orders"], summary["refunded_orders"] = len(paid_ids), len(refund_ids)
    summary["internal_orders"] = len(internal_ids)
    summary["average_order"] = summary["received"] / len(paid_ids) if paid_ids and not summary["unallocated_events"] else (None if summary["unallocated_events"] else ZERO)
    if summary["unallocated_events"]:
        # Carrier subtotals cannot be advertised as complete if allocation failed.
        summary["courier_payable"] = None
    ordered_products = sorted(products.values(), key=lambda item: (-item["received"], item["name"]))
    top = [{**{key: product[key] for key in ("sku", "name", "sold_units", "returned_units")},
            "net_units": product["sold_units"] - product["returned_units"],
            "net_sales": _money(product["received"] - product["refunded"]), "profit_net": _money(product["profit"])}
           for product in ordered_products[:10]]
    chart_keys = ("received", "refunded", "net_received", "product_profit_net", "paid_orders", "sold_units")
    return {"summary": _serialize(summary),
            "daily": [{"date": key, **{field: _serialize(value)[field] for field in chart_keys}} for key, value in daily.items()],
            "products": top, "deliveries": sorted(deliveries, key=lambda row: (row["date"], row["order_number"]), reverse=True)[:20],
            "delivery_rows_total": len(deliveries), "losses": sorted(losses, key=lambda row: row["date"], reverse=True)[:20],
            "loss_rows_total": len(losses)}


def build_dashboard_report(period):
    if (period.end - period.start).days >= 366:
        raise ValueError("აირჩიეთ არაუმეტეს 366 დღის პერიოდი.")
    previous = previous_period(period)
    current, before = _collect(period), _collect(previous)
    comparisons = {}
    for key in (*MONEY_KEYS, "paid_orders", "sold_units", "returned_units", "net_units"):
        value, old = current["summary"][key], before["summary"][key]
        if value is None or old is None:
            comparisons[key] = {"delta": None, "percent": None}
            continue
        delta = Decimal(value) - Decimal(old)
        comparisons[key] = {"delta": _money(delta),
                            "percent": _money(delta / abs(Decimal(old)) * 100) if Decimal(old) != 0 else None}
    return {**current, "previous": before["summary"], "comparisons": comparisons,
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "previous_period": {"start": previous.start.isoformat(), "end": previous.end.isoformat()},
            "currency": "GEL", "vat_rate": 18, "timezone": "Asia/Tbilisi", "generated_at": timezone.now().isoformat()}
