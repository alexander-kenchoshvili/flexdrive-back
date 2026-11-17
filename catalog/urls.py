from django.urls import path

from .vin_views import VehicleVinAPIView
from .interest_views import VehicleInterestView
from .views import (
    CategoryListAPIView,
    CategoryDetailAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    ProductSuggestionAPIView,
    VehicleEngineListAPIView,
    VehicleMakeListAPIView,
    VehicleModelListAPIView,
    VehicleYearListAPIView,
)

urlpatterns = [
    path("vehicles/interest/", VehicleInterestView.as_view(), name="catalog-vehicle-interest"),
    path("vehicles/vin/", VehicleVinAPIView.as_view(), name="catalog-vehicle-vin"),
    path("products/", ProductListAPIView.as_view(), name="catalog-product-list"),
    path("products/suggestions/", ProductSuggestionAPIView.as_view(), name="catalog-product-suggestions"),
    path("products/<slug:slug>/", ProductDetailAPIView.as_view(), name="catalog-product-detail"),
    path("categories/", CategoryListAPIView.as_view(), name="catalog-category-list"),
    path("categories/<slug:slug>/", CategoryDetailAPIView.as_view(), name="catalog-category-detail"),
    path("vehicles/makes/", VehicleMakeListAPIView.as_view(), name="catalog-vehicle-make-list"),
    path("vehicles/models/", VehicleModelListAPIView.as_view(), name="catalog-vehicle-model-list"),
    path("vehicles/years/", VehicleYearListAPIView.as_view(), name="catalog-vehicle-year-list"),
    path("vehicles/engines/", VehicleEngineListAPIView.as_view(), name="catalog-vehicle-engine-list"),
]
