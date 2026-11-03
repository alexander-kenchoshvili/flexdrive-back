"""Shared stored RedCap facts for business and accounting; not invoice balances."""
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, CharField, Count, F, Q, Value, When

from commerce.accounting_reports import MAX_REPORT_ROWS, TBILISI, _bounded
from commerce.models import Order, RedcapShipment

ZERO = Decimal("0.00")
STAGES = {"not_sent": "ჯერ არ გაგზავნილა", "created": "გზავნილი შექმნილია", "shipped": "გზაშია",
          "delivered": "ჩაბარებულია", "cancelled": "გაუქმებულია", "returning": "ნივთების დაბრუნება", "uncertain": "შედეგი დასადასტურებელია"}
IN_TRANSIT = ("picked_up", "in_warehouse", "mzadaa_gasatanad", "sawyobidan_gatanilia", "gagzavnilia_regionshi", "out_for_delivery")
ATTENTION = ("molodinis_rezhimshi", "postponed", "unreachable", "refused", "ukan_dabrunebuli")
UNCERTAIN = ("submitting", "unknown", "cancelling", "cancel_unknown")
STATUS_LABELS = {"registered": "დარეგისტრირებულია", "pending_pickup": "აღების მოლოდინში", "picked_up": "კურიერმა აიღო",
    "in_warehouse": "საწყობშია", "mzadaa_gasatanad": "გასატანად მზადაა", "sawyobidan_gatanilia": "საწყობიდან გატანილია",
    "gagzavnilia_regionshi": "რეგიონში გაგზავნილია", "out_for_delivery": "ჩასაბარებლად გზაშია", "delivered": "ჩაბარებულია",
    "molodinis_rezhimshi": "მოლოდინის რეჟიმშია", "postponed": "გადადებულია", "unreachable": "მიმღებთან კავშირი ვერ შედგა",
    "refused": "მიმღებმა უარი თქვა", "ukan_dabrunebuli": "უკან დაბრუნებულია", "cancelled": "გაუქმებულია"}


def _money(value):
    return None if value is None else format(value, ".2f")


def shipment_facts(order):
    shipment = getattr(order, "redcap_shipment", None)
    case = getattr(order, "return_case", None)
    state = shipment.state if shipment else "not_sent"
    carrier = shipment.carrier_status if shipment else ""
    if case and case.disposition == "from_customer":
        stage = "returning"
    elif state == "cancelled":
        stage = "cancelled"
    elif state in UNCERTAIN:
        stage = "uncertain"
    elif carrier == "delivered":
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
        issues.append("RedCap-ის ფასი უცნობია.")
    if difference is not None and difference != ZERO:
        issues.append("RedCap-ის ფასი ჩექაუთის ტარიფს არ ემთხვევა.")
    if carrier in ATTENTION or carrier and carrier not in STATUS_LABELS:
        issues.append("საკურიერო სტატუსს ყურადღება სჭირდება.")
    return {"order_number": order.order_number, "stage": stage, "stage_label": STAGES[stage],
        "tracking_number": shipment.tracking_number if shipment else None,
        "carrier_status_label": STATUS_LABELS.get(carrier, "უცნობი სტატუსი" if carrier else "ჯერ არ შემოწმებულა"),
        "submitted_at": shipment.submitted_at.isoformat() if shipment and shipment.submitted_at else None,
        "checked_at": shipment.tracking_checked_at.isoformat() if shipment and shipment.tracking_checked_at else None,
        "customer_delivery": _money(order.delivery_price), "quoted_price": _money(order.carrier_delivery_cost),
        "buffer": _money(order.delivery_margin), "booked_price": _money(price), "difference": _money(difference),
        "issues": issues}


def booking_report(period):
    lower, upper = period.bounds
    bookings = RedcapShipment.objects.filter(order__delivery_provider="redcap", submitted_at__gte=lower,
        submitted_at__lt=upper).select_related("order__redcap_shipment", "order__return_case").order_by("submitted_at", "pk")
    rows, known, difference, unknown, cancelled, mismatches = [], ZERO, ZERO, 0, 0, 0
    for shipment in _bounded(bookings, MAX_REPORT_ROWS):
        row = shipment_facts(shipment.order)
        row["cancelled"] = shipment.state == "cancelled"
        row["date"] = shipment.submitted_at.astimezone(TBILISI).date().isoformat()
        # Cancellation charges require provider/invoice review; never invent zero.
        if shipment.state == "cancelled":
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
    orders = Order.objects.filter(delivery_provider="redcap").exclude(payment_status__in=("pending", "failed", "cancelled"))
    orders = orders.annotate(shipment_stage=Case(
        When(return_case__disposition="from_customer", then=Value("returning")),
        When(redcap_shipment__state="cancelled", then=Value("cancelled")),
        When(redcap_shipment__state__in=UNCERTAIN, then=Value("uncertain")),
        When(redcap_shipment__carrier_status="delivered", then=Value("delivered")),
        When(redcap_shipment__carrier_status__in=IN_TRANSIT, then=Value("shipped")),
        When(redcap_shipment__state="created", then=Value("created")),
        default=Value("not_sent"), output_field=CharField()))
    review = (Q(redcap_shipment__state__in=(*UNCERTAIN, "failed"))
        | (Q(redcap_shipment__isnull=False) & (~Q(redcap_shipment__tracking_error="") | ~Q(redcap_shipment__last_error="")))
        | Q(redcap_shipment__state="created", redcap_shipment__booked_price__isnull=True)
        | Q(redcap_shipment__booked_price__isnull=False) & ~Q(redcap_shipment__booked_price=F("carrier_delivery_cost"))
        | Q(redcap_shipment__carrier_status__in=ATTENTION)
        | Q(redcap_shipment__isnull=False) & ~Q(redcap_shipment__carrier_status__in=("", *STATUS_LABELS)))
    summary = orders.aggregate(**{key: Count("pk", filter=Q(shipment_stage=key)) for key in STAGES}, review=Count("pk", filter=review))
    selected = options.get("shipments", "all")
    if selected == "review":
        orders = orders.filter(review)
    elif selected != "all":
        orders = orders.filter(shipment_stage=selected)
    page = Paginator(orders.select_related("redcap_shipment", "return_case").order_by("-updated_at", "-pk"), 20).get_page(options.get("shipments_page", 1))
    return {"filter": selected, "summary": summary, "items": [shipment_facts(order) for order in page],
        "total": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages, "page_size": 20}
