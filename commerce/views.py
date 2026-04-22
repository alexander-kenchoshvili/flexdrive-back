from decimal import Decimal

from django.conf import settings
from django.db.models import Count, DecimalField, IntegerField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.utils import validate_recaptcha

from .models import Order, OrderStatus
from .serializers import (
    BuyNowSessionCreateSerializer,
    BuyNowSessionSerializer,
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderListSerializer,
    OrderListSummarySerializer,
    OrderSummarySerializer,
    WishlistItemCreateSerializer,
    WishlistItemSerializer,
)
from .services import (
    BUY_NOW_TOKEN_COOKIE_NAME,
    CART_TOKEN_COOKIE_NAME,
    WISHLIST_TOKEN_COOKIE_NAME,
    add_product_to_cart,
    add_product_to_wishlist,
    BuyNowConflictError,
    BuyNowSessionStateError,
    CartAvailabilityChangedError,
    confirm_buy_now_session_updates,
    confirm_cart_item_prices,
    create_or_replace_buy_now_session,
    create_order_from_buy_now_session,
    create_order_from_cart,
    delete_buy_now_session,
    get_cart_item_for_update,
    get_buy_now_session_queryset,
    get_cart_queryset,
    get_wishlist_queryset,
    remove_product_from_wishlist,
    remove_cart_item,
    resolve_buy_now_session,
    resolve_cart,
    resolve_wishlist,
    sync_cart_availability_issues,
    update_cart_item_quantity,
)


def _api_cookie_kwargs(*, httponly=True, max_age=None):
    kwargs = {
        "httponly": httponly,
        "secure": settings.API_COOKIE_SECURE,
        "samesite": settings.API_COOKIE_SAMESITE,
        "path": settings.API_COOKIE_PATH,
    }
    if max_age is not None:
        kwargs["max_age"] = max_age
    if settings.API_COOKIE_DOMAIN:
        kwargs["domain"] = settings.API_COOKIE_DOMAIN
    return kwargs


def _api_cookie_delete_kwargs():
    kwargs = {
        "path": settings.API_COOKIE_PATH,
    }
    if settings.API_COOKIE_DOMAIN:
        kwargs["domain"] = settings.API_COOKIE_DOMAIN
    return kwargs


class CartResponseMixin:
    def build_cart_response(self, request, resolved_cart, *, status_code=status.HTTP_200_OK):
        cart = get_cart_queryset().get(pk=resolved_cart.cart.pk)
        response = Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status_code,
        )
        if resolved_cart.clear_guest_token:
            response.delete_cookie(CART_TOKEN_COOKIE_NAME, **_api_cookie_delete_kwargs())
        elif resolved_cart.guest_token:
            response.set_cookie(
                key=CART_TOKEN_COOKIE_NAME,
                value=str(resolved_cart.guest_token),
                **_api_cookie_kwargs(max_age=60 * 60 * 24 * 30),
            )
        return response


class WishlistResponseMixin:
    def build_wishlist_response(self, request, resolved_wishlist, *, status_code=status.HTTP_200_OK):
        queryset = get_wishlist_queryset(
            user=resolved_wishlist.user,
            guest_token=resolved_wishlist.guest_token,
        )
        serializer = WishlistItemSerializer(queryset, many=True, context={"request": request})
        response = Response(
            {
                "count": queryset.count(),
                "results": serializer.data,
            },
            status=status_code,
        )
        if resolved_wishlist.clear_guest_token:
            response.delete_cookie(WISHLIST_TOKEN_COOKIE_NAME, **_api_cookie_delete_kwargs())
        elif resolved_wishlist.guest_token:
            response.set_cookie(
                key=WISHLIST_TOKEN_COOKIE_NAME,
                value=str(resolved_wishlist.guest_token),
                **_api_cookie_kwargs(max_age=60 * 60 * 24 * 30),
            )
        return response


