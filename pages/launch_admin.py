"""Explicit, audited public-opening action, available only to the owner."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.conf import settings

from common.storefront_access import make_preview_code
from .models import LaunchControl


@admin.register(LaunchControl)
class LaunchControlAdmin(admin.ModelAdmin):
    readonly_fields = ("public_open", "preview_version", "updated_at")

    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_staff and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_module_permission(request):
            raise PermissionDenied
        return redirect("admin:pages_launchcontrol_changelist")

    def changelist_view(self, request, extra_context=None):
        if not self.has_module_permission(request):
            raise PermissionDenied
        preview_code = None
        enabled = settings.STOREFRONT_ACCESS_GUARD_ENABLED
        if request.method == "POST":
            action = request.POST.get("action")
            if not enabled or action not in {"open", "close", "preview", "revoke"}:
                return HttpResponseBadRequest("არასწორი მოქმედება ან დაცვა ჯერ არ არის ჩართული.")
            with transaction.atomic():
                control = LaunchControl.objects.select_for_update().get(pk=1)
                if action == "preview":
                    preview_code = make_preview_code(control)
                    self.log_change(request, control, "შეიქმნა 24-საათიანი სატესტო შესვლის კოდი.")
                elif action == "revoke":
                    control.preview_version += 1
                    control.save(update_fields=["preview_version", "updated_at"])
                    self.log_change(request, control, "ყველა არსებული სატესტო შესვლის კოდი გაუქმდა.")
                    self.message_user(request, "ძველი სატესტო კოდები გაუქმებულია.", messages.SUCCESS)
                else:
                    public_open = action == "open"
                    if control.public_open != public_open:
                        control.public_open = public_open
                        control.save(update_fields=["public_open", "updated_at"])
                        self.log_change(request, control, "საიტი საჯაროდ გაიხსნა." if public_open else "საიტი დაცულ რეჟიმში დაბრუნდა.")
                    self.message_user(request, "საიტი საჯაროდ გახსნილია." if public_open else "საიტი დაცულ რეჟიმშია.", messages.SUCCESS)
            if preview_code is None:
                return redirect("admin:pages_launchcontrol_changelist")
        control = LaunchControl.objects.get(pk=1)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "საიტის საჯარო გახსნა",
            "control": control,
            "guard_enabled": enabled,
            "preview_code": preview_code,
        }
        response = TemplateResponse(request, "admin/pages/launch_control.html", context)
        # Browser form POSTs need their same-origin Origin/Referer for CSRF checks.
        response["Referrer-Policy"] = "same-origin"
        return response
