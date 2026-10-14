"""Keep the visible OEM specification aligned with the product's part number."""

from django.utils import timezone

from .models import ProductSpec


def is_oem_key(key):
    return str(key or "").strip().casefold() == "oem"


def sync_oem_specs(products, *, batch_size=1000):
    # Callers hold product locks. Do this in batches for the bulk supplier import.
    products = {product.pk: product for product in products}
    if not products:
        return {"created": 0, "updated": 0}
    existing = list(
        ProductSpec.objects.filter(product_id__in=products, key__iexact="OEM")
    )
    now = timezone.now()
    seen = set()
    updated = []
    deleted = []
    for spec in existing:
        seen.add(spec.product_id)
        value = products[spec.product_id].manufacturer_part_number
        if not value:
            deleted.append(spec.pk)
        elif spec.value != value:
            spec.value = value
            spec.updated_at = now
            updated.append(spec)
    created = [
        ProductSpec(product=product, key="OEM", value=product.manufacturer_part_number, sort_order=1)
        for product in products.values()
        if product.manufacturer_part_number and product.pk not in seen
    ]
    if deleted:
        ProductSpec.objects.filter(pk__in=deleted).delete()
    if updated:
        ProductSpec.objects.bulk_update(updated, ["value", "updated_at"], batch_size=batch_size)
    if created:
        ProductSpec.objects.bulk_create(created, batch_size=batch_size)
    return {"created": len(created), "updated": len(updated)}