class BuyNowSessionResponseMixin:
    def apply_buy_now_cookie(self, response, resolved_session=None, *, delete_cookie=False):
        if delete_cookie or (resolved_session and resolved_session.clear_guest_token):
            response.delete_cookie(BUY_NOW_TOKEN_COOKIE_NAME, **_api_cookie_delete_kwargs())
        elif resolved_session and resolved_session.guest_token:
            response.set_cookie(
                key=BUY_NOW_TOKEN_COOKIE_NAME,
                value=str(resolved_session.guest_token),
                **_api_cookie_kwargs(max_age=settings.BUY_NOW_SESSION_TTL_SECONDS),
            )
        return response

    def build_buy_now_response(self, request, resolved_session, *, status_code=status.HTTP_200_OK):
        session = get_buy_now_session_queryset().get(pk=resolved_session.session.pk)
        response = Response(
            BuyNowSessionSerializer(session, context={"request": request}).data,
            status=status_code,
        )
        return self.apply_buy_now_cookie(response, resolved_session)

    def build_buy_now_state_error_response(self, error):
        response = Response(error.to_response_data(), status=error.status_code)
        return self.apply_buy_now_cookie(response, delete_cookie=error.clear_guest_token)

    def build_buy_now_conflict_response(self, resolved_session, error):
        response = Response(error.to_response_data(), status=error.status_code)
        return self.apply_buy_now_cookie(response, resolved_session)


class CartAPIView(CartResponseMixin, APIView):
    def get(self, request):
        resolved_cart = resolve_cart(request)
        return self.build_cart_response(request, resolved_cart)


class BuyNowSessionAPIView(BuyNowSessionResponseMixin, APIView):
    def get(self, request):
        try:
            resolved_session = resolve_buy_now_session(request)
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)
        return self.build_buy_now_response(request, resolved_session)

    def post(self, request):
        resolved_session = resolve_buy_now_session(request, create=True)
        serializer = BuyNowSessionCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        session = create_or_replace_buy_now_session(
            session=resolved_session.session,
            user=request.user if request.user.is_authenticated else None,
            guest_token=resolved_session.guest_token,
            product=serializer.context["product"],
            quantity=serializer.validated_data["quantity"],
        )
        resolved_session.session = session
        return self.build_buy_now_response(request, resolved_session)

    def delete(self, request):
        try:
            resolved_session = resolve_buy_now_session(request)
        except BuyNowSessionStateError as error:
            response = Response(status=status.HTTP_204_NO_CONTENT)
            return self.apply_buy_now_cookie(response, delete_cookie=error.clear_guest_token)

        delete_buy_now_session(resolved_session.session)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        return self.apply_buy_now_cookie(response, resolved_session, delete_cookie=True)


class OrderPagination(PageNumberPagination):
    page_size = 10

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "summary": getattr(self, "summary", None),
                "results": data,
            }
        )


class CartItemListAPIView(CartResponseMixin, APIView):
    def post(self, request):
        resolved_cart = resolve_cart(request)
        serializer = CartItemCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        add_product_to_cart(
            cart=resolved_cart.cart,
            product=serializer.context["product"],
            quantity=serializer.validated_data["quantity"],
        )
        return self.build_cart_response(request, resolved_cart)


class CartPriceConfirmationAPIView(CartResponseMixin, APIView):
    def post(self, request):
        resolved_cart = resolve_cart(request)
        confirm_cart_item_prices(resolved_cart.cart)
        return self.build_cart_response(request, resolved_cart)


class BuyNowSessionConfirmationAPIView(BuyNowSessionResponseMixin, APIView):
    def post(self, request):
        try:
            resolved_session = resolve_buy_now_session(request)
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)

        try:
            resolved_session.session = confirm_buy_now_session_updates(resolved_session.session)
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)
        except BuyNowConflictError as error:
            return self.build_buy_now_conflict_response(resolved_session, error)

        return self.build_buy_now_response(request, resolved_session)


class WishlistAPIView(WishlistResponseMixin, APIView):
    def get(self, request):
        resolved_wishlist = resolve_wishlist(request)
        return self.build_wishlist_response(request, resolved_wishlist)


class WishlistItemListAPIView(WishlistResponseMixin, APIView):
    def post(self, request):
        resolved_wishlist = resolve_wishlist(request)
        serializer = WishlistItemCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        add_product_to_wishlist(
            user=resolved_wishlist.user,
            guest_token=resolved_wishlist.guest_token,
            product=serializer.context["product"],
        )
        return self.build_wishlist_response(request, resolved_wishlist)


