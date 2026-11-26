"""Scoped signed checkout access; knowing an application UUID is insufficient."""
from django.core.signing import BadSignature

ACCESS_MAX_AGE = 30 * 86400


def credo_access_cookie_name(token):
    return "fd_credo_" + token.hex


def has_credo_access_cookie(request, token):
    try:
        return request.get_signed_cookie(
            credo_access_cookie_name(token), salt="credo-application", max_age=ACCESS_MAX_AGE,
        ) == str(token)
    except (KeyError, BadSignature):
        return False


def has_credo_order_access(request, order):
    if order.payment_method != "credo":
        return False
    from .models import CredoApplication
    token = CredoApplication.objects.filter(order=order).values_list("public_token", flat=True).first()
    return bool(token and has_credo_access_cookie(request, token))
