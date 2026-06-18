from django.conf import settings
from django.core.cache import cache

from .models import VehicleEngine, VehicleMake, VehicleModel


VEHICLE_SEARCH_CACHE_KEY = "catalog:vehicle-search-catalog:v1"


def get_vehicle_search_catalog():
    cached_catalog = cache.get(VEHICLE_SEARCH_CACHE_KEY)
    if cached_catalog is not None:
        return cached_catalog

    catalog = {
        "makes": list(
            VehicleMake.objects.filter(is_active=True)
            .order_by("sort_order", "name", "id")
            .values("id", "name", "slug")
        ),
        "models": list(
            VehicleModel.objects.filter(is_active=True, make__is_active=True)
            .order_by(
                "make__sort_order",
                "make__name",
                "sort_order",
                "name",
                "id",
            )
            .values("id", "make_id", "name", "slug")
        ),
        "engines": list(
            VehicleEngine.objects.filter(
                is_active=True,
                model__is_active=True,
                model__make__is_active=True,
            )
            .order_by(
                "model__make__sort_order",
                "model__make__name",
                "model__sort_order",
                "model__name",
                "sort_order",
                "name",
                "id",
            )
            .values("id", "model_id", "model__make_id", "name", "slug")
        ),
    }
    cache.set(
        VEHICLE_SEARCH_CACHE_KEY,
        catalog,
        timeout=settings.CACHE_TTL_CATALOG_VEHICLES,
    )
    return catalog


def invalidate_vehicle_search_catalog():
    cache.delete(VEHICLE_SEARCH_CACHE_KEY)
