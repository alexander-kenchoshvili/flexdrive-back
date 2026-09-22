"""Copy Cloudinary image references by SKU, without downloading/uploading files."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups
from common.storage_backends import CloudinaryMediaStorage
from catalog.models import Product, ProductImage


FILE_FIELDS = (
    "image_original", "image_desktop", "image_tablet", "image_mobile", "image_ai_background",
)
IMAGE_FIELDS = FILE_FIELDS + (
    "use_ai_background", "alt_text", "is_primary", "sort_order", "crop_x", "crop_y",
    "crop_width", "crop_height", "image_padding", "replace_background_with_white",
)


def require_shared_cloudinary():
    if not settings.USE_CLOUDINARY_MEDIA or not settings.CLOUDINARY_SHARED_MEDIA:
        raise ValueError("This transfer requires USE_CLOUDINARY_MEDIA=True and CLOUDINARY_SHARED_MEDIA=True.")
    if not isinstance(ProductImage._meta.get_field("image_original").storage, CloudinaryMediaStorage):
        raise ValueError("Product images must use Cloudinary storage, not local filesystem paths.")


def image_values(image):
    result = {}
    for name in IMAGE_FIELDS:
        value = getattr(image, name)
        if name in FILE_FIELDS:
            value = str(value or "")
        result[name] = value
    return result


def export_snapshot():
    require_shared_cloudinary()
    products = {}
    for image in ProductImage.objects.select_related("product").order_by("product__sku", "sort_order", "pk"):
        products.setdefault(image.product.sku, []).append(image_values(image))
    return {
        "version": 1,
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
        "exported_at": timezone.now().isoformat(),
        "products": products,
    }


def validate_snapshot(snapshot):
    require_shared_cloudinary()
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise ValueError("Unsupported product-image snapshot format.")
    if snapshot.get("cloud_name") != settings.CLOUDINARY_CLOUD_NAME:
        raise ValueError("Source and destination must use the same Cloudinary cloud name.")
    products = snapshot.get("products")
    if not isinstance(products, dict) or not products:
        raise ValueError("Snapshot has no image products.")
    validated = {}
    for sku, rows in products.items():
        if not isinstance(sku, str) or not sku.strip() or len(sku) > 64:
            raise ValueError("Snapshot contains an invalid SKU.")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{sku}: expected a non-empty image list.")
        validated[sku] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(IMAGE_FIELDS):
                raise ValueError(f"{sku}: unexpected or missing image fields.")
            values = {}
            for name, value in row.items():
                field = ProductImage._meta.get_field(name)
                if name in FILE_FIELDS:
                    if not isinstance(value, str) or len(value) > field.max_length:
                        raise ValueError(f"{sku}: invalid {name} path.")
                    if value and (":" in value or "\\" in value or value.startswith("/")
                                  or any(part in ("", ".", "..") for part in value.split("/"))):
                        raise ValueError(f"{sku}: expected a Cloudinary storage name in {name}, not a URL/local path.")
                    values[name] = value
                else:
                    values[name] = field.clean(value, None)
            if not any(values[name] for name in FILE_FIELDS[:4]):
                raise ValueError(f"{sku}: image row has no usable image.")
            if values["use_ai_background"] and not values["image_ai_background"]:
                raise ValueError(f"{sku}: AI background enabled without its image.")
            validated[sku].append(values)
        if sum(row["is_primary"] for row in validated[sku]) > 1:
            raise ValueError(f"{sku}: multiple primary images.")
    return validated


@transaction.atomic
def import_snapshot(snapshot, *, commit=False, skip_missing=False):
    rows_by_sku = validate_snapshot(snapshot)
    products = {
        product.sku: product
        for product in Product.objects.select_for_update().filter(sku__in=rows_by_sku).order_by("pk")
    }
    missing = sorted(set(rows_by_sku) - set(products))
    if missing and not skip_missing:
        raise ValueError("Destination SKUs missing (nothing changed): " + ", ".join(missing))
    existing = {}
    for image in ProductImage.objects.filter(product_id__in=[p.pk for p in products.values()]).select_related("product").order_by("sort_order", "pk"):
        existing.setdefault(image.product.sku, []).append(image_values(image))
    new_images = []
    unchanged = 0
    for sku, product in products.items():
        desired = sorted(rows_by_sku[sku], key=lambda row: row["sort_order"])
        if sku in existing:
            if existing[sku] != desired:
                raise ValueError(f"{sku}: destination already has different images; refusing to replace them.")
            unchanged += 1
            continue
        new_images.extend(ProductImage(product=product, **row) for row in desired)
    if commit and new_images:
        # Avoid ProductImage.save(): the variants already exist in Cloudinary.
        ProductImage.objects.bulk_create(new_images, batch_size=500)
        transaction.on_commit(lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES))
    return {
        "products_to_add": len(products) - unchanged,
        "images_to_add": len(new_images),
        "unchanged_products": unchanged,
        "missing_skus": missing,
    }
