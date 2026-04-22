from django.urls import path

from .views import (
    CategoryListAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    ProductSuggestionAPIView,
)

urlpatterns = [
    path("products/", ProductListAPIView.as_view(), name="catalog-product-list"),
    path("products/suggestions/", ProductSuggestionAPIView.as_view(), name="catalog-product-suggestions"),
    path("products/<slug:slug>/", ProductDetailAPIView.as_view(), name="catalog-product-detail"),
    path("categories/", CategoryListAPIView.as_view(), name="catalog-category-list"),
]
