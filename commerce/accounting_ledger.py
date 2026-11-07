"""One product ledger for confirmed, unreturned sales or completed refunds."""
from decimal import Decimal
from django.db.models import Exists, OuterRef, Q
from .models import PaymentTransaction
from .accounting_reports import event_queryset, order_row, _allocation, _bounded, MAX_REPORT_ROWS, TBILISI
from .return_costs import return_cost_report
from .courier_reporting import booking_report

HEADERS = ["თარიღი", "შეკვეთა", "პროდუქტი", "SKU", "რაოდენობა", "შესაძენი ერთეული ₾",
           "გასაყიდი ერთეული ₾", "შესაძენი ჯამი ₾", "გასაყიდი ჯამი ₾",
           "თვითღირებულება დღგ-ის გარეშე ₾", "პროდუქტის მოგება დღგ-ის გარეშე ₾", "შიდა მიტანა (ძველი) ₾",
           "ჩექაუთის საკურიერო ტარიფი ₾", "ბუფერი ₾", "გადახდილი / დაბრუნებული თანხა ₾", "გადახდა", "მყიდველის ტიპი", "მყიდველი კომპანია დღგ-ის გადამხდელია",
           "უკუმიტანისთვის დაქვითული ₾", "უკუმიტანის ხარჯი (საინფორმაციო) ₾",
           "RedCap-ის ფასი (საინფორმაციო) ₾", "ფასთა სხვაობა (საინფორმაციო) ₾",
           "პირველი მიტანისთვის დაქვითული (მიტანის ნაშთში შედის) ₾"]


def visible_columns(show_purchase=False):
    return [i for i in range(len(HEADERS)) if show_purchase or i not in (5, 7)]


def build_ledger(period, status, sku=""):
    if status not in ("paid", "refunded", "all"):
        raise ValueError("Invalid financial status")
    qs = event_queryset(period).filter(order__isnull=False, currency="GEL").select_related("order__redcap_shipment")
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
        shipment = getattr(payment.order, "redcap_shipment", None) if payment.order.delivery_provider == "redcap" else None
        booked_price = shipment.booked_price if shipment else None
        difference = booked_price - payment.order.carrier_delivery_cost if booked_price is not None else None
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
            courier = order["delivery_provider"] in {"easyway", "redcap"}
            rows.append([
                occurred.astimezone(TBILISI).strftime("%d.%m.%Y %H:%M"), order["order_number"],
                line["name"], line["internal_sku"], line["quantity"] * sign,
                purchase.gross / line["quantity"] if purchase else None, a.sale.gross / line["quantity"],
                purchase.gross * sign if purchase and allocation else None, a.sale.gross * sign if allocation else None,
                purchase.net * sign if purchase and allocation else None, a.net_markup * sign if allocation and a.net_markup is not None else None,
                allocation["delivery_gross"] * sign if first and internal and allocation else (Decimal(0) if first and allocation else None),
                allocation["carrier_quote"] * sign if first and courier and allocation else (Decimal(0) if first and allocation else None),
                allocation["regional_buffer"] * sign if first and allocation else None,
                payment.amount * sign if first else None,
                ("ნაწილობრივ დაბრუნებული" if payment.amount < payment.order.total else "დაბრუნებული") if refund else "გადახდილი",
                "იურიდიული პირი" if payment.order.buyer_type == "legal_entity" else "ფიზიკური პირი",
                ("კი" if payment.order.company_is_vat_registered is True else
                 "არა" if payment.order.company_is_vat_registered is False else "არ არის მითითებული")
                if payment.order.buyer_type == "legal_entity" else "—",
                allocation["retained_return_fee"] if first and refund and allocation else (Decimal(0) if first and not refund else None),
                allocation["return_delivery_cost"] if first and refund and allocation else (Decimal(0) if first and not refund else None),
                booked_price if first else None, difference if first else None,
                allocation["retained_delivery_fee"] if first and refund and allocation else (Decimal(0) if first and not refund and allocation else None),
            ])
        if len(rows) > group_start:
            groups.append({"event_id": payment.pk, "delivery_provider": order["delivery_provider"],
                           "original_total": payment.order.total, "refund": refund, "rows": rows[group_start:]})
    totals = ["სულ", None, None, None, sum(r[4] for r in rows), None, None]
    for column in range(7, 15):
        values = [row[column] for row in rows]
        # Missing historical costs must not turn into invented zero-cost profit.
        totals.append(None if column <= 10 and any(v is None for v in values)
                      else sum((v for v in values if v is not None), Decimal(0)))
    if sku:
        totals[11:15] = [None] * 4
    totals.extend([None, None, None])
    for column in (18, 19):
        values = [row[column] for row in rows if row[14] is not None]
        totals.append(None if sku or any(v is None for v in values) else sum(values, Decimal(0)))
    totals[19] = None  # Expense periods are independent of cash-refund dates.
    totals.extend([None, None])  # Booking snapshots are information, not cash.
    delivery_fees = [row[22] for row in rows if row[14] is not None]
    # Informational subset of net delivery, not another income/expense entry.
    totals.append(None if sku or any(value is None for value in delivery_fees)
                  else sum(delivery_fees, Decimal(0)))
    costs = return_cost_report(period) if not sku else None
    bookings = booking_report(period) if not sku else None
    return {"headers": HEADERS, "rows": rows, "groups": groups, "totals": totals, "period": period,
            "status": status, "sku": sku, "order_count": len({p.order_id for p in events}), "return_costs": costs,
            "courier_bookings": bookings}
