"""Current operational snapshots, using stored facts only. No provider or write calls."""
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import SupplierSyncReport
from commerce.models import EasywaySyncReport, OrderReturn, OrderReturnLine, OwnedStockAllocation, OwnedStockLot, PaymentTransaction

from .reports import TBILISI, _money

PAGE_SIZE = 20
PAYMENT_LABELS = {
    "pending": "დადასტურების მოლოდინში", "authorized": "თანხა ავტორიზებულია",
    "paid": "გადახდილია", "failed": "წარუმატებელი", "cancelled": "გაუქმებულია",
    "refund_pending": "თანხის დაბრუნების მოლოდინში", "refunded": "თანხა დაბრუნებულია",
}
ACTION_LABELS = {
    "sale": "გადახდა", "authorize": "ავტორიზაცია", "capture": "თანხის ჩამოჭრა",
    "refund": "თანხის დაბრუნება", "cancel": "გაუქმება",
}
ISSUE_LABELS = {
    "provider_order_missing": "ბანკის გადახდის ID არ არის შენახული.",
    "paid_without_order": "გადახდა დაფიქსირებულია, მაგრამ შეკვეთა არ არის დაკავშირებული.",
    "pending_overdue": "შენახული შემოწმების მიხედვით გადახდა ვადის შემდეგაც დაუდასტურებელი იყო.",
    "provider_review_required": "ბანკის პასუხი ავტომატურად ვერ გადაწყდა.",
    "bank_request_failed": "ბანკთან ბოლო შენახული გადამოწმება ვერ დასრულდა.",
    "bank_response_conflict": "ბანკის პასუხი ვერ დადასტურდა.",
    "unexpected_error": "ბოლო შენახული გადამოწმება შეცდომით შეწყდა.",
}
SUPPLIER_COUNTS = {
    "new": "ახალი პროდუქტები", "out_of_stock": "მარაგი ამოეწურა",
    "back_in_stock": "მარაგში დაბრუნდა", "archived": "დაარქივდა",
    "restored": "არქივიდან გამოქვეყნდა", "supplier_price": "შესყიდვის ფასი შეიცვალა",
}
TRACKING_COUNTS = {
    "checked": "შემოწმდა", "changed": "შეიცვალა", "review": "გადასამოწმებელია",
    "failed": "შეცდომა", "skipped": "გამოტოვებულია",
}
PENDING = Q(status__in=("pending", "authorized", "refund_pending"))
ISSUES = ~Q(reconciliation_issue="") | Q(status="paid", order__isnull=True)


def _age(when, now):
    days = (now.astimezone(TBILISI).date() - when.astimezone(TBILISI).date()).days
    return days if days >= 0 else None


def _page(queryset, number, serialize):
    page = Paginator(queryset, PAGE_SIZE).get_page(number)
    return {"items": [serialize(row) for row in page.object_list], "total": page.paginator.count,
            "page": page.number, "pages": page.paginator.num_pages, "page_size": PAGE_SIZE}


def _returns(options, now):
    cases = OrderReturn.objects.all()
    counts = cases.aggregate(
        awaiting=Count("pk", filter=Q(receipt_status="awaiting")),
        received=Count("pk", filter=Q(receipt_status="received")),
        not_required=Count("pk", filter=Q(receipt_status="not_required")),
    )
    units = OrderReturnLine.objects.filter(return_case__receipt_status="awaiting").aggregate(total=Sum("expected_quantity"))["total"] or 0
    selected = options.get("returns", "awaiting")
    if selected != "all":
        cases = cases.filter(receipt_status=selected)
    cases = cases.select_related("order").prefetch_related(
        Prefetch("lines", queryset=OrderReturnLine.objects.select_related("order_item").order_by("pk")),
    ).order_by("created_at", "pk")

    def serialize(case):
        lines = list(case.lines.all())
        return {"id": case.pk, "order_number": case.order.order_number, "receipt_status": case.receipt_status,
                "receipt_label": case.get_receipt_status_display(), "disposition_label": case.get_disposition_display(),
                "payment_label": PAYMENT_LABELS.get(case.order.payment_status, "მდგომარეობა უცნობია"),
                "requested_at": case.created_at.isoformat(), "received_at": case.received_at.isoformat() if case.received_at else None,
                "waiting_days": _age(case.created_at, now) if case.receipt_status == "awaiting" else None,
                "expected_units": sum(line.expected_quantity for line in lines),
                "saleable_units": sum(line.saleable_quantity for line in lines),
                "unsaleable_units": sum(line.unsaleable_quantity for line in lines),
                "product_count": len(lines),
                "products": [{"name": line.order_item.product_name, "sku": line.order_item.internal_sku,
                              "quantity": line.expected_quantity} for line in lines[:5]]}

    return {"summary": {**counts, "awaiting_units": units}, "filter": selected,
            **_page(cases, options.get("returns_page", 1), serialize)}


