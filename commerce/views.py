from decimal import Decimal

from django.conf import settings
from django.db.models import Count, DecimalField, IntegerField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.utils import validate_recaptcha

from .card_payments import (
    ActiveCardPaymentExists,
    CardPaymentError,
    CardPaymentStartFailed,
    ensure_card_payments_enabled,
    get_public_card_payment,
    start_buy_now_card_payment,
    start_cart_card_payment,
)
from .delivery_quotes import DeliveryQuoteError, build_delivery_quote
from .bog_callbacks import (
    BogCallbackError,
    apply_bog_callback,
    parse_bog_callback,
    verify_bog_callback_signature,
)
from .models import (
    EasywayCity,
    EasywayRegion,
    Order,
    OrderCheckoutSource,
    OrderStatus,
)
from .meta_conversions import build_marketing_context, has_marketing_consent
from .legal import build_terms_acceptance_snapshot
from .serializers import (
    BuyNowSessionCreateSerializer,
    BuyNowSessionSerializer,
    CardPaymentCheckoutSerializer,
    CardPaymentSerializer,
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
    CheckoutSerializer,
    DeliveryQuoteRequestSerializer,
    OrderListSerializer,
    OrderListSummarySerializer,
    OrderLookupSerializer,
    OrderLookupSummarySerializer,
    PublicOrderSummarySerializer,
    OrderSummarySerializer,
    WishlistItemCreateSerializer,
    WishlistItemSerializer,
    normalize_order_lookup_phone,
)
from .services import (
    BUY_NOW_TOKEN_COOKIE_NAME,
    CART_AVAILABILITY_CHANGED_CODE,
    CART_TOKEN_COOKIE_NAME,
    WISHLIST_TOKEN_COOKIE_NAME,
    add_product_to_cart,
    add_product_to_wishlist,
    BuyNowConflictError,
    BuyNowSessionStateError,
    build_checkout_owner_fingerprint,
    build_checkout_request_fingerprint,
    CartAvailabilityChangedError,
    confirm_buy_now_session_updates,
    confirm_cart_item_prices,
    create_or_replace_buy_now_session,
    create_order_from_buy_now_session,
    create_order_from_cart,
    delete_buy_now_session,
    get_completed_idempotent_order,
    get_cart_item_for_update,
    get_buy_now_session_queryset,
    get_cart_queryset,
    get_wishlist_queryset,
    remove_product_from_wishlist,
    remove_cart_item,
    resolve_buy_now_session,
    resolve_cart,
    resolve_wishlist,
    parse_guest_token,
    parse_checkout_idempotency_key,
    StockReservationError,
    sync_cart_availability_issues,
    update_cart_item_quantity,
)


def _required_checkout_idempotency_key(request):
    idempotency_key = parse_checkout_idempotency_key(
        request.headers.get("Idempotency-Key")
    )
    if idempotency_key is None:
        raise ValidationError(
            {
                "idempotency_key": (
                    "Idempotency-Key header is required for card payments."
                )
            }
        )
    if idempotency_key.version != 4:
        raise ValidationError(
            {
                "idempotency_key": (
                    "Idempotency-Key must be a UUID version 4."
                )
            }
        )
    return idempotency_key


def _delivery_quote_error_response(error):
    return Response(
        {"detail": error.detail, "code": error.code},
        status=error.status_code,
    )


class DeliveryRegionListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        regions = EasywayRegion.objects.filter(is_active=True).order_by(
            "name",
            "external_id",
        )
        return Response(
            {
                "results": [
                    {
                        "id": region.external_id,
                        "name": region.name,
                        "is_internal_delivery": region.is_internal_delivery,
                    }
                    for region in regions
                ]
            }
        )


class DeliveryCityListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, region_id):
        region = get_object_or_404(
            EasywayRegion,
            external_id=region_id,
            is_active=True,
        )
        cities = EasywayCity.objects.filter(
            region=region,
            is_active=True,
        ).order_by("name", "external_id")
        return Response(
            {
                "region": {
                    "id": region.external_id,
                    "name": region.name,
                    "is_internal_delivery": region.is_internal_delivery,
                },
                "results": [
                    {
                        "id": city.external_id,
                        "name": city.name,
                    }
                    for city in cities
                ],
            }
        )


