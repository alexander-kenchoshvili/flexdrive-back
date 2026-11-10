"""Shared stored Wingo facts for business and accounting; not invoice balances."""
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, CharField, Count, F, Q, Value, When

from commerce.accounting_reports import MAX_REPORT_ROWS, TBILISI, _bounded
from commerce.models import Order, WingoShipment
from .wingo_tracking import STATUS_LABELS

ZERO = Decimal("0.00")
STAGES = {"not_sent": "ჯერ არ გაგზავნილა", "created": "გზავნილი შექმნილია", "shipped": "გზაშია",
          "delivered": "ჩაბარებულია", "cancelled": "გაუქმებულია", "returning": "ნივთების დაბრუნება", "uncertain": "შედეგი დასადასტურებელია"}
IN_TRANSIT = (3, 5, 6, 7)
ATTENTION = (4, 8, 10, 11)
UNCERTAIN = ("submitting", "unknown")


def _money(value):
    return None if value is None else format(value, ".2f")


def shipment_facts(order):
    shipment = getattr(order, "wingo_shipment", None)
    case = getattr(order, "return_case", None)
    state = shipment.state if shipment else "not_sent"
    carrier = shipment.carrier_status if shipment else None
    if case and case.disposition == "from_customer":
        stage = "returning"
    elif carrier == 10:
        stage = "cancelled"
    elif state in UNCERTAIN:
        stage = "uncertain"
    elif carrier == 9:
        stage = "delivered"
    elif carrier in IN_TRANSIT:
        stage = "shipped"
    else:
        stage = "created" if state == "created" else "not_sent"
    price = shipment.booked_price if shipment else None
    difference = price - order.carrier_delivery_cost if price is not None else None
    issues = []
    if state in UNCERTAIN:
        issues.append("გაგზავნის ან გაუქმების შედეგი დასადასტურებელია.")
    if state == "failed":
        issues.append("გზავნილის შექმნის მოთხოვნა უარყოფილია.")
    if shipment and (shipment.tracking_error or shipment.last_error):
        issues.append("გზავნილს შენახული გაფრთხილება აქვს — გადაამოწმეთ შეკვეთა ადმინში.")
    if state == "created" and price is None:
        issues.append("Wingo-ს ფასი უცნობია.")
    if difference is not None and difference != ZERO:
        issues.append("Wingo-ს ფასი ჩექაუთის ტარიფს არ ემთხვევა.")
    if carrier in ATTENTION or carrier is not None and carrier not in STATUS_LABELS:
        issues.append("საკურიერო სტატუსს ყურადღება სჭირდება.")
    if shipment and shipment.webhook_received_at and (not shipment.webhook_checked_at
            or shipment.webhook_received_at > shipment.webhook_checked_at):
        issues.append("მიღებული შეტყობინება ჯერ არ გადამოწმებულა — განაახლეთ სტატუსი ადმინში.")
    if carrier == 10:
        issues.append("გაუქმებული გზავნილის შესაძლო საფასური Wingo-სთან შესაჯერებელია.")
    return {"order_number": order.order_number, "stage": stage, "stage_label": STAGES[stage],
        "tracking_number": shipment.tracking_number if shipment else None,
        "return_tracking_number": case.wingo_return_tracking_number if case else None,
        "carrier_status_label": STATUS_LABELS.get(carrier, "უცნობი სტატუსი" if carrier else "ჯერ არ შემოწმებულა"),
        "submitted_at": shipment.submitted_at.isoformat() if shipment and shipment.submitted_at else None,
        "checked_at": shipment.tracking_checked_at.isoformat() if shipment and shipment.tracking_checked_at else None,
        "customer_delivery": _money(order.delivery_price), "quoted_price": _money(order.carrier_delivery_cost),
        "buffer": _money(order.delivery_margin), "booked_price": _money(price), "difference": _money(difference),
        "issues": issues}


def booking_report(period):
    lower, upper = period.bounds
    bookings = WingoShipment.objects.filter(order__delivery_provider="wingo", state="created", submitted_at__gte=lower,
        submitted_at__lt=upper).select_related("order__wingo_shipment", "order__return_case").order_by("submitted_at", "pk")
    rows, known, difference, unknown, cancelled, mismatches = [], ZERO, ZERO, 0, 0, 0
    for shipment in _bounded(bookings, MAX_REPORT_ROWS):
        row = shipment_facts(shipment.order)
        row["cancelled"] = shipment.carrier_status == 10
        row["date"] = shipment.submitted_at.astimezone(TBILISI).date().isoformat()
        # Cancellation charges require provider/invoice review; never invent zero.
        if shipment.carrier_status == 10:
            cancelled += 1
        elif shipment.booked_price is None:
            unknown += 1
        else:
            known += shipment.booked_price
            difference += shipment.booked_price - shipment.order.carrier_delivery_cost
            mismatches += int(shipment.booked_price != shipment.order.carrier_delivery_cost)
        rows.append(row)
    return {"rows": rows, "known_price": known, "total": None if unknown else known,
        "difference": None if unknown else difference, "unknown": unknown, "cancelled": cancelled, "mismatches": mismatches}


def shipment_report(options):
    orders = Order.objects.filter(delivery_provider="wingo").exclude(payment_status__in=("pending", "failed", "cancelled"))
    orders = orders.annotate(shipment_stage=Case(
        When(return_case__disposition="from_customer", then=Value("returning")),
        When(wingo_shipment__carrier_status=10, then=Value("cancelled")),
        When(wingo_shipment__state__in=UNCERTAIN, then=Value("uncertain")),
        When(wingo_shipment__carrier_status=9, then=Value("delivered")),
        When(wingo_shipment__carrier_status__in=IN_TRANSIT, then=Value("shipped")),
        When(wingo_shipment__state="created", then=Value("created")),
        default=Value("not_sent"), output_field=CharField()))
    review = (Q(wingo_shipment__state__in=(*UNCERTAIN, "failed"))
        | (Q(wingo_shipment__isnull=False) & (~Q(wingo_shipment__tracking_error="") | ~Q(wingo_shipment__last_error="")))
        | Q(wingo_shipment__state="created", wingo_shipment__booked_price__isnull=True)
        | Q(wingo_shipment__booked_price__isnull=False) & ~Q(wingo_shipment__booked_price=F("carrier_delivery_cost"))
        | Q(wingo_shipment__carrier_status__in=ATTENTION)
        | Q(wingo_shipment__carrier_status__isnull=False) & ~Q(wingo_shipment__carrier_status__in=STATUS_LABELS)
        | Q(wingo_shipment__webhook_received_at__isnull=False) & (Q(wingo_shipment__webhook_checked_at__isnull=True)
            | Q(wingo_shipment__webhook_received_at__gt=F("wingo_shipment__webhook_checked_at"))))
    summary = orders.aggregate(**{key: Count("pk", filter=Q(shipment_stage=key)) for key in STAGES}, review=Count("pk", filter=review))
    selected = options.get("shipments", "all")
    if selected == "review":
        orders = orders.filter(review)
    elif selected != "all":
        orders = orders.filter(shipment_stage=selected)
    page = Paginator(orders.select_related("wingo_shipment", "return_case").order_by("-updated_at", "-pk"), 20).get_page(options.get("shipments_page", 1))
    return {"filter": selected, "summary": summary, "items": [shipment_facts(order) for order in page],
        "total": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages, "page_size": 20}
