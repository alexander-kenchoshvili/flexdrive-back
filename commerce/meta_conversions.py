import hashlib
import json
import logging
import re
import time
from decimal import Decimal
from urllib.parse import unquote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CURRENCY = "GEL"
PURCHASE_EVENT_NAME = "Purchase"
COOKIE_CONSENT_NAME = "flexdrive_cookie_consent"
COOKIE_CONSENT_VERSION = 1
MARKETING_CONSENT_HEADER = "X-FlexDrive-Marketing-Consent"


def build_meta_purchase_event_id(order):
    transaction_id = str(order.order_number or order.public_token).strip()
    return f"purchase-{transaction_id}"


def send_meta_purchase_event(*, order, request=None):
    if not _is_meta_capi_enabled():
        return False

    if not _has_meta_marketing_consent(request):
        return False

    payload = build_meta_purchase_payload(order=order, request=request)
    url = _build_events_url()

    try:
        response = requests.post(
            url,
            params={"access_token": settings.META_CAPI_ACCESS_TOKEN},
            json=payload,
            timeout=max(1, settings.META_CAPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Meta Conversions API purchase event failed.", exc_info=True)
        return False

    return True


def build_meta_purchase_payload(*, order, request=None):
    event = {
        "event_name": PURCHASE_EVENT_NAME,
        "event_time": int(time.time()),
        "event_id": build_meta_purchase_event_id(order),
        "action_source": "website",
        "event_source_url": _build_order_success_url(order),
        "user_data": _build_user_data(order=order, request=request),
        "custom_data": _build_custom_data(order),
    }

    payload = {"data": [event]}

    if settings.META_CAPI_TEST_EVENT_CODE:
        payload["test_event_code"] = settings.META_CAPI_TEST_EVENT_CODE

    return payload


def _is_meta_capi_enabled():
    return (
        bool(settings.META_CAPI_ENABLED)
        and bool(settings.META_PIXEL_ID)
        and bool(settings.META_CAPI_ACCESS_TOKEN)
    )


def _has_meta_marketing_consent(request):
    if request is None:
        return False

    if _request_marketing_consent_header(request) == "granted":
        return True

    consent = _parse_cookie_consent(
        request.COOKIES.get(COOKIE_CONSENT_NAME),
    )

    return (
        isinstance(consent, dict)
        and consent.get("version") == COOKIE_CONSENT_VERSION
        and consent.get("marketing") is True
    )


def _request_marketing_consent_header(request):
    headers = getattr(request, "headers", None)
    if headers is not None:
        return str(headers.get(MARKETING_CONSENT_HEADER, "")).strip().lower()

    meta = getattr(request, "META", {})
    return str(meta.get("HTTP_X_FLEXDRIVE_MARKETING_CONSENT", "")).strip().lower()


def _parse_cookie_consent(raw_value):
    if not raw_value:
        return None

    for candidate in (raw_value, unquote(raw_value)):
        try:
            return json.loads(candidate)
        except (TypeError, ValueError):
            continue

    return None


def _build_events_url():
    version = (settings.META_CAPI_GRAPH_API_VERSION or "v25.0").strip()
    if not version.startswith("v"):
        version = f"v{version}"
    return f"https://graph.facebook.com/{version}/{settings.META_PIXEL_ID}/events"


def _build_order_success_url(order):
    frontend_base_url = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{frontend_base_url}/checkout/success/{order.public_token}"


def _build_user_data(*, order, request=None):
    user_data = {}

    if request is not None:
        client_ip_address = _get_client_ip(request)
        client_user_agent = request.META.get("HTTP_USER_AGENT", "").strip()

        if client_ip_address:
            user_data["client_ip_address"] = client_ip_address
        if client_user_agent:
            user_data["client_user_agent"] = client_user_agent

    hashed_email = _hash_customer_value(order.email)
    hashed_phone = _hash_customer_value(_normalize_phone(order.phone))
    hashed_first_name = _hash_customer_value(order.first_name)
    hashed_last_name = _hash_customer_value(order.last_name)
    hashed_city = _hash_customer_value(order.city)

    if hashed_email:
        user_data["em"] = [hashed_email]
    if hashed_phone:
        user_data["ph"] = [hashed_phone]
    if hashed_first_name:
        user_data["fn"] = [hashed_first_name]
    if hashed_last_name:
        user_data["ln"] = [hashed_last_name]
    if hashed_city:
        user_data["ct"] = [hashed_city]
    if order.user_id:
        user_data["external_id"] = [_hash_customer_value(order.user_id)]

    return user_data


def _build_custom_data(order):
    items = list(order.items.all())
    contents = [
        {
            "id": _build_content_id(item),
            "quantity": item.quantity,
            "item_price": _decimal_to_float(item.unit_price),
        }
        for item in items
        if _build_content_id(item)
    ]

    return {
        "currency": CURRENCY,
        "value": _decimal_to_float(order.total),
        "order_id": order.order_number,
        "content_type": "product",
        "content_ids": [item["id"] for item in contents],
        "contents": contents,
        "num_items": sum(item.quantity for item in items),
    }


def _build_content_id(item):
    return str(item.sku or item.product_id or "").strip()


def _decimal_to_float(value):
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def _hash_customer_value(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_phone(value):
    return re.sub(r"\D+", "", str(value or ""))


def _get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "").strip()
