"""Pending manual review of supplier cost changes."""

from django.db import transaction
from django.utils import timezone

from .models import Product, SupplierPriceReview


def record_supplier_price_change(product, previous_price, current_price):
    """Keep one pending row per product while retaining the first observed cost."""
    if previous_price == current_price:
        return
    review, created = SupplierPriceReview.objects.get_or_create(
        product=product,
        defaults={
            "previous_supplier_price": previous_price,
            "latest_supplier_price": current_price,
        },
    )
    if not created:
        review.latest_supplier_price = current_price
        review.latest_changed_at = timezone.now()
        review.save(update_fields=["latest_supplier_price", "latest_changed_at"])


@transaction.atomic
def resolve_supplier_price_review(product_id):
    """A reviewed product may sell again only above its current supplier cost."""
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.supplier_price is None or product.price <= product.supplier_price:
        return False
    SupplierPriceReview.objects.filter(product_id=product_id).delete()
    Product.objects.filter(pk=product_id).update(supplier_price_review_pending=False)
    return True
