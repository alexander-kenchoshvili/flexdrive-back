"""Temporary storefront access, shared by the API and the Nuxt server.

Access verdicts and the two legal documents are public reads. Preview codes are signed,
expire after 24 hours and never grant account/admin/payment permissions.
"""

import secrets
from urllib.parse import unquote

from django.conf import settings
from django.core import signing
from django.db import DatabaseError
from django.http import JsonResponse
from django.urls import Resolver404, resolve
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_safe

from pages.models import LaunchControl


PREVIEW_COOKIE = "fd_preview_access"
PREVIEW_SALT = "flexdrive.storefront-preview.v1"
PREVIEW_MAX_AGE = 24 * 60 * 60


def make_preview_code(control):
    return signing.dumps({"version": control.preview_version, "nonce": secrets.token_urlsafe(24)}, salt=PREVIEW_SALT)


def has_preview_access(request, control):
    token = request.COOKIES.get(PREVIEW_COOKIE, "")
    if not isinstance(token, str) or not 1 <= len(token) <= 512:
        return False
    # h3 serializes cookie values with encodeURIComponent (Django keeps them raw).
    token = unquote(token)
    try:
        payload = signing.loads(token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except (signing.BadSignature, ValueError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("version") == control.preview_version


def private_response(response):
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    patch_vary_headers(response, ["Cookie"])
    return response


@require_safe
def launch_status(request):
    enabled = settings.STOREFRONT_ACCESS_GUARD_ENABLED
    try:
        control = LaunchControl.objects.get(pk=1) if enabled else None
    except (DatabaseError, LaunchControl.DoesNotExist):
        return private_response(JsonResponse({"code": "storefront_unavailable"}, status=503))
    return private_response(JsonResponse({
        "guard_enabled": enabled,
        "public_open": bool(control and control.public_open),
        "preview_allowed": bool(control and has_preview_access(request, control)),
    }))


def _is_required_exception(request):
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return False
    if "admin" in match.namespaces or match.url_name == "accounting-report":
        return True  # Each view retains its existing admin/session permission checks.
    if match.func is launch_status:
        return True
    from pages.public_information import PUBLIC_LEGAL_PAGES, public_legal_information
    if (
        match.func is public_legal_information
        and request.method in {"GET", "HEAD"}
        and match.kwargs.get("slug") in PUBLIC_LEGAL_PAGES
    ):
        return True
    if request.method != "POST":
        return False
    from commerce.views import BogPaymentCallbackAPIView
    from commerce.wingo_webhooks import WingoWebhookAPIView
    expected = {
        "commerce-bog-payment-callback": BogPaymentCallbackAPIView,
        "commerce-wingo-webhook": WingoWebhookAPIView,
    }
    return match.url_name in expected and getattr(match.func, "view_class", None) is expected[match.url_name]


class StorefrontAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.STOREFRONT_ACCESS_GUARD_ENABLED:
            return self.get_response(request)
        if _is_required_exception(request):
            return private_response(self.get_response(request))
        try:
            control = LaunchControl.objects.get(pk=1)
        except (DatabaseError, LaunchControl.DoesNotExist):
            return private_response(JsonResponse({"code": "storefront_unavailable"}, status=503))
        if not control.public_open and not has_preview_access(request, control):
            response = JsonResponse({"code": "storefront_not_open", "detail": "საიტი ჯერ არ არის საჯაროდ გახსნილი."}, status=403)
            response["X-Robots-Tag"] = "noindex, nofollow"
            return private_response(response)
        return private_response(self.get_response(request))
