from django.urls import path

from .views import (
    CategoryListAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    ProductSuggestionAPIView,
    VehicleEngineListAPIView,
    VehicleMakeListAPIView,
    VehicleModelListAPIView,
    VehicleYearListAPIView,
)

urlpatterns = [
    path("products/", ProductListAPIView.as_view(), name="catalog-product-list"),
    path("products/suggestions/", ProductSuggestionAPIView.as_view(), name="catalog-product-suggestions"),
    path("products/<slug:slug>/", ProductDetailAPIView.as_view(), name="catalog-product-detail"),
    path("categories/", CategoryListAPIView.as_view(), name="catalog-category-list"),
    path("vehicles/makes/", VehicleMakeListAPIView.as_view(), name="catalog-vehicle-make-list"),
    path("vehicles/models/", VehicleModelListAPIView.as_view(), name="catalog-vehicle-model-list"),
    path("vehicles/years/", VehicleYearListAPIView.as_view(), name="catalog-vehicle-year-list"),
    path("vehicles/engines/", VehicleEngineListAPIView.as_view(), name="catalog-vehicle-engine-list"),
]
