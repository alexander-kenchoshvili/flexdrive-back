from django.contrib import admin
from django.db import transaction
from django.db.models import F, Q

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups

from .models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductImage,
    ProductSpec,
    ProductStatus,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)


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


class ProductFitmentInline(admin.TabularInline):
    model = ProductFitment
    extra = 1
    fields = ("vehicle_model", "engine", "year_from", "year_to", "notes")
    autocomplete_fields = ("vehicle_model", "engine")
    ordering = (
        "vehicle_model__make__name",
        "vehicle_model__name",
        "year_from",
        "year_to",
        "engine__name",
    )


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
    list_display = (
        "name",
        "slug",
        "parent",
        "sort_order",
        "markup_percent",
        "is_active",
        "has_image",
        "updated_at",
    )
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug")
    list_editable = ("sort_order", "markup_percent", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")
    fieldsets = (
        (
            "General",
            {
                "fields": (
                    "name",
                    "slug",
                    "parent",
                    "sort_order",
                    "markup_percent",
                    "is_active",
                )
            },
        ),
        (
            "Category image",
            {
                "fields": (
                    "image_original",
                    "image_desktop",
                    "image_tablet",
                    "image_mobile",
                    "image_alt_text",
                )
            },
        ),
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

    @admin.display(boolean=True, description="image")
    def has_image(self, obj):
        return bool(obj.desktop_image or obj.tablet_image or obj.mobile_image)

    def save_model(self, request, obj, form, change):
        previous_markup = None
        if change and obj.pk:
            previous_markup = (
                type(obj)
                .objects.filter(pk=obj.pk)
                .values_list("markup_percent", flat=True)
                .first()
            )

        super().save_model(request, obj, form, change)

        if previous_markup is not None and previous_markup != obj.markup_percent:
            self._recalculate_category_product_prices(obj)

    @staticmethod
    def _recalculate_category_product_prices(category):
        for product in category.products.filter(
            supplier_price__isnull=False,
            markup_percent_override__isnull=True,
        ).select_related("category"):
            product.price = product.calculate_customer_price()
            product.save(update_fields=["price", "updated_at"])


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")


@admin.register(VehicleMake)
class VehicleMakeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")


@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ("name", "make", "slug", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "make")
    search_fields = ("name", "slug", "make__name", "make__slug")
    list_editable = ("sort_order", "is_active")
    list_select_related = ("make",)
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("make",)
    ordering = ("make__sort_order", "make__name", "sort_order", "name")


@admin.register(VehicleEngine)
class VehicleEngineAdmin(admin.ModelAdmin):
    list_display = ("name", "model", "slug", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "model__make", "model")
    search_fields = ("name", "slug", "model__name", "model__slug", "model__make__name")
    list_editable = ("sort_order", "is_active")
    list_select_related = ("model", "model__make")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("model",)
    ordering = (
        "model__make__sort_order",
        "model__make__name",
        "model__sort_order",
        "model__name",
        "sort_order",
        "name",
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "manufacturer_part_number",
        "brand",
        "category",
        "status",
        "placement",
        "side",
        "supplier_price",
        "effective_markup_percent_readonly",
        "price",
        "old_price",
        "on_sale_flag",
        "is_new",
        "is_featured",
        "is_universal_fitment",
        "stock_qty",
        "in_stock_flag",
        "updated_at",
    )
    list_filter = (
        "status",
        "category",
        "brand",
        "placement",
        "side",
        "is_new",
        "is_featured",
        "is_universal_fitment",
        OnSaleListFilter,
        InStockListFilter,
    )
    search_fields = (
        "name",
        "sku",
        "manufacturer_part_number",
        "slug",
        "brand__name",
        "fitments__vehicle_model__name",
        "fitments__vehicle_model__make__name",
        "fitments__engine__name",
    )
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("category", "brand")
    autocomplete_fields = ("brand",)
    inlines = (ProductImageInline, ProductSpecInline, ProductFitmentInline)
    readonly_fields = (
        "category_markup_readonly",
        "effective_markup_percent_readonly",
        "calculated_customer_price_readonly",
        "on_sale_readonly",
        "in_stock_readonly",
        "created_at",
        "updated_at",
    )
    actions = ("action_publish", "action_unpublish", "action_mark_featured")

    class Media:
        js = ("catalog/admin_product_pricing_preview.js",)

    fieldsets = (
        (
            "General",
            {
                "fields": (
                    "name",
                    "slug",
                    "sku",
                    "manufacturer_part_number",
                    "brand",
                    "category",
                    "status",
                )
            },
        ),
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
        (
            "Pricing",
            {
                "fields": (
                    "supplier_price",
                    "category_markup_readonly",
                    "markup_percent_override",
                    "calculated_customer_price_readonly",
                    "price",
                    "old_price",
                    "on_sale_readonly",
                )
            },
        ),
        (
            "Parts metadata",
            {"fields": ("placement", "side", "is_universal_fitment")},
        ),
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

    @admin.display(description="Category markup")
    def category_markup_readonly(self, obj):
        if not obj or not obj.category_id:
            return "0.00%"
        return f"{obj.category.markup_percent:.2f}%"

    @admin.display(description="Applied markup")
    def effective_markup_percent_readonly(self, obj):
        if not obj:
            return "0.00%"
        return f"{obj.effective_markup_percent:.2f}%"

    @admin.display(description="Calculated customer price")
    def calculated_customer_price_readonly(self, obj):
        if not obj:
            return ""
        return f"{obj.calculate_customer_price():.2f} GEL"

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.supplier_price is not None and "price" not in readonly_fields:
            readonly_fields.append("price")
        return readonly_fields

    @admin.action(description="Publish selected products")
    def action_publish(self, request, queryset):
        queryset.update(status=ProductStatus.PUBLISHED)
        transaction.on_commit(
            lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
        )

    @admin.action(description="Move selected products to draft")
    def action_unpublish(self, request, queryset):
        queryset.update(status=ProductStatus.DRAFT)
        transaction.on_commit(
            lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
        )

    @admin.action(description="Mark selected products as featured")
    def action_mark_featured(self, request, queryset):
        queryset.update(is_featured=True)
        transaction.on_commit(
            lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
        )
