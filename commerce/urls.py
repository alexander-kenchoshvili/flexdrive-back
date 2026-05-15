from django.urls import path

from .views import (
    BuyNowCheckoutAPIView,
    BuyNowSessionAPIView,
    BuyNowSessionConfirmationAPIView,
    CartAPIView,
    CartItemDetailAPIView,
    CartItemListAPIView,
    CartPriceConfirmationAPIView,
    OrderCheckoutAPIView,
    OrderSummaryAPIView,
    OrderLookupAPIView,
    OwnedOrderListAPIView,
    OwnedOrderDetailAPIView,
    WishlistAPIView,
    WishlistItemDetailAPIView,
    WishlistItemListAPIView,
)

urlpatterns = [
    path("buy-now/session/", BuyNowSessionAPIView.as_view(), name="commerce-buy-now-session"),
    path(
        "buy-now/session/confirm/",
        BuyNowSessionConfirmationAPIView.as_view(),
        name="commerce-buy-now-session-confirm",
    ),
    path("buy-now/checkout/", BuyNowCheckoutAPIView.as_view(), name="commerce-buy-now-checkout"),
    path("cart/", CartAPIView.as_view(), name="commerce-cart"),
    path("cart/confirm-prices/", CartPriceConfirmationAPIView.as_view(), name="commerce-cart-confirm-prices"),
    path("cart/items/", CartItemListAPIView.as_view(), name="commerce-cart-item-list"),
    path("cart/items/<int:pk>/", CartItemDetailAPIView.as_view(), name="commerce-cart-item-detail"),
    path("wishlist/", WishlistAPIView.as_view(), name="commerce-wishlist"),
    path("wishlist/items/", WishlistItemListAPIView.as_view(), name="commerce-wishlist-item-list"),
    path("wishlist/items/<int:product_id>/", WishlistItemDetailAPIView.as_view(), name="commerce-wishlist-item-detail"),
    path("orders/checkout/", OrderCheckoutAPIView.as_view(), name="commerce-order-checkout"),
    path("orders/lookup/", OrderLookupAPIView.as_view(), name="commerce-order-lookup"),
    path("orders/", OwnedOrderListAPIView.as_view(), name="commerce-order-list"),
    path("orders/<uuid:public_token>/detail/", OwnedOrderDetailAPIView.as_view(), name="commerce-order-detail"),
    path("orders/<uuid:public_token>/", OrderSummaryAPIView.as_view(), name="commerce-order-summary"),
]
