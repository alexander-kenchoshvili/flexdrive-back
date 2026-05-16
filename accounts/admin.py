from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, FacebookAccount, GoogleAccount, UserProfile


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


class FacebookAccountInline(admin.StackedInline):
    model = FacebookAccount
    extra = 0
    max_num = 1
    can_delete = False
    readonly_fields = (
        "facebook_id",
        "email",
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
    inlines = (UserProfileInline, GoogleAccountInline, FacebookAccountInline)


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


@admin.register(FacebookAccount)
class FacebookAccountAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "user",
        "created_at",
        "updated_at",
    )
    search_fields = ("email", "facebook_id", "user__email", "user__username")
    readonly_fields = (
        "user",
        "facebook_id",
        "email",
        "full_name",
        "picture_url",
        "created_at",
        "updated_at",
    )
