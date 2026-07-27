from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Product, ProductSupplierSource

from .models import (
    Order,
    SupplierStockHold,
    SupplierStockHoldStatus,
)


def calculate_effective_supplier_stock(*, supplier_stock_qty, active_hold_quantity):
    return max(int(supplier_stock_qty or 0) - int(active_hold_quantity or 0), 0)


def get_active_supplier_hold_quantities(*, product_ids, now=None):
    product_ids = list(product_ids)
    if not product_ids:
        return {}

    now = now or timezone.now()
    rows = (
        SupplierStockHold.objects.filter(
            product_id__in=product_ids,
            status=SupplierStockHoldStatus.ACTIVE,
            expires_at__gt=now,
        )
        .values("product_id")
        .annotate(total_quantity=Sum("quantity"))
    )
    return {
        row["product_id"]: row["total_quantity"] or 0
        for row in rows
    }


@transaction.atomic
def create_supplier_stock_holds_for_order(*, order, now=None):
    now = now or timezone.now()
    hold_expires_at = now + timedelta(
        seconds=settings.CROSSMOTORS_SALE_HOLD_SECONDS
    )
    order_items = list(
        order.items.select_related("product")
        .filter(
            product__supplier_source=ProductSupplierSource.CROSS_MOTORS,
        )
        .order_by("product_id", "id")
    )
    if not order_items:
        return []

    product_ids = sorted({item.product_id for item in order_items})
    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    }

    holds = []
    for order_item in order_items:
        product = products[order_item.product_id]
        hold, _ = SupplierStockHold.objects.get_or_create(
            order_item=order_item,
            defaults={
                "product": product,
                "quantity": order_item.quantity,
                "supplier_stock_at_sale": product.supplier_stock_qty,
                "expires_at": hold_expires_at,
            },
        )
        holds.append(hold)
    return holds


def expire_supplier_stock_holds(*, now=None, product_ids=None):
    now = now or timezone.now()
    queryset = SupplierStockHold.objects.filter(
        status=SupplierStockHoldStatus.ACTIVE,
        expires_at__lte=now,
    )
    if product_ids is not None:
        queryset = queryset.filter(product_id__in=list(product_ids))
    return queryset.update(
        status=SupplierStockHoldStatus.EXPIRED,
        released_at=now,
        release_note="დროებითი დაცვის ვადა ავტომატურად დასრულდა.",
        updated_at=now,
    )


def _recalculate_locked_cross_motors_products(products, *, now):
    products = list(products)
    active_quantities = get_active_supplier_hold_quantities(
        product_ids=[product.pk for product in products],
        now=now,
    )
    changed = []
    for product in products:
        if (
            product.supplier_source != ProductSupplierSource.CROSS_MOTORS
            or product.supplier_stock_qty is None
        ):
            continue
        effective_stock = calculate_effective_supplier_stock(
            supplier_stock_qty=product.supplier_stock_qty,
            active_hold_quantity=active_quantities.get(product.pk, 0),
        )
        if product.stock_qty == effective_stock:
            continue
        product.stock_qty = effective_stock
        product.updated_at = now
        changed.append(product)
    if changed:
        Product.objects.bulk_update(changed, ["stock_qty", "updated_at"])
    return changed


@transaction.atomic
def release_supplier_stock_hold(
    *,
    hold,
    released_by=None,
    note="",
    status=SupplierStockHoldStatus.MANUALLY_RELEASED,
    now=None,
):
    now = now or timezone.now()
    locked_hold = (
        SupplierStockHold.objects.select_for_update()
        .select_related("product", "order_item__order")
        .get(pk=hold.pk)
    )
    if locked_hold.status != SupplierStockHoldStatus.ACTIVE:
        return locked_hold, False

    product = Product.objects.select_for_update().get(pk=locked_hold.product_id)
    locked_hold.status = status
    locked_hold.released_at = now
    locked_hold.released_by = released_by
    locked_hold.release_note = str(note or "").strip()[:500]
    locked_hold.save(
        update_fields=[
            "status",
            "released_at",
            "released_by",
            "release_note",
            "updated_at",
        ]
    )
    _recalculate_locked_cross_motors_products([product], now=now)
    return locked_hold, True


@transaction.atomic
def release_order_supplier_stock_holds(*, order, now=None):
    now = now or timezone.now()
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    holds = list(
        SupplierStockHold.objects.select_for_update()
        .filter(
            order_item__order=locked_order,
            status=SupplierStockHoldStatus.ACTIVE,
        )
        .order_by("product_id", "id")
    )
    product_ids = sorted({hold.product_id for hold in holds})
    products = list(
        Product.objects.select_for_update()
        .filter(
            pk__in=product_ids,
            supplier_source=ProductSupplierSource.CROSS_MOTORS,
        )
        .order_by("pk")
    )
    if holds:
        SupplierStockHold.objects.filter(pk__in=[hold.pk for hold in holds]).update(
            status=SupplierStockHoldStatus.ORDER_CANCELLED,
            released_at=now,
            release_note="შეკვეთა გაუქმდა ან თანხა სრულად დაბრუნდა.",
            updated_at=now,
        )
    _recalculate_locked_cross_motors_products(products, now=now)
    return product_ids
