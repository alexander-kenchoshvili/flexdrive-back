"""A private notification triggers a canonical authenticated GET, never a blind write."""

import hashlib
import hmac
import json

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .wingo import WingoClient, WingoError
from .wingo_tracking import WingoTrackingBusy, provider_datetime, sync_shipment
from .wingo_webhook_urls import verify_webhook_token


MAX_WEBHOOK_BYTES = 64 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def parse_notification(raw, *, event_header=None):
    try:
        body = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if not isinstance(body, dict) or body.get("event") not in {"order.created", "order.status_changed"}:
            raise ValueError
        if event_header and event_header != body["event"]:
            raise ValueError
        provider_datetime(body.get("timestamp"))
        order = body.get("order")
        if not isinstance(order, dict) or type(order.get("orderStatusId")) is not int:
            raise ValueError
        for key in ("id", "orderNumber", "supplierOrderId"):
            WingoClient._reference(order.get(key))
        return {key: order[key] for key in ("id", "orderNumber", "supplierOrderId")}
    except (ValueError, TypeError, UnicodeError, RecursionError, WingoError):
        raise ValueError("Invalid Wingo notification") from None


class WingoWebhookAPIView(APIView):
    authentication_classes = ()
    permission_classes = [AllowAny]
    parser_classes = ()
    throttle_classes = ()  # Private per-order route; GET work is serialized per shipment.

    def post(self, request, public_token, token):
        order = Order.objects.filter(public_token=public_token, delivery_provider="wingo").first()
        if order is None or not verify_webhook_token(order, token):
            return Response({"status": "rejected"}, status=404)
        if request.content_type != "application/json":
            return Response({"status": "invalid_content_type"}, status=415)
        raw = request.read(MAX_WEBHOOK_BYTES + 1)
        if len(raw) > MAX_WEBHOOK_BYTES:
            return Response({"status": "body_too_large"}, status=413)
        if settings.WINGO_WEBHOOK_SECRET:
            expected = "sha256=" + hmac.new(settings.WINGO_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
            if not constant_time_compare(expected, request.headers.get("X-Wingo-Signature", "")):
                return Response({"status": "invalid_signature"}, status=403)
        try:
            notification = parse_notification(raw, event_header=request.headers.get("X-Wingo-Event"))
        except ValueError:
            return Response({"status": "invalid_notification"}, status=400)
        try:
            result = sync_shipment(order.pk, notification=notification)
        except WingoTrackingBusy:
            return Response({"status": "retry"}, status=503, headers={"Retry-After": "3"})
        except WingoError:
            return Response({"status": "retry"}, status=503, headers={"Retry-After": "3"})
        return Response({"status": "accepted", "result": result})
