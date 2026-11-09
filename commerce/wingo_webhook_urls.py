"""Private per-order notification URLs; callback bodies never authorize a status."""

from urllib.parse import urlsplit

from django.conf import settings
from django.urls import reverse
from django.utils.crypto import constant_time_compare, salted_hmac

from .wingo import WingoConfigurationError


def webhook_token(order, *, secret=None):
    return salted_hmac("commerce.wingo.webhook.v1", f"{order.public_token}:{order.order_number}",
                      secret=secret, algorithm="sha256").hexdigest()


def verify_webhook_token(order, token):
    if not isinstance(token, str) or len(token) != 64:
        return False
    keys = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    return any(constant_time_compare(webhook_token(order, secret=key), token) for key in keys)


def build_webhook_url(order):
    base = settings.WINGO_WEBHOOK_PUBLIC_URL.rstrip("/")
    if not base:
        if settings.WINGO_ACCOUNT_MODE == "production":
            raise WingoConfigurationError("Wingo-ს ავტომატური სტატუსებისთვის მიუთითეთ ვებჰუკის საჯარო მისამართი.")
        return None  # Local TEST booking can still be checked with the admin button.
    route = reverse("commerce-wingo-webhook", args=[order.public_token, webhook_token(order)])
    prefix = route.rsplit("/", 3)[0]
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment
                 and parsed.path.rstrip("/") == prefix and len(base) <= 500)
        parsed.port
    except ValueError:
        valid = False
    if not valid or any(ord(char) <= 32 or ord(char) == 127 for char in base):
        raise WingoConfigurationError("Wingo-ს ვებჰუკის მისამართი უნდა იყოს ბექენდის HTTPS მისამართი /api/commerce/wingo/webhook/ გზით.")
    return base + route[len(prefix):]
