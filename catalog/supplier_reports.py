"""Small, credential-free summaries of committed supplier changes."""

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from catalog.models import CUSTOMER_STOCK_RESERVE_QTY, Product, ProductImage, ProductStatus, SupplierSyncReport


CHANGE_LABELS = {
    "new": "ახალი პროდუქტები — Draft",
    "out_of_stock": "მარაგი ამოეწურა",
    "back_in_stock": "მარაგში დაბრუნდა",
    "back_in_stock_without_image": "მარაგში დაბრუნდა, სურათი არ აქვს",
    "archived": "დაარქივდა",
    "restored": "არქივიდან გამოქვეყნდა",
    "supplier_price": "მომწოდებლის ფასი შეიცვალა",
    "oem_added": "OEM დაემატა",
    "oem_changed": "OEM შეიცვალა",
    "oem_removed": "OEM წაიშალა",
}
DETAIL_LIMIT = 50


def supplier_snapshot(*, lock=False):
    images = ProductImage.objects.filter(product_id=OuterRef("pk")).filter(
        Q(image_original__gt="") | Q(image_desktop__gt="")
        | Q(image_tablet__gt="") | Q(image_mobile__gt="")
    )
    products = Product.objects.filter(sku__startswith="CM-").annotate(
        has_image=Exists(images),
    ).order_by("pk")
    if lock:
        products = products.select_for_update()
    return {
        row["sku"]: row
        for row in products.values(
            "sku", "internal_sku", "name", "status", "stock_qty", "supplier_price",
            "manufacturer_part_number", "has_image",
        )
    }


def create_success_report(*, started_at, before, after):
    changes = {key: {"count": 0, "items": []} for key in CHANGE_LABELS}

    def add(key, row, **detail):
        group = changes[key]
        group["count"] += 1
        # This is a photo-upload work list, so retain every affected product.
        if key == "back_in_stock_without_image" or len(group["items"]) < DETAIL_LIMIT:
            group["items"].append({"sku": row["sku"], "internal_sku": row.get("internal_sku") or "", "name": row["name"], **detail})

    for sku, row in sorted(after.items()):
        old = before.get(sku)
        if old is None:
            add("new", row)
            continue
        if old["status"] != ProductStatus.ARCHIVED and row["status"] == ProductStatus.ARCHIVED:
            add("archived", row)
        if old["status"] == ProductStatus.ARCHIVED and row["status"] == ProductStatus.PUBLISHED:
            add("restored", row)
        was_available = old["status"] == ProductStatus.PUBLISHED and old["stock_qty"] > CUSTOMER_STOCK_RESERVE_QTY
        available = row["status"] == ProductStatus.PUBLISHED and row["stock_qty"] > CUSTOMER_STOCK_RESERVE_QTY
        if not was_available and available and row.get("has_image") is False:
            add("back_in_stock_without_image", row)
        if old["status"] == row["status"] == ProductStatus.PUBLISHED:
            if was_available and not available:
                add("out_of_stock", row)
            elif not was_available and available:
                add("back_in_stock", row)
        if old["supplier_price"] != row["supplier_price"]:
            add(
                "supplier_price", row,
                before=str(old["supplier_price"]) if old["supplier_price"] is not None else "—",
                after=str(row["supplier_price"]) if row["supplier_price"] is not None else "—",
            )
        old_oem = old.get("manufacturer_part_number") or ""
        new_oem = row.get("manufacturer_part_number") or ""
        if old_oem != new_oem:
            key = "oem_added" if not old_oem else "oem_removed" if not new_oem else "oem_changed"
            add(key, row, before=old_oem or "—", after=new_oem or "—")

    summary = "; ".join(
        f"{label}: {changes[key]['count']}"
        for key, label in CHANGE_LABELS.items() if changes[key]["count"]
    ) or "სინქრონიზაცია დასრულდა, მნიშვნელოვანი ცვლილებები არ არის."
    return SupplierSyncReport.objects.create(
        started_at=started_at, finished_at=timezone.now(),
        status=SupplierSyncReport.Status.SUCCESS, summary=summary, changes=changes,
    )
