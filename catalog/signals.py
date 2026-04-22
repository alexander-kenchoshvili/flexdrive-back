from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups

from .models import Category, Product, ProductImage


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=ProductImage)
def invalidate_catalog_category_cache(**kwargs):
    invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