def _card_payment_error_response(request, error):
    if isinstance(error, ActiveCardPaymentExists):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, CardPaymentStartFailed):
        status_code = status.HTTP_502_BAD_GATEWAY
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    data = {
        "detail": error.detail,
        "code": error.code,
        "retryable": error.retryable,
    }
    if error.payment is not None:
        data["payment"] = CardPaymentSerializer(
            error.payment,
            context={"request": request},
        ).data
    return Response(data, status=status_code)


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
    def apply_cart_cookie(self, response, resolved_cart):
        if resolved_cart.clear_guest_token:
            response.delete_cookie(
                CART_TOKEN_COOKIE_NAME,
                **_api_cookie_delete_kwargs(),
            )
        elif resolved_cart.guest_token:
            response.set_cookie(
                key=CART_TOKEN_COOKIE_NAME,
                value=str(resolved_cart.guest_token),
                **_api_cookie_kwargs(max_age=60 * 60 * 24 * 30),
            )
        return response

    def build_cart_response(self, request, resolved_cart, *, status_code=status.HTTP_200_OK):
        cart = get_cart_queryset().get(pk=resolved_cart.cart.pk)
        response = Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status_code,
        )
        return self.apply_cart_cookie(response, resolved_cart)


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


class CartCardPaymentStartAPIView(CartResponseMixin, APIView):
    throttle_scope = "checkout"

    def post(self, request):
        try:
            ensure_card_payments_enabled()
        except CardPaymentError as error:
            return _card_payment_error_response(request, error)

        if not validate_recaptcha(
            request.data.get("recaptcha_token"),
            expected_action="checkout",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."},
                status=status.HTTP_403_FORBIDDEN,
            )

        resolved_cart = resolve_cart(request)
        serializer = CardPaymentCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = _required_checkout_idempotency_key(request)
        user = request.user if request.user.is_authenticated else None
        owner_fingerprint = build_checkout_owner_fingerprint(
            user=user,
            guest_token=resolved_cart.guest_token,
        )
        request_fingerprint = build_checkout_request_fingerprint(
            source=OrderCheckoutSource.CART,
            validated_data=serializer.validated_data,
        )
        terms_acceptance = build_terms_acceptance_snapshot(
            request=request,
            accepted_at=timezone.now(),
        )

        try:
            result = start_cart_card_payment(
                cart=resolved_cart.cart,
                user=user,
                validated_data=serializer.validated_data,
                terms_acceptance=terms_acceptance,
                idempotency_key=idempotency_key,
                owner_fingerprint=owner_fingerprint,
                request_fingerprint=request_fingerprint,
                marketing_consent=has_marketing_consent(request),
                marketing_context=build_marketing_context(request),
            )
        except StockReservationError as error:
            response = Response(
                {
                    "detail": error.detail,
                    "code": CART_AVAILABILITY_CHANGED_CODE,
                    "cart_issues": error.issues,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
            return self.apply_cart_cookie(response, resolved_cart)
        except DeliveryQuoteError as error:
            response = _delivery_quote_error_response(error)
            return self.apply_cart_cookie(response, resolved_cart)
        except CardPaymentError as error:
            response = _card_payment_error_response(request, error)
            return self.apply_cart_cookie(response, resolved_cart)

        response = Response(
            CardPaymentSerializer(
                result.payment,
                context={"request": request},
            ).data,
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )
        if not result.created:
            response["Idempotency-Replayed"] = "true"
        return self.apply_cart_cookie(response, resolved_cart)


class CardPaymentAvailabilityAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        response = Response(
            {
                "enabled": bool(settings.BOG_PAYMENTS_ENABLED),
                "payment_method": "card",
                "provider": "bog",
                "currency": "GEL",
                "capture": "automatic",
                "redirect_checkout": True,
            }
        )
        response["Cache-Control"] = "no-store"
        return response


class DeliveryQuoteAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "checkout"

    def post(self, request):
        serializer = DeliveryQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = serializer.validated_data["source"]

        if source == OrderCheckoutSource.CART:
            resolved_cart = resolve_cart(request)
            items = list(
                resolved_cart.cart.items.select_related(
                    "product",
                    "product__category",
                ).order_by("id")
            )
        else:
            try:
                resolved_session = resolve_buy_now_session(request)
            except BuyNowSessionStateError as error:
                return Response(error.to_response_data(), status=error.status_code)
            items = [resolved_session.session]

        try:
            quote = build_delivery_quote(
                source=source,
                items=items,
                region=serializer.validated_data["region"],
                city=serializer.validated_data["city"],
            )
        except DeliveryQuoteError as error:
            return Response(
                {"detail": error.detail, "code": error.code},
                status=error.status_code,
            )

        response = Response(quote, status=status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        return response


class BuyNowCardPaymentStartAPIView(BuyNowSessionResponseMixin, APIView):
    throttle_scope = "checkout"

    def post(self, request):
        try:
            ensure_card_payments_enabled()
        except CardPaymentError as error:
            return _card_payment_error_response(request, error)

        if not validate_recaptcha(
            request.data.get("recaptcha_token"),
            expected_action="checkout",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CardPaymentCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = _required_checkout_idempotency_key(request)
        user = request.user if request.user.is_authenticated else None

        try:
            resolved_session = resolve_buy_now_session(request)
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)

        owner_fingerprint = build_checkout_owner_fingerprint(
            user=user,
            guest_token=resolved_session.guest_token,
        )
        request_fingerprint = build_checkout_request_fingerprint(
            source=OrderCheckoutSource.BUY_NOW,
            validated_data=serializer.validated_data,
        )
        terms_acceptance = build_terms_acceptance_snapshot(
            request=request,
            accepted_at=timezone.now(),
        )

        try:
            result = start_buy_now_card_payment(
                session=resolved_session.session,
                user=user,
                validated_data=serializer.validated_data,
                terms_acceptance=terms_acceptance,
                idempotency_key=idempotency_key,
                owner_fingerprint=owner_fingerprint,
                request_fingerprint=request_fingerprint,
                marketing_consent=has_marketing_consent(request),
                marketing_context=build_marketing_context(request),
            )
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)
        except BuyNowConflictError as error:
            return self.build_buy_now_conflict_response(
                resolved_session,
                error,
            )
        except DeliveryQuoteError as error:
            response = _delivery_quote_error_response(error)
            return self.apply_buy_now_cookie(response, resolved_session)
        except CardPaymentError as error:
            response = _card_payment_error_response(request, error)
            return self.apply_buy_now_cookie(response, resolved_session)

        response = Response(
            CardPaymentSerializer(
                result.payment,
                context={"request": request},
            ).data,
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )
        if not result.created:
            response["Idempotency-Replayed"] = "true"
        return self.apply_buy_now_cookie(response, resolved_session)


class CardPaymentStatusAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, public_token):
        payment = get_public_card_payment(public_token)
        if payment is None:
            return Response(
                {"detail": "გადახდა ვერ მოიძებნა."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            CardPaymentSerializer(
                payment,
                context={"request": request},
            ).data
        )


class BogPaymentCallbackAPIView(APIView):
    authentication_classes = ()
    permission_classes = [AllowAny]
    parser_classes = ()

    def post(self, request):
        raw_body = request.body
        if len(raw_body) > settings.BOG_CALLBACK_MAX_BODY_BYTES:
            return Response(
                {
                    "detail": "Callback body is too large.",
                    "code": "bog_callback_body_too_large",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        try:
            verify_bog_callback_signature(
                raw_body,
                request.headers.get("Callback-Signature"),
            )
            callback = parse_bog_callback(raw_body)
            result = apply_bog_callback(callback)
        except BogCallbackError as error:
            return Response(
                {
                    "detail": str(error),
                    "code": error.code,
                },
                status=error.status_code,
            )

        return Response(
            {
                "status": "accepted",
                "result": result.result,
            },
            status=status.HTTP_200_OK,
        )


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
        idempotency_key = parse_checkout_idempotency_key(
            request.headers.get("Idempotency-Key")
        )
        owner_fingerprint = build_checkout_owner_fingerprint(
            user=request.user if request.user.is_authenticated else None,
            guest_token=resolved_cart.guest_token,
        )
        request_fingerprint = build_checkout_request_fingerprint(
            source=OrderCheckoutSource.CART,
            validated_data=serializer.validated_data,
        )
        terms_acceptance = build_terms_acceptance_snapshot(
            request=request,
            accepted_at=timezone.now(),
        )

        try:
            result = create_order_from_cart(
                cart=resolved_cart.cart,
                user=request.user if request.user.is_authenticated else None,
                validated_data=serializer.validated_data,
                idempotency_key=idempotency_key,
                owner_fingerprint=owner_fingerprint,
                request_fingerprint=request_fingerprint,
                terms_acceptance=terms_acceptance,
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
        except DeliveryQuoteError as error:
            return _delivery_quote_error_response(error)

        if result.created:
            Order.objects.filter(pk=result.order.pk).update(
                marketing_consent=has_marketing_consent(request),
                marketing_context=build_marketing_context(request),
            )
            result.order.refresh_from_db()

        response = Response(
            OrderSummarySerializer(
                result.order,
                context={"request": request},
            ).data,
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )
        if not result.created:
            response["Idempotency-Replayed"] = "true"
        return response


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

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = parse_checkout_idempotency_key(
            request.headers.get("Idempotency-Key")
        )
        request_fingerprint = build_checkout_request_fingerprint(
            source=OrderCheckoutSource.BUY_NOW,
            validated_data=serializer.validated_data,
        )
        terms_acceptance = build_terms_acceptance_snapshot(
            request=request,
            accepted_at=timezone.now(),
        )
        user = request.user if request.user.is_authenticated else None
        guest_token = None
        if not user:
            guest_token = parse_guest_token(
                request.COOKIES.get(BUY_NOW_TOKEN_COOKIE_NAME)
            )

        owner_fingerprint = None
        if user or guest_token:
            owner_fingerprint = build_checkout_owner_fingerprint(
                user=user,
                guest_token=guest_token,
            )

        if idempotency_key and owner_fingerprint:
            existing_order = get_completed_idempotent_order(
                idempotency_key=idempotency_key,
                source=OrderCheckoutSource.BUY_NOW,
                owner_fingerprint=owner_fingerprint,
                request_fingerprint=request_fingerprint,
            )
            if existing_order:
                response = Response(
                    OrderSummarySerializer(
                        existing_order,
                        context={"request": request},
                    ).data,
                    status=status.HTTP_200_OK,
                )
                response["Idempotency-Replayed"] = "true"
                return self.apply_buy_now_cookie(response, delete_cookie=True)

        try:
            resolved_session = resolve_buy_now_session(request)
        except BuyNowSessionStateError as error:
            if idempotency_key and owner_fingerprint:
                existing_order = get_completed_idempotent_order(
                    idempotency_key=idempotency_key,
                    source=OrderCheckoutSource.BUY_NOW,
                    owner_fingerprint=owner_fingerprint,
                    request_fingerprint=request_fingerprint,
                )
                if existing_order:
                    response = Response(
                        OrderSummarySerializer(
                            existing_order,
                            context={"request": request},
                        ).data,
                        status=status.HTTP_200_OK,
                    )
                    response["Idempotency-Replayed"] = "true"
                    return self.apply_buy_now_cookie(response, delete_cookie=True)
            return self.build_buy_now_state_error_response(error)

        owner_fingerprint = build_checkout_owner_fingerprint(
            user=user,
            guest_token=resolved_session.guest_token,
        )

        try:
            result = create_order_from_buy_now_session(
                session=resolved_session.session,
                user=user,
                validated_data=serializer.validated_data,
                idempotency_key=idempotency_key,
                owner_fingerprint=owner_fingerprint,
                request_fingerprint=request_fingerprint,
                terms_acceptance=terms_acceptance,
            )
        except BuyNowSessionStateError as error:
            return self.build_buy_now_state_error_response(error)
        except BuyNowConflictError as error:
            return self.build_buy_now_conflict_response(resolved_session, error)
        except DeliveryQuoteError as error:
            return self.apply_buy_now_cookie(
                _delivery_quote_error_response(error),
                resolved_session,
            )

        if result.created:
            Order.objects.filter(pk=result.order.pk).update(
                marketing_consent=has_marketing_consent(request),
                marketing_context=build_marketing_context(request),
            )
            result.order.refresh_from_db()

        response = Response(
            OrderSummarySerializer(
                result.order,
                context={"request": request},
            ).data,
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )
        if not result.created:
            response["Idempotency-Replayed"] = "true"
        return self.apply_buy_now_cookie(response, resolved_session, delete_cookie=True)


class OrderSummaryAPIView(APIView):
    def get(self, request, public_token):
        order = get_object_or_404(Order.objects.prefetch_related("items"), public_token=public_token)
        serializer = PublicOrderSummarySerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderLookupAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "order_lookup"

    not_found_detail = "შეკვეთა ვერ მოიძებნა. გადაამოწმეთ შეკვეთის ნომერი და ტელეფონის ნომერი."

    def post(self, request):
        serializer = OrderLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not validate_recaptcha(
            serializer.validated_data["recaptcha_token"],
            expected_action="order_lookup",
            remote_ip=request.META.get("REMOTE_ADDR"),
        ):
            return Response(
                {"detail": "უსაფრთხოების შემოწმება ვერ გაიარა."},
                status=status.HTTP_403_FORBIDDEN,
            )

        order = (
            Order.objects.prefetch_related("items")
            .filter(order_number__iexact=serializer.validated_data["order_number"])
            .first()
        )
        if not order or normalize_order_lookup_phone(order.phone) != serializer.validated_data["normalized_phone"]:
            return Response({"detail": self.not_found_detail}, status=status.HTTP_404_NOT_FOUND)

        summary_serializer = OrderLookupSummarySerializer(order, context={"request": request})
        return Response(summary_serializer.data)


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
