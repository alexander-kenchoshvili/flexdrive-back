"""Own-first inventory allocation. All stock writers serialize on Product rows.

Checkout reservations reserve the COMBINED available quantity. They do not promise
a physical source or cost layer to a customer. The final sale chooses FIFO owned
lots then external stock and records the actual cost without changing sale prices.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from catalog.models import Product, ProductSupplierSource
from .models import OrderItemInventory, OwnedStockAllocation, OwnedStockLot


def inventory_changed():
    from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups
    from catalog.search_cache import invalidate_vehicle_search_catalog

    def invalidate():
        invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
        invalidate_vehicle_search_catalog()
    transaction.on_commit(invalidate)


@transaction.atomic
def consume_order_inventory(*, order, allow_safety_reserve=False):
    """Called inside the checkout transaction, after its reservation checks.

    The verified paid callback retains the existing ability to use the external
    safety margin after a supplier count drops. Direct checkout cannot use it.
    """
    items = list(order.items.order_by("product_id", "pk"))
    if not items or any(item.product_id is None for item in items):
        raise ValidationError("შეკვეთის პროდუქტი ვეღარ მოიძებნა.")
    product_ids = sorted({item.product_id for item in items})
    products = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")}
    if set(products) != set(product_ids):
        raise ValidationError("შეკვეთის პროდუქტი ვეღარ მოიძებნა.")
    existing = OrderItemInventory.objects.filter(order_item__order=order).count()
    if existing:
        if existing == len(items):
            return
        raise ValidationError("შეკვეთის მარაგის აღრიცხვა არასრულია.")

    for item in items:
        product = products[item.product_id]
        available = (product.owned_stock_qty + product.stock_qty
                     if allow_safety_reserve else product.customer_available_stock_qty)
        if item.quantity > available:
            raise ValidationError("პროდუქტის ხელმისაწვდომი რაოდენობა შეიცვალა.")
        remaining = item.quantity
        plans = []
        lots = OwnedStockLot.objects.filter(product=product).annotate(
            consumed=Sum("allocations__quantity", filter=Q(allocations__restored_at__isnull=True)),
        ).order_by("created_at", "pk")
        for lot in lots:
            free = lot.quantity - (lot.consumed or 0)
            take = min(remaining, free)
            if take > 0:
                plans.append((lot, take))
                remaining -= take
            if remaining == 0:
                break
        owned = sum(qty for _, qty in plans)
        if owned != min(product.owned_stock_qty, item.quantity):
            raise ValidationError("საკუთარი მარაგის ნაშთი ისტორიას არ ემთხვევა.")
        costs = [(lot.purchase_unit_gross, qty) for lot, qty in plans]
        if remaining:
            costs.append((item.purchase_unit_gross, remaining))
        total = (None if any(cost is None for cost, _ in costs)
                 else sum((cost * qty for cost, qty in costs), Decimal("0.00")))
        record = OrderItemInventory.objects.create(
            order_item=item, external_quantity=remaining,
            external_source=product.supplier_source, purchase_total_gross=total,
        )
        OwnedStockAllocation.objects.bulk_create([
            OwnedStockAllocation(inventory=record, lot=lot, quantity=qty) for lot, qty in plans
        ])
        product.owned_stock_qty -= owned
        product.stock_qty -= remaining
        Product.objects.filter(pk=product.pk).update(
            owned_stock_qty=product.owned_stock_qty, stock_qty=product.stock_qty, updated_at=timezone.now(),
        )
    from .supplier_stock import create_supplier_stock_holds_for_order
    create_supplier_stock_holds_for_order(order=order)
    inventory_changed()


def restore_allocated_inventory(*, order):
    """Existing pre-dispatch cancellation only; caller holds order/product locks.

    Returns manual external quantities. Supplier quantities restore through their
    holds, owned quantities restore their original allocations exactly once.
    """
    manual = {}
    now = timezone.now()
    for item in order.items.select_related("inventory", "product").order_by("product_id", "pk"):
        try:
            record = item.inventory
        except OrderItemInventory.DoesNotExist:
            # Unallocated test/older orders retain their existing restoration path.
            if item.product.supplier_source != ProductSupplierSource.CROSS_MOTORS:
                manual[item.product_id] = manual.get(item.product_id, 0) + item.quantity
            continue
        allocations = list(record.allocations.filter(restored_at__isnull=True))
        quantity = sum(row.quantity for row in allocations)
        if quantity:
            OwnedStockAllocation.objects.filter(pk__in=[a.pk for a in allocations]).update(restored_at=now)
            Product.objects.filter(pk=item.product_id).update(owned_stock_qty=F("owned_stock_qty") + quantity)
            Product.objects.filter(
                pk=item.product_id, status="archived", supplier_missing=True, owned_stock_qty__gt=0,
            ).exclude(internal_sku__isnull=True).exclude(internal_sku="").update(status="published")
        if record.external_source != ProductSupplierSource.CROSS_MOTORS:
            manual[item.product_id] = manual.get(item.product_id, 0) + record.external_quantity
    inventory_changed()
    return [{"product_id": product_id, "quantity": qty} for product_id, qty in manual.items() if qty]
