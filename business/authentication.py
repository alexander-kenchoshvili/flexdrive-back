from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.crypto import constant_time_compare
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission


BUSINESS_PERMISSION = "business.view_dashboard"
BUSINESS_COOKIE = "fd_business_session"
BUSINESS_COOKIE_PATH = "/api/business/"
SESSION_KIND = "flexdrive_business"


def can_view_dashboard(user):
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.has_perm(BUSINESS_PERMISSION)
    )


def session_store(session_key=None):
    return import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key)


def get_business_session(request):
    if not hasattr(request, "_business_session"):
        request._business_session = session_store(request.COOKIES.get(BUSINESS_COOKIE))
    return request._business_session


class BusinessSessionAuthentication(BaseAuthentication):
    """Never accepts customer JWT cookies, admin sessionid or bearer tokens."""

    def authenticate(self, request):
        if not request.COOKIES.get(BUSINESS_COOKIE):
            return None
        session = get_business_session(request)
        if session.get("kind") != SESSION_KIND:
            return None
        try:
            user = get_user_model().objects.get(pk=session.get("user_id"))
        except (get_user_model().DoesNotExist, ValueError, TypeError):
            return None
        stored_hash = session.get("auth_hash", "")
        if not user.is_active or not constant_time_compare(stored_hash, user.get_session_auth_hash()):
            return None
        return user, session

    def authenticate_header(self, request):
        return "BusinessSession"


class CanViewDashboard(BasePermission):
    message = "ბიზნესპანელზე წვდომის უფლება არ გაქვთ."

    def has_permission(self, request, view):
        return can_view_dashboard(request.user)
