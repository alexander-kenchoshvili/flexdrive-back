import requests
from django.conf import settings


RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def _get_allowed_hostnames():
    configured = getattr(settings, "RECAPTCHA_ALLOWED_HOSTNAMES", None)
    if configured:
        return {str(host).strip().lower() for host in configured if str(host).strip()}

    return {
        str(host).strip().lower()
        for host in getattr(settings, "ALLOWED_HOSTS", [])
        if host and host != "*"
    }


def validate_recaptcha(token, expected_action=None, remote_ip=None):
    if not token:
        return False

    secret = getattr(settings, "RECAPTCHA_SECRET_KEY", None)
    if not secret:
        return False

    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    timeout_seconds = getattr(settings, "RECAPTCHA_TIMEOUT_SECONDS", 5)

    try:
        response = requests.post(RECAPTCHA_VERIFY_URL, data=data, timeout=timeout_seconds)
        result = response.json()
    except Exception:
        return False

    if not result.get("success", False):
        return False

    min_score = getattr(settings, "RECAPTCHA_MIN_SCORE", 0.5)
    if result.get("score", 0) < min_score:
        return False

    if expected_action and result.get("action") != expected_action:
        return False

    allowed_hostnames = _get_allowed_hostnames()
    if allowed_hostnames:
        hostname = str(result.get("hostname", "")).strip().lower()
        if hostname not in allowed_hostnames:
            return False

    return True