class WishlistItemDetailAPIView(WishlistResponseMixin, APIView):
    def delete(self, request, product_id):
        resolved_wishlist = resolve_wishlist(request)
        remove_product_from_wishlist(
            user=resolved_wishlist.user,
            guest_token=resolved_wishlist.guest_token,
            product_id=product_id,
        )
        return self.build_wishlist_response(request, resolved_wishlist)


class CartItemDetailAPIView(CartResponseMixin, APIView):
    def patch(self, request, pk):
        resolved_cart = resolve_cart(request)
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart_item = get_cart_item_for_update(resolved_cart.cart, pk)
        update_cart_item_quantity(cart_item, serializer.validated_data["quantity"])
        return self.build_cart_response(request, resolved_cart)

    def delete(self, request, pk):
        resolved_cart = resolve_cart(request)
        cart_item = get_cart_item_for_update(resolved_cart.cart, pk)
        remove_cart_item(cart_item)
        return self.build_cart_response(request, resolved_cart)


class OrderCheckoutAPIView(APIView):
    throttle_scope = "checkout"

    def post(self, request):
        recaptcha_token = request.data.get("recaptcha_token")
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="checkout",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."},
                status=status.HTTP_403_FORBIDDEN,
            )

        resolved_cart = resolve_cart(request)
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = create_order_from_cart(
                cart=resolved_cart.cart,
                user=request.user if request.user.is_authenticated else None,
                validated_data=serializer.validated_data,
            )
        except CartAvailabilityChangedError as availability_error:
            sync_cart_availability_issues(
                cart=resolved_cart.cart,
                issues=availability_error.issues,
            )
            return Response(
                availability_error.to_response_data(),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            OrderSummarySerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BuyNowCheckoutAPIView(BuyNowSessionResponseMixin, APIView):
    throttle_scope = "checkout"

    def post(self, request):
        recaptcha_token = request.data.get("recaptcha_token")
        if not validate_recaptcha(
            recaptcha_token,
            expected_action="checkout",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {
                    "detail": "\u10e3\u10e1\u10d0\u10e4\u10e0\u10d7\u10ee\u10dd\u10d4\u10d1\u10d8\u10e1 "
                    "\u10e8\u10d4\u10db\u10dd\u10ec\u10db\u10d4\u10d1\u10d0 \u10d5\u10d4\u10e0 \u10d2\u10d0\u10d8\u10d0\u10e0\u10d0."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            resolved_session = resolve_buy_now_session(request)
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = create_order_from_buy_now_session(
                session=resolved_session.session,
                user=request.user if request.user.is_authenticated else None,
                validated_data=serializer.validated_data,
            )
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)
        except BuyNowConflictError as error:
            return self.build_buy_now_conflict_response(resolved_session, error)

        response = Response(
            OrderSummarySerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
        return self.apply_buy_now_cookie(response, resolved_session, delete_cookie=True)


class OrderSummaryAPIView(APIView):
    def get(self, request, public_token):
        order = get_object_or_404(Order.objects.prefetch_related("items"), public_token=public_token)
        serializer = OrderSummarySerializer(order, context={"request": request})
        return Response(serializer.data)


class OwnedOrderListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer
    pagination_class = OrderPagination

    def _get_base_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def _build_summary(self):
        summary = self._get_base_queryset().aggregate(
            total_orders=Count("id"),
            total_spent=Coalesce(
                Sum("total", filter=~Q(status=OrderStatus.CANCELLED)),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            last_order_at=Max("created_at"),
        )
        return OrderListSummarySerializer(summary).data

    def get_queryset(self):
        return (
            self._get_base_queryset()
            .annotate(
                item_count=Count("items"),
                total_quantity=Coalesce(
                    Sum("items__quantity"),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            .order_by("-created_at", "-id")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        summary = self._build_summary()

        if page is not None:
            self.paginator.summary = summary
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "summary": summary,
                "results": serializer.data,
            }
        )


class OwnedOrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, public_token):
        order = get_object_or_404(
            Order.objects.prefetch_related("items"),
            user=request.user,
            public_token=public_token,
        )
        serializer = OrderSummarySerializer(order, context={"request": request})
        return Response(serializer.data)
