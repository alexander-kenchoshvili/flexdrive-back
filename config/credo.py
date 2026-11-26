"""Credo environment mapping. Loading configuration never calls a bank."""
import math
import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def _invalid(name):
    # Environment values (especially keys and malformed URLs) are never echoed.
    raise ImproperlyConfigured(f"Invalid Credo configuration: check {name}.") from None


def _boolean(env, name, default):
    raw = env.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    _invalid(name)


def _timeout(env, name, default):
    try:
        value = float(env.get(name, default))
        if not math.isfinite(value) or not 0 < value <= 300:
            raise ValueError
        return value
    except (TypeError, ValueError, OverflowError):
        _invalid(name)


def _url(value, name, *, origin=False):
    if not value:
        return
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
                or "\\" in value or (origin and parsed.path not in ("", "/"))):
            raise ValueError
        _ = parsed.port
    except (ValueError, TypeError):
        _invalid(name)


def load_credo_environment(env):
    values = {
        "CREDO_PAYMENTS_ENABLED": _boolean(env, "CREDO_PAYMENTS_ENABLED", False),
        "CREDO_STATUS_CHECK_ENABLED": _boolean(env, "CREDO_STATUS_CHECK_ENABLED", False),
        "CREDO_TEST_MODE": _boolean(env, "CREDO_TEST_MODE", True),
        "CREDO_MERCHANT_ID": env.get("CREDO_MERCHANT_ID", "").strip(),
        # No strip/interpolation here: the credential is an exact signing input.
        "CREDO_SECRET_KEY": env.get("CREDO_SECRET_KEY", ""),
        # The create spec documents the path but has servers:[]; require an
        # explicitly confirmed complete URL before enabling either real client.
        "CREDO_ORDER_URL": env.get("CREDO_ORDER_URL", "").strip(),
        "CREDO_STATUS_URL": env.get("CREDO_STATUS_URL", "https://ganvadeba.credo.ge/widget/api.php").strip(),
        "CREDO_REDIRECT_ORIGIN": env.get("CREDO_REDIRECT_ORIGIN", "https://ganvadeba.credo.ge").strip(),
        "CREDO_HTTP_CONNECT_TIMEOUT_SECONDS": _timeout(env, "CREDO_HTTP_CONNECT_TIMEOUT_SECONDS", 5),
        "CREDO_HTTP_READ_TIMEOUT_SECONDS": _timeout(env, "CREDO_HTTP_READ_TIMEOUT_SECONDS", 15),
    }
    ttl = env.get("CREDO_RESERVATION_TTL_SECONDS", "").strip()
    try:
        ttl = int(ttl) if ttl else None
        if ttl is not None and not 1 <= ttl <= 7 * 86400:
            raise ValueError
    except ValueError:
        _invalid("CREDO_RESERVATION_TTL_SECONDS")
    values["CREDO_RESERVATION_TTL_SECONDS"] = ttl
    merchant = values["CREDO_MERCHANT_ID"]
    if merchant and (not re.fullmatch(r"[0-9]{1,64}", merchant) or int(merchant) < 1):
        _invalid("CREDO_MERCHANT_ID")
    if any(ord(char) < 32 or ord(char) == 127 for char in values["CREDO_SECRET_KEY"]):
        _invalid("CREDO_SECRET_KEY")
    for name in ("CREDO_ORDER_URL", "CREDO_STATUS_URL", "CREDO_REDIRECT_ORIGIN"):
        _url(values[name], name, origin=name == "CREDO_REDIRECT_ORIGIN")
    if values["CREDO_PAYMENTS_ENABLED"] and not values["CREDO_STATUS_CHECK_ENABLED"]:
        _invalid("CREDO_STATUS_CHECK_ENABLED")
    if values["CREDO_PAYMENTS_ENABLED"] and ttl is None:
        _invalid("CREDO_RESERVATION_TTL_SECONDS")
    if values["CREDO_PAYMENTS_ENABLED"] or values["CREDO_STATUS_CHECK_ENABLED"]:
        for name in ("CREDO_MERCHANT_ID", "CREDO_SECRET_KEY", "CREDO_ORDER_URL", "CREDO_STATUS_URL", "CREDO_REDIRECT_ORIGIN"):
            if not values[name].strip():
                _invalid(name)
    return values
