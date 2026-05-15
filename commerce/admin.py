from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponseRedirect

from .models import Cart, CartItem, Order, OrderItem, OrderStatus
from .services import (
    can_cancel_order,
    can_transition_order_status,
    cancel_order_and_restore_stock,
    transition_order_status,
)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "quantity", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "guest_token", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "user__username", "guest_token")
    readonly_fields = ("created_at", "updated_at")
    inlines = (CartItemInline,)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "sku", "unit_price", "quantity", "line_total")
    readonly_fields = fields
    can_delete = False


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        if not self.instance.pk:
            return cleaned_data

        next_status = cleaned_data.get("status")
        if not next_status:
            return cleaned_data

        current_order = Order.objects.only("status").get(pk=self.instance.pk)
        if current_order.status == next_status:
            return cleaned_data

        if next_status == OrderStatus.CANCELLED:
            self.add_error(
                "status",
                "Use the 'Cancel and restore stock' button to cancel this order.",
            )
            return cleaned_data

        if not can_transition_order_status(current_order, next_status):
            self.add_error(
                "status",
                (
                    f"Cannot change status from '{current_order.get_status_display()}' "
                    f"to '{OrderStatus(next_status).label}'."
                ),
            )

        return cleaned_data


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    change_form_template = "admin/commerce/order/change_form.html"
    list_display = (
        "order_number",
        "customer_name",
        "phone",
        "email",
        "payment_method",
        "payment_status",
        "total",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_status", "payment_method", "created_at")
    search_fields = ("order_number", "first_name", "last_name", "email", "phone")
    readonly_fields = (
        "order_number",
        "public_token",
        "subtotal",
        "total",
        "stock_restored_at",
        "created_at",
        "updated_at",
    )
    inlines = (OrderItemInline,)

    fieldsets = (
        (
            "Order",
            {
                "fields": (
                    "order_number",
                    "public_token",
                    "payment_method",
                    "payment_status",
                    "status",
                )
            },
        ),
        ("Customer", {"fields": ("first_name", "last_name", "email", "phone")}),
        ("Delivery", {"fields": ("city", "address_line", "note")}),
        ("Totals", {"fields": ("subtotal", "total")}),
        (
            "Timestamps",
            {
                "fields": ("stock_restored_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Customer")
    def customer_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}

        if object_id:
            order = self.get_object(request, object_id)
            extra_context["show_cancel_and_restore_stock"] = bool(
                order and can_cancel_order(order)
            )
        else:
            extra_context["show_cancel_and_restore_stock"] = False

        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            return

        current_order = Order.objects.get(pk=obj.pk)
        requested_status = obj.status

        if requested_status == current_order.status:
            super().save_model(request, obj, form, change)
            return

        obj.status = current_order.status
        super().save_model(request, obj, form, change)
        transition_order_status(obj, requested_status)

    def response_change(self, request, obj):
        if "_cancel_and_restore_stock" not in request.POST:
            return super().response_change(request, obj)

        try:
            cancel_order_and_restore_stock(obj)
        except DjangoValidationError as error:
            self.message_user(request, error.messages[0], level=messages.ERROR)
        else:
            self.message_user(
                request,
                "Order was cancelled and stock was restored successfully.",
                level=messages.SUCCESS,
            )

        return HttpResponseRedirect(".")
