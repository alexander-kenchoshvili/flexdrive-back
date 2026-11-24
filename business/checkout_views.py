import logging

from django.core import signing
from django.db import DatabaseError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from commerce.delivery_quote_data import DeliveryQuoteError
from common.throttling import CachedScopedRateThrottle

from .checkout_progress import SOURCES, STAGE_LABELS, record_checkout_progress
from .checkout_report import RESULT_LABELS, build_checkout_report
from .views import BusinessAnalyticsView, BusinessReportInput


class CheckoutProgressInput(serializers.Serializer):
    source = serializers.ChoiceField(choices=tuple(SOURCES))
    stage = serializers.ChoiceField(choices=tuple(STAGE_LABELS))
    analytics_consent = serializers.BooleanField()
    quote_token = serializers.CharField(max_length=4096, required=False)

    def validate(self, attrs):
        if ("quote_token" in attrs) != (attrs["stage"] == "quoted"):
            raise serializers.ValidationError("Invalid quote fields.")
        return attrs


class CheckoutProgressView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (CachedScopedRateThrottle,)
    throttle_scope = "checkout_progress"

    def post(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return Response(status=204)
        if not isinstance(request.data, dict) or set(request.data) - set(CheckoutProgressInput().fields):
            return Response(status=400)
        payload = CheckoutProgressInput(data=request.data)
        if not payload.is_valid():
            return Response(status=400)
        values = payload.validated_data
        if not values["analytics_consent"]:
            return Response(status=204)
        try:
            record_checkout_progress(request, values)
        except (DeliveryQuoteError, signing.BadSignature, ValueError):
            return Response(status=400)
        except DatabaseError:
            logging.getLogger(__name__).warning("checkout_progress_storage_unavailable")
            return Response(status=503)
        return Response(status=204)


class BusinessCheckoutInput(BusinessReportInput):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    result = serializers.ChoiceField(choices=("all", *RESULT_LABELS), default="all")
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
    case_page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
    product_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)

    def validate_start(self, value):
        if value.year < 1900:
            raise serializers.ValidationError("Invalid start.")
        return value


class BusinessCheckoutView(BusinessAnalyticsView):
    input_serializer = BusinessCheckoutInput

    def get_report(self, period, values):
        return build_checkout_report(period, values)


class BusinessCartInput(BusinessReportInput):
    view = serializers.ChoiceField(choices=("contents", "additions", "products"), default="contents")
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class BusinessCartView(BusinessAnalyticsView):
    input_serializer = BusinessCartInput

    def get_report(self, period, values):
        from .carts import build_cart_report
        return build_cart_report(period, values)
