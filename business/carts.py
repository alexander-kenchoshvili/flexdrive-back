"""Private current cart contents. A snapshot is not addition history."""
from django.core.paginator import Paginator
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Exists, Max, Min, OuterRef, Prefetch, Q, Sum
from django.db.models.functions import Greatest
from django.utils import timezone

from commerce.models import Cart, CartItem, PaymentTransaction
from .models import CartAddition


def build_cart_report(period, values):
    if values.get("view") in ("additions", "products"):
        return _addition_report(period, values)
    lower, upper = period.bounds
    query = Cart.objects.filter(is_active=True).annotate(
        report_item_count=Count("items"), units=Sum("items__quantity", default=0),
        last_change=Greatest("updated_at", Max("items__updated_at")),
    ).filter(report_item_count__gt=0, last_change__gte=lower, last_change__lt=upper)
    term = values.get("q", "")
    if term:
        matching = CartItem.objects.filter(cart_id=OuterRef("pk")).filter(
            Q(product__name__icontains=term) | Q(product__internal_sku__icontains=term))
        query = query.filter(Exists(matching))
    query = query.order_by("-last_change", "-pk").prefetch_related(Prefetch(
        "items", queryset=CartItem.objects.select_related("product").order_by("pk")[:5], to_attr="preview_items"))
    page = Paginator(query, 20).get_page(values.get("page", 1))
    rows = [{"id": cart.pk, "owner": "ანგარიშის კალათა" if cart.user_id else "სტუმრის კალათა — ვინაობა უცნობია",
             "updated_at": cart.last_change.isoformat(), "products": cart.report_item_count, "units": cart.units,
             "items": [{"name": item.product.name, "sku": item.product.internal_sku or "",
                        "quantity": item.quantity} for item in cart.preview_items],
             "remaining": max(0, cart.report_item_count - len(cart.preview_items))} for cart in page.object_list]
    return {"status": "ready", "view": "contents", "source": "shop", "timezone": "Asia/Tbilisi",
            "period": {"start": str(period.start), "end": str(period.end)}, "rows": rows,
            "total": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages,
            "generated_at": timezone.now().isoformat(),
            "note": "მოქმედი არაცარიელი კალათების მიმდინარე შიგთავსი. პერიოდი ბოლო შენახული ცვლილების დროით იფილტრება; წარსულში წაშლილი პროდუქტების ისტორია არ არის."}


def _later_orders(events):
    """One bounded read. Exact saved cart/item/price, within 24h; no person inference."""
    cart_ids = {event.cart_id for event in events if event.cart_id}
    if not cart_ids:
        return {}, False
    candidates = list(PaymentTransaction.objects.filter(
        action="sale", order__isnull=False, captured_at__isnull=False,
        created_at__gte=min(event.created_at for event in events),
        created_at__lt=max(event.created_at for event in events) + timedelta(hours=24),
        checkout_snapshot__source="cart",
        checkout_snapshot__source_reference__cart_id__in=cart_ids,
    ).select_related("order").order_by("created_at", "pk")[:401])
    result = {}
    for event in events:
        for payment in candidates[:400]:
            if not (event.created_at <= payment.created_at < event.created_at + timedelta(hours=24)
                    and event.created_at <= payment.captured_at < event.created_at + timedelta(hours=24)):
                continue
            snapshot = payment.checkout_snapshot
            reference = snapshot.get("source_reference")
            items = snapshot.get("items")
            if (not isinstance(reference, dict) or reference.get("cart_id") != event.cart_id
                    or not isinstance(items, list)):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    match = (item.get("source_item_id") == event.source_item_id
                             and item.get("product_id") == event.product_id
                             and type(item.get("quantity")) is int and item["quantity"] >= event.quantity
                             and Decimal(str(item.get("unit_price"))) == event.unit_price)
                except (InvalidOperation, ValueError, TypeError):
                    match = False
                if match:
                    result[event.pk] = {"order_number": payment.order.order_number,
                                        "at": payment.captured_at.isoformat()}
                    break
            if event.pk in result:
                break
    return result, len(candidates) > 400


def _addition_report(period, values):
    lower, upper = period.bounds
    events = CartAddition.objects.filter(created_at__gte=lower, created_at__lt=upper)
    term = values.get("q", "")
    if term:
        events = events.filter(Q(name__icontains=term) | Q(sku__icontains=term))
    totals = events.aggregate(additions=Count("pk"), units=Sum("quantity", default=0), carts=Count("cart_key", distinct=True))
    first = CartAddition.objects.aggregate(at=Min("created_at"))["at"]
    mode = values.get("view", "additions")
    linked, limited = {}, False
    if mode == "products":
        query = events.values("product_id", "sku", "name").annotate(
            additions=Count("pk"), units=Sum("quantity"), carts=Count("cart_key", distinct=True),
            last_at=Max("created_at")).order_by("-additions", "sku", "name", "product_id")
    else:
        query = events.order_by("-created_at", "-pk")
    page = Paginator(query, 20).get_page(values.get("page", 1))
    selected = list(page.object_list)
    if mode == "products":
        rows = [{**row, "last_at": row["last_at"].isoformat()} for row in selected]
    else:
        linked, limited = _later_orders(selected)
        rows = [{"id": event.pk, "at": event.created_at.isoformat(), "sku": event.sku,
                 "name": event.name, "quantity": event.quantity,
                 "later_order": linked.get(event.pk)} for event in selected]
    return {"status": "ready", "source": "shop", "view": mode, "timezone": "Asia/Tbilisi",
            "period": {"start": str(period.start), "end": str(period.end)},
            "generated_at": timezone.now().isoformat(), "first_recorded_at": first.isoformat() if first else None,
            "rows": rows, "totals": totals, "total": page.paginator.count,
            "page": page.number, "pages": page.paginator.num_pages, "links_limited": limited,
            "note": "მხოლოდ ახალი, თანხმობით აღრიცხული წარმატებული დამატებები; რაოდენობის შესწორება დამატება არ არის. ძველი ისტორია არ აღდგება. კალათები ადამიანებს არ უდრის. მოგვიანებით შეძენის მითითება მხოლოდ იმავე კალათის/პროდუქტის შენახული ბანკის ჩანაწერით, 24 საათში მოწმდება; უცნობი კავშირი დაკარგულ გაყიდვას არ ნიშნავს."}
