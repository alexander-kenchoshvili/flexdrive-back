from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups

from .models import (
    Category,
    Product,
    ProductImage,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)
from .search_cache import invalidate_vehicle_search_catalog


PRODUCT_IMAGE_FILE_FIELDS = (
    "image_original",
    "image_desktop",
    "image_tablet",
    "image_mobile",
    "image_ai_background",
)


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=ProductImage)
def invalidate_catalog_category_cache(**kwargs):
    transaction.on_commit(
        lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
    )


@receiver([post_save, post_delete], sender=VehicleMake)
@receiver([post_save, post_delete], sender=VehicleModel)
@receiver([post_save, post_delete], sender=VehicleEngine)
def invalidate_vehicle_search_cache(**kwargs):
    transaction.on_commit(invalidate_vehicle_search_catalog)


@receiver(post_delete, sender=ProductImage)
def delete_product_image_files_from_storage(instance, **kwargs):
    storage_names = []
    seen = set()

    for field_name in PRODUCT_IMAGE_FILE_FIELDS:
        image_field = getattr(instance, field_name)
        storage_name = str(image_field.name or "")
        if not storage_name:
            continue

        key = (id(image_field.storage), storage_name)
        if key in seen:
            continue

        seen.add(key)
        storage_names.append((image_field.storage, storage_name))

    if not storage_names:
        return

    def storage_name_is_still_used(storage_name):
        return ProductImage.objects.filter(
            Q(image_original=storage_name)
            | Q(image_desktop=storage_name)
            | Q(image_tablet=storage_name)
            | Q(image_mobile=storage_name)
            | Q(image_ai_background=storage_name)
        ).exists()

    def delete_files():
        for storage, storage_name in storage_names:
            if storage_name_is_still_used(storage_name):
                continue
            try:
                storage.delete(storage_name)
            except Exception:
                continue

    transaction.on_commit(delete_files)
