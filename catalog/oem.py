"""OEM specification synchronization and whitespace-tolerant code matching."""

import re
import unicodedata

from django.utils import timezone

from .models import ProductSpec


_OEM_SPACING_CHARACTERS = (
    "\u00a0\u1680"
    + "".join(chr(codepoint) for codepoint in range(0x2000, 0x200B))
    + "\u2028\u2029\u202f\u205f\u3000\u200b\ufeff\u2060"
)


def oem_search_patterns(query):
    code = unicodedata.normalize("NFKC", str(query or "")).casefold()
    for invisible in ("\u200b", "\ufeff", "\u2060"):
        code = code.replace(invisible, "")
    code = re.sub(r"\s+", "", code)
    if (
        not code
        or len(code) > 120
        or not re.fullmatch(r"[a-z0-9._-]+", code)
        or not re.search(r"[a-z0-9]", code)
    ):
        return None
    # Explicit Unicode spacing covers copied OEMs regardless of the DB locale.
    # Escape each code character: user input must never become a regex operator.
    gap = r"[\s" + _OEM_SPACING_CHARACTERS + "]*"
    pattern = gap.join(re.escape(char) for char in code)
    return {"contains": pattern, "exact": f"^{gap}{pattern}{gap}$", "prefix": f"^{gap}{pattern}"}


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
