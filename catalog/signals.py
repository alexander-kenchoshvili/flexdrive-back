from django.db import transaction
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
