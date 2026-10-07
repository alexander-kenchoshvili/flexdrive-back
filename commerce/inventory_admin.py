"""Read-only operational inventory and return history; mutations use order actions."""
from django.contrib import admin
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from .models import OrderReturn, OrderReturnLine, OwnedStockLot


def order_link(order):
    return format_html('<a href="{}">{}</a>', reverse("admin:commerce_order_change", args=[order.pk]), order.order_number)


class ExplicitDefaultFilter(admin.SimpleListFilter):
    def choices(self, changelist):
        for value, label in self.lookup_choices:
            yield {"selected": (self.value() or self.default_value) == value,
                   "query_string": changelist.get_query_string({self.parameter_name: value}, []),
                   "display": label}


class ReceiptFilter(ExplicitDefaultFilter):
    title = "მიღების მდგომარეობა"
    parameter_name = "receipt"
    default_value = "awaiting"

    def lookups(self, request, model_admin):
        return [("awaiting", "უკან მოსალოდნელი"), ("received", "მიღებული"), ("all", "სრული ისტორია")]

    def queryset(self, request, queryset):
        value = self.value() or self.default_value
        if value in {"awaiting", "received"}:
            return queryset.filter(receipt_status=value)
        return queryset


class BalanceFilter(ExplicitDefaultFilter):
    title = "მარაგის ნაშთი"
    parameter_name = "balance"
    default_value = "available"

    def lookups(self, request, model_admin):
        return [("available", "დარჩენილი მარაგი"), ("empty", "ამოწურული"), ("all", "სრული ისტორია")]

    def queryset(self, request, queryset):
        value = self.value() or self.default_value
        if value == "available":
            return queryset.filter(remaining__gt=0)
        if value == "empty":
            return queryset.filter(remaining=0)
        return queryset


class ReadOnlyHistoryAdmin(admin.ModelAdmin):
    actions = None
    list_per_page = 30

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReturnLineInline(admin.TabularInline):
    model = OrderReturnLine
    extra = 0
    can_delete = False
    fields = readonly_fields = ("product_name", "company_sku", "expected_quantity", "saleable_quantity", "unsaleable_quantity")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("commerce.view_orderreturn") or request.user.has_perm("commerce.change_order")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order_item")

    @admin.display(description="პროდუქტი")
    def product_name(self, obj):
        return obj.order_item.product_name

    @admin.display(description="FlexDrive-ის კოდი")
    def company_sku(self, obj):
        return obj.order_item.internal_sku or "—"


@admin.register(OrderReturn)
class OrderReturnAdmin(ReadOnlyHistoryAdmin):
    list_display = ("return_order", "products_summary", "receipt_status", "expected_units", "payment_state", "started_at", "received_at")
    list_display_links = ("return_order",)
    list_filter = (ReceiptFilter,)
    search_fields = ("order__order_number", "lines__order_item__product_name", "lines__order_item__internal_sku")
    search_help_text = "მოძებნეთ შეკვეთის ნომრით, პროდუქტის სახელით ან FlexDrive-ის კოდით."
    fields = readonly_fields = ("linked_order", "disposition", "receipt_status", "payment_state", "started_at", "requested_by", "received_at", "received_by")
    inlines = (ReturnLineInline,)
    change_form_template = "admin/commerce/orderreturn/change_form.html"
    change_list_template = "admin/commerce/orderreturn/change_list.html"

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or request.user.has_perm("commerce.change_order")

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order", "requested_by", "received_by").prefetch_related("lines__order_item")

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        case = self.get_object(request, object_id) if object_id else None
        if case:
            extra_context["return_order_url"] = reverse("admin:commerce_order_change", args=[case.order_id])
            if case.disposition == "from_customer" and case.receipt_status == "awaiting" and request.user.has_perm("commerce.change_order"):
                extra_context["receive_url"] = reverse("admin:commerce_order_return_receive", args=[case.order_id])
        return super().changeform_view(request, object_id, form_url, extra_context)

    @admin.display(description="შეკვეთა", ordering="order__order_number")
    def return_order(self, obj):
        return obj.order.order_number

    @admin.display(description="შეკვეთის გვერდი")
    def linked_order(self, obj):
        return order_link(obj.order)

    @admin.display(description="ნივთების რაოდენობა")
    def expected_units(self, obj):
        return sum(line.expected_quantity for line in obj.lines.all())

    @admin.display(description="პროდუქტები")
    def products_summary(self, obj):
        return format_html_join("", "<div>{} × {}</div>",
                                ((line.order_item.product_name, line.expected_quantity) for line in obj.lines.all()))

    @admin.display(description="თანხის მდგომარეობა")
    def payment_state(self, obj):
        return {"paid": "თანხა ჯერ არ დაბრუნებულა", "refund_pending": "ბანკის დადასტურების მოლოდინში",
                "refunded": "თანხა დაბრუნებულია"}.get(obj.order.payment_status, "შეამოწმეთ შეკვეთა")

    @admin.display(description="დაფიქსირების დრო", ordering="created_at")
    def started_at(self, obj):
        return obj.created_at


@admin.register(OwnedStockLot)
class OwnedStockLotAdmin(ReadOnlyHistoryAdmin):
    list_display = ("product_name", "company_sku", "quantity", "remaining_units", "origin_order", "received_time")
    list_filter = (BalanceFilter,)
    search_fields = ("product__name", "product__internal_sku", "return_line__return_case__order__order_number")
    search_help_text = "მოძებნეთ პროდუქტის სახელით, FlexDrive-ის კოდით ან მიღების წყარო შეკვეთის ნომრით."
    ordering = ("-created_at", "-pk")
    fields = readonly_fields = ("product_name", "company_sku", "quantity", "remaining_units", "origin_order", "received_time", "purchase_unit_gross", "source_lot")
    change_list_template = "admin/commerce/ownedstocklot/change_list.html"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product", "return_line__return_case__order", "source_lot__product").annotate(
            used=Coalesce(Sum("allocations__quantity", filter=Q(allocations__restored_at__isnull=True)), 0),
            remaining=F("quantity") - F("used"),
        )

    @admin.display(description="პროდუქტი", ordering="product__name")
    def product_name(self, obj):
        return obj.product.name

    @admin.display(description="FlexDrive-ის კოდი", ordering="product__internal_sku")
    def company_sku(self, obj):
        return obj.product.internal_sku or "—"

    @admin.display(description="დარჩენილი რაოდენობა", ordering="remaining")
    def remaining_units(self, obj):
        return obj.remaining

    @admin.display(description="მიღების წყარო — შეკვეთა")
    def origin_order(self, obj):
        return order_link(obj.return_line.return_case.order)

    @admin.display(description="მარაგში მიღების დრო", ordering="created_at")
    def received_time(self, obj):
        return obj.created_at