def _stock(options, now):
    # A restored sale allocation no longer consumes its receipt lot.
    consumed = OwnedStockAllocation.objects.filter(lot_id=OuterRef("pk"), restored_at__isnull=True).order_by().values("lot_id").annotate(total=Sum("quantity")).values("total")
    lots = OwnedStockLot.objects.annotate(used=Coalesce(Subquery(consumed), 0)).annotate(remaining=F("quantity") - F("used"))
    invalid = lots.filter(remaining__lt=0).count()
    lots = lots.filter(remaining__gt=0)
    value = ExpressionWrapper(F("remaining") * F("purchase_unit_gross"), output_field=DecimalField(max_digits=24, decimal_places=2))
    summary = lots.aggregate(
        units=Sum("remaining"), products=Count("product_id", distinct=True), lots=Count("pk"),
        known_value_gross=Sum(value), unknown_cost_units=Sum("remaining", filter=Q(purchase_unit_gross__isnull=True)),
    )
    for key in ("units", "products", "lots", "unknown_cost_units"):
        summary[key] = summary[key] or 0
    summary["known_value_gross"] = _money(summary["known_value_gross"] or Decimal("0.00"))
    summary["value_gross"] = None if summary["unknown_cost_units"] or invalid else summary["known_value_gross"]
    summary["invalid_lots"] = invalid
    lots = lots.select_related("product", "return_line__return_case__order").order_by("created_at", "pk")

    def serialize(lot):
        return {"id": lot.pk, "name": lot.product.name, "sku": lot.product.internal_sku or "",
                "order_number": lot.return_line.return_case.order.order_number,
                "received_at": lot.created_at.isoformat(), "age_days": _age(lot.created_at, now),
                "received_units": lot.quantity, "remaining_units": lot.remaining,
                "unit_cost_gross": _money(lot.purchase_unit_gross),
                "value_gross": _money(lot.purchase_unit_gross * lot.remaining) if lot.purchase_unit_gross is not None else None}

    return {"summary": summary, **_page(lots, options.get("stock_page", 1), serialize)}


def _payments(options):
    payments = PaymentTransaction.objects.all()
    summary = payments.aggregate(
        pending=Count("pk", filter=PENDING), failed=Count("pk", filter=Q(status="failed")),
        issues=Count("pk", filter=ISSUES), attention=Count("pk", filter=PENDING | Q(status="failed") | ISSUES),
    )
    selected = options.get("payments", "attention")
    filters = {"attention": PENDING | Q(status="failed") | ISSUES, "pending": PENDING, "failed": Q(status="failed"), "issues": ISSUES}
    payments = payments.filter(filters[selected]).select_related("order").order_by("-updated_at", "-pk")

    def serialize(payment):
        issue = ISSUE_LABELS.get(payment.reconciliation_issue, "შენახულია გადასამოწმებელი ჩანაწერი.") if payment.reconciliation_issue else None
        if payment.status == "paid" and not payment.order_id:
            issue = ISSUE_LABELS["paid_without_order"]
        return {"id": payment.pk, "order_number": payment.order.order_number if payment.order_id else None,
                "action_label": ACTION_LABELS.get(payment.action, "სხვა მოქმედება"), "status": payment.status,
                "status_label": PAYMENT_LABELS.get(payment.status, "მდგომარეობა უცნობია"),
                "amount": _money(payment.amount), "currency": payment.currency,
                "created_at": payment.created_at.isoformat(), "updated_at": payment.updated_at.isoformat(),
                "expires_at": payment.expires_at.isoformat() if payment.expires_at else None,
                "issue": issue,
                "checked_at": payment.reconciliation_attempted_at.isoformat() if payment.reconciliation_attempted_at else None}

    return {"summary": summary, "filter": selected, **_page(payments, options.get("payments_page", 1), serialize)}


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _sync(model, key, label, counters):
    latest = model.objects.order_by("-finished_at", "-pk").first()
    success = model.objects.filter(status="success").order_by("-finished_at", "-pk").values_list("finished_at", flat=True).first()
    result = {"key": key, "label": label, "latest": None, "last_success_at": success.isoformat() if success else None}
    if latest:
        payload = latest.changes if key == "supplier" else latest.details
        payload = payload if isinstance(payload, dict) else {}
        counts = payload if key == "supplier" else payload.get("counts", {})
        counts = counts if isinstance(counts, dict) else {}
        result["latest"] = {
            "status": latest.status, "status_label": latest.get_status_display(),
            "started_at": latest.started_at.isoformat(), "finished_at": latest.finished_at.isoformat(),
            "source_label": latest.get_source_display() if key == "carrier" else None,
            "counts": [{"key": name, "label": text, "value": _count(
                counts.get(name, {}).get("count") if key == "supplier" and isinstance(counts.get(name), dict) else counts.get(name) if key == "carrier" else None,
            )} for name, text in counters.items()],
        }
    return result


def build_operations_report(options=None):
    options = options or {}
    now = timezone.now()
    return {"generated_at": now.isoformat(), "timezone": "Asia/Tbilisi",
            "returns": _returns(options, now), "stock": _stock(options, now), "payments": _payments(options),
            "syncs": [_sync(SupplierSyncReport, "supplier", "Cross Motors", SUPPLIER_COUNTS),
                      _sync(EasywaySyncReport, "carrier", "EasyWay", TRACKING_COUNTS)]}
