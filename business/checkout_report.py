"""Private checkout diagnostics from saved observations and bank transactions."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.core.paginator import Paginator
from django.utils import timezone

from catalog.models import Product
from commerce.models import PaymentTransaction

from .checkout_progress import SOURCES, STAGE_LABELS, basket_key
from .models import CheckoutProgress
from .payment_attempts import DELIVERY_LABELS, WINDOW, _amount, _dict, _identity, checkout_summary, failure_reason


MAX_RECORDS = 2500
PAGE_SIZE = 20
MAX_STEPS = 40
RESULT_LABELS = {
    "open": "გაფორმება ჯერ მიმდინარეობს",
    "before_bank": "ბანკამდე შეჩერდა",
    "bank_pending": "ბანკის შედეგი მოლოდინშია",
    "bank_issue": "გადახდა ვერ დასრულდა",
    "paid": "გადახდილია",
    "paid_later": "მოგვიანებით გადაიხადა",
}
ERROR_STAGES = {"quote_error", "form_invalid", "price_changed", "stock_changed", "submit_unconfirmed"}


@dataclass
class CheckoutCase:
    started_at: datetime
    source: str
    items: list | tuple
    observed: list = field(default_factory=list)
    attempts: list = field(default_factory=list)
    paid_at: datetime | None = None


def _snapshot_items(payment):
    items = _dict(payment.checkout_snapshot).get("items")
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        item = _dict(item)
        product, quantity, price = item.get("product_id"), item.get("quantity"), _amount(item.get("unit_price"))
        if type(product) is int and product > 0 and type(quantity) is int and quantity > 0 and price is not None:
            result.append((product, quantity, price))
    return result


def _cases(observations, payments):
    records = [(row.created_at, 0, row.pk, row.basket_key, row.source, row.items, row) for row in observations]
    for payment in payments:
        identity = _identity(payment, max_items=None)
        items = identity[3] if identity else _snapshot_items(payment)
        if items:
            source = identity[1] if identity else _dict(payment.checkout_snapshot).get("source")
            key = basket_key(identity) if identity else f"payment:{payment.pk}"
            known_source = source if isinstance(source, str) and source in SOURCES else ""
            records.append((payment.created_at, 1, payment.pk, key, known_source, items, payment))
    latest, cases = {}, []
    for time, kind, _, key, source, items, row in sorted(records):
        case = latest.get(key)
        if case is None or time >= case.started_at + WINDOW or (case.paid_at and time > case.paid_at):
            case = latest[key] = CheckoutCase(time, source, items)
            cases.append(case)
        if kind:
            case.attempts.append(row)
            if row.order_id and row.captured_at and case.paid_at is None:
                case.paid_at = row.captured_at
        else:
            case.observed.append(row)
    return cases


def _payment_result(payment):
    if payment.order_id and payment.captured_at:
        return "გადახდა დადასტურდა"
    if payment.status in {"pending", "authorized"}:
        return "გადახდა მოლოდინშია" if payment.provider_order_id else "ბანკის პასუხი ჯერ ვერ დადასტურდა"
    if payment.status == "cancelled":
        return "გადახდის მცდელობა გაუქმდა"
    reason = failure_reason(payment)
    return reason["label"] if reason else "გადახდის შედეგი ვერ დადასტურდა"


def _outcome(case, now):
    if case.paid_at:
        retried = any(row.status in {"failed", "cancelled"} and row.created_at < case.paid_at for row in case.attempts)
        resolved_blocker = any(row.stage in ERROR_STAGES and row.created_at < case.paid_at for row in case.observed)
        return ("paid_later" if retried or resolved_blocker else "paid"), None
    if case.attempts:
        last = case.attempts[-1]
        if last.status in {"pending", "authorized"}:
            return "bank_pending", None
        return "bank_issue", _payment_result(last)
    last = case.observed[-1]
    reason = STAGE_LABELS.get(last.stage) if last.stage in ERROR_STAGES else None
    return ("open" if now < last.created_at + WINDOW else "before_bank"), reason


def _timeline(case):
    steps = [{"at": row.created_at, "label": STAGE_LABELS.get(row.stage, "გაფორმების ნაბიჯი"),
              "kind": "issue" if row.stage in ERROR_STAGES else "step",
              "delivery": _amount(row.delivery_amount), "service": DELIVERY_LABELS.get(row.delivery_service)}
             for row in case.observed]
    for payment in case.attempts:
        started = "გადახდის მოთხოვნა ბანკში შეიქმნა" if payment.provider_order_id else "გადახდის დაწყების მოთხოვნა დამუშავდა"
        steps.append({"at": payment.created_at, "label": started, "kind": "step", "checkout": checkout_summary(payment)})
        steps.append({"at": payment.captured_at or payment.updated_at, "label": _payment_result(payment),
                      "kind": "issue" if payment.status in {"failed", "cancelled"} else "step"})
    steps.sort(key=lambda step: step["at"])
    return [{**step, "at": step["at"].isoformat()} for step in steps[-MAX_STEPS:]], len(steps) > MAX_STEPS


def _case_payload(entry, product_id):
    case, result, reason = entry
    steps, limited = _timeline(case)
    item = next(item for item in case.items if item[0] == product_id)
    return {"started_at": case.started_at.isoformat(), "source": SOURCES.get(case.source, "გზა უცნობია"),
            "quantity": item[1], "unit_price": item[2], "result": result, "label": RESULT_LABELS[result],
            "reason": reason, "steps": steps, "steps_limited": limited, "payment_attempts": len(case.attempts),
            "has_checkout_steps": bool(case.observed),
            "basket_subtotal": format(sum(Decimal(price) * quantity for _, quantity, price in case.items), ".2f")}


def build_checkout_report(period, options):
    lower, upper = period.bounds
    now = timezone.now()
    window = {"created_at__gte": lower - WINDOW, "created_at__lt": min(upper + WINDOW, now)}
    observations = list(CheckoutProgress.objects.filter(**window).order_by("-created_at", "-pk")[:MAX_RECORDS + 1])
    payments = list(PaymentTransaction.objects.filter(**window, provider="bog", action="sale", currency="GEL")
                    .only("created_at", "updated_at", "status", "amount", "currency", "checkout_snapshot", "provider",
                          "action", "provider_order_id", "provider_reference", "order_id", "captured_at")
                    .order_by("-created_at", "-pk")[:MAX_RECORDS + 1])
    products = defaultdict(list)
    for case in _cases(observations[:MAX_RECORDS], payments[:MAX_RECORDS]):
        if lower <= case.started_at < upper:
            result, reason = _outcome(case, now)
            for product_id in {item[0] for item in case.items}:
                products[product_id].append((case, result, reason))

    query = options["q"].casefold()
    selected = options.get("product_id")
    names = Product.objects.filter(pk__in=products).only("id", "name", "sku", "internal_sku").in_bulk()
    rows = []
    for product_id, cases in products.items():
        product = names.get(product_id)
        name = (product.name or f"პროდუქტი #{product_id}") if product else f"პროდუქტი #{product_id}"
        sku = (product.display_sku or product.sku) if product else ""
        if query and not any(query in (value or "").casefold() for value in (name, sku, product.sku if product else "")):
            continue
        matching = sum(options["result"] in {"all", entry[1]} for entry in cases)
        if not matching:
            continue
        counts = {key: sum(entry[1] == key for entry in cases) for key in RESULT_LABELS}
        rows.append({"id": product_id, "name": name, "sku": sku, "started": len(cases), "counts": counts,
                     "unfinished": counts["before_bank"] + counts["bank_issue"], "matching": matching})
    rows.sort(key=lambda row: (-row["unfinished"], -row["matching"], row["name"], row["id"]))
    page = Paginator(rows, PAGE_SIZE).get_page(options["page"])
    report = {"period": {"start": str(period.start), "end": str(period.end)}, "products": list(page),
              "page": page.number, "pages": page.paginator.num_pages,
              "limited": max(len(observations), len(payments)) > MAX_RECORDS, "detail": None}
    if selected is not None and any(row["id"] == selected for row in page):
        entries = [entry for entry in reversed(products[selected]) if options["result"] in {"all", entry[1]}]
        detail = Paginator(entries, PAGE_SIZE).get_page(options["case_page"])
        report["detail"] = {"id": selected, "page": detail.number, "pages": detail.paginator.num_pages,
                            "cases": [_case_payload(entry, selected) for entry in detail]}
    return report
