"""Accounting access is read/export only; never grants model-admin access."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

ACCOUNTING_PERMISSION = "commerce.view_accounting_report"


def can_view_accounting(user):
    return bool(user.is_active and user.is_staff and user.has_perm(ACCOUNTING_PERMISSION))


def accountant_only(user):
    return bool(not user.is_superuser and can_view_accounting(user))


class AccountantAdminMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if not match or "admin" not in match.namespaces or not accountant_only(request.user):
            return None
        if match.url_name == "index":
            return redirect("accounting-report")
        if match.url_name not in {"login", "logout", "password_change", "password_change_done"}:
            raise PermissionDenied

    def process_template_response(self, request, response):
        if accountant_only(request.user) and response.context_data is not None:
            response.context_data.update(available_apps=[], is_nav_sidebar_enabled=False, site_url=None)
        return response
