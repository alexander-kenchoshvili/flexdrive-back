"""One product ledger for confirmed, unreturned sales or completed refunds."""
from decimal import Decimal
from django.db.models import Exists, OuterRef, Q
from .models import PaymentTransaction
from .accounting_reports import event_queryset, order_row, _allocation, _bounded, MAX_REPORT_ROWS, TBILISI

HEADERS = ["თარიღი", "შეკვეთა", "პროდუქტი", "SKU", "რაოდენობა", "შესაძენი ერთეული ₾",
           "გასაყიდი ერთეული ₾", "შესაძენი ჯამი ₾", "გასაყიდი ჯამი ₾",
           "თვითღირებულება დღგ-ის გარეშე ₾", "პროდუქტის მოგება დღგ-ის გარეშე ₾", "თბილისის მიტანა ₾",
           "რეგიონის მიტანა ₾", "ბუფერი ₾", "სრული თანხა ₾", "გადახდა"]


def build_ledger(period, status, sku=""):
    if status not in ("paid", "refunded", "all"):
        raise ValueError("Invalid financial status")
    qs = event_queryset(period).filter(order__isnull=False, currency="GEL")
    if status == "paid":
        refunds = PaymentTransaction.objects.filter(order_id=OuterRef("order_id"), action="refund", status="refunded", refunded_at__isnull=False)
        qs = qs.exclude(action="refund").annotate(has_refund=Exists(refunds)).filter(has_refund=False)
    elif status == "refunded":
        qs = qs.filter(action="refund")
    sku = sku.strip()
    if sku:
        qs = qs.filter(Q(order__items__internal_sku__icontains=sku) | Q(order__items__sku__icontains=sku)
                       | Q(order__items__product_name__icontains=sku)).distinct()
    rows, groups = [], []
    events = _bounded(qs, MAX_REPORT_ROWS)
    events.sort(key=lambda p: (p.refunded_at if p.action == "refund" else p.captured_at, p.pk))
    for payment in events:
        group_start = len(rows)
        order = order_row(payment.order, tax_rates=lambda item: (Decimal(18), Decimal(18)))
        allocation, _ = _allocation(payment, order)
        refund = payment.action == "refund"
        sign = -1 if refund and status == "all" else 1
        occurred = payment.refunded_at if refund else payment.captured_at
        lines = [line for line in order["lines"] if not sku or sku.casefold() in line["internal_sku"].casefold()
                 or sku.casefold() in line["supplier_sku"].casefold()
                 or sku.casefold() in line["name"].casefold()]
        for index, line in enumerate(lines):
            a = line["amounts"]
            purchase = a.purchase
            first = index == 0 and not sku
            internal = order["delivery_provider"] == "internal"
            regional = order["delivery_provider"] == "easyway"
            rows.append([
                occurred.astimezone(TBILISI).strftime("%d.%m.%Y %H:%M"), order["order_number"],
                line["name"], line["internal_sku"], line["quantity"] * sign,
                purchase.gross / line["quantity"] if purchase else None, a.sale.gross / line["quantity"],
                purchase.gross * sign if purchase and allocation else None, a.sale.gross * sign if allocation else None,
                purchase.net * sign if purchase and allocation else None, a.net_markup * sign if allocation else None,
                order["delivery_price"] * sign if first and internal and allocation else (Decimal(0) if first and allocation else None),
                order["carrier_quote"] * sign if first and regional and allocation else (Decimal(0) if first and allocation else None),
                order["regional_buffer"] * sign if first and allocation else None,
                payment.amount * sign if first else None,
                "დაბრუნებული" if refund else "გადახდილი",
            ])
        if len(rows) > group_start:
            groups.append({"event_id": payment.pk, "rows": rows[group_start:]})
    totals = ["სულ", None, None, None, sum(r[4] for r in rows), None, None]
    for column in range(7, 15):
        values = [row[column] for row in rows]
        # Missing historical costs must not turn into invented zero-cost profit.
        totals.append(None if column <= 10 and any(v is None for v in values)
                      else sum((v for v in values if v is not None), Decimal(0)))
    if sku:
        totals[11:15] = [None] * 4
    totals.append(None)
    return {"headers": HEADERS, "rows": rows, "groups": groups, "totals": totals, "period": period,
            "status": status, "sku": sku, "order_count": len({p.order_id for p in events})}
