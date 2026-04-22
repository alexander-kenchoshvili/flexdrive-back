from django.contrib import admin
from django.db.models import F, Q

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups

from .models import Category, Product, ProductImage, ProductSpec, ProductStatus


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = (
        "image_original",
        "image_desktop",
        "image_tablet",
        "image_mobile",
        "alt_text",
        "is_primary",
        "sort_order",
    )
    ordering = ("sort_order", "id")


class ProductSpecInline(admin.TabularInline):
    model = ProductSpec
    extra = 1
    fields = ("key", "value", "sort_order")
    ordering = ("sort_order", "id")


class OnSaleListFilter(admin.SimpleListFilter):
    title = "on sale"
    parameter_name = "on_sale"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "yes":
            return queryset.filter(old_price__gt=F("price"))
        if value == "no":
            return queryset.filter(Q(old_price__isnull=True) | Q(old_price__lte=F("price")))
        return queryset


class InStockListFilter(admin.SimpleListFilter):
    title = "in stock"
    parameter_name = "in_stock"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "yes":
            return queryset.filter(stock_qty__gt=0)
        if value == "no":
            return queryset.filter(stock_qty=0)
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")
    fieldsets = (
        ("General", {"fields": ("name", "slug", "parent", "sort_order", "is_active")}),
        (
            "SEO",
            {
                "fields": (
                    "seo_title",
                    "seo_description",
                    "seo_image",
                    "seo_noindex",
                    "seo_canonical_url",
                )
            },
        ),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "status",
        "price",
        "old_price",
        "on_sale_flag",
        "is_new",
        "is_featured",
        "stock_qty",
        "in_stock_flag",
        "updated_at",
    )
    list_filter = (
        "status",
        "category",
        "is_new",
        "is_featured",
        OnSaleListFilter,
        InStockListFilter,
    )
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("category",)
    inlines = (ProductImageInline, ProductSpecInline)
    readonly_fields = ("on_sale_readonly", "in_stock_readonly", "created_at", "updated_at")
    actions = ("action_publish", "action_unpublish", "action_mark_featured")

    fieldsets = (
        ("General", {"fields": ("name", "slug", "sku", "category", "status")}),
        (
            "SEO",
            {
                "fields": (
                    "seo_title",
                    "seo_description",
                    "seo_image",
                    "seo_noindex",
                    "seo_canonical_url",
                )
            },
        ),
        ("Descriptions", {"fields": ("short_description", "description")}),
        ("Pricing", {"fields": ("price", "old_price", "on_sale_readonly")}),
        ("Flags", {"fields": ("is_new", "is_featured")}),
        ("Inventory", {"fields": ("stock_qty", "in_stock_readonly")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(boolean=True, description="On sale")
    def on_sale_flag(self, obj):
        return obj.on_sale

    @admin.display(boolean=True, description="In stock")
    def in_stock_flag(self, obj):
        return obj.in_stock

    @admin.display(description="On sale")
    def on_sale_readonly(self, obj):
        if not obj:
            return False
        return obj.on_sale

    @admin.display(description="In stock")
    def in_stock_readonly(self, obj):
        if not obj:
            return False
        return obj.in_stock

    @admin.action(description="Publish selected products")
    def action_publish(self, request, queryset):
        queryset.update(status=ProductStatus.PUBLISHED)
        invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)

    @admin.action(description="Move selected products to draft")
    def action_unpublish(self, request, queryset):
        queryset.update(status=ProductStatus.DRAFT)
        invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)

    @admin.action(description="Mark selected products as featured")
    def action_mark_featured(self, request, queryset):
        queryset.update(is_featured=True)
        invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
