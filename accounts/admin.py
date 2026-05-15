from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, GoogleAccount, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 1
    max_num = 1
    can_delete = False
    fields = ("phone", "city", "address_line")


class GoogleAccountInline(admin.StackedInline):
    model = GoogleAccount
    extra = 0
    max_num = 1
    can_delete = False
    readonly_fields = (
        "google_sub",
        "email",
        "email_verified",
        "full_name",
        "picture_url",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline, GoogleAccountInline)


@admin.register(GoogleAccount)
class GoogleAccountAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "user",
        "email_verified",
        "created_at",
        "updated_at",
    )
    search_fields = ("email", "google_sub", "user__email", "user__username")
    readonly_fields = (
        "user",
        "google_sub",
        "email",
        "email_verified",
        "full_name",
        "picture_url",
        "created_at",
        "updated_at",
    )
