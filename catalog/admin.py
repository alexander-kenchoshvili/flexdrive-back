from django import forms
from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q
from django.forms.models import BaseInlineFormSet
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from PIL import Image, ImageOps
from decimal import Decimal

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


class ProductImageAdminForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = "__all__"

    def validate_constraints(self):
        # The inline formset validates the final submitted primary-image state.
        # Running the model constraint per row sees stale DB values when moving
        # the primary flag from an existing image to a newly uploaded image.
        return None


class ProductImageInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        primary_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            if form.cleaned_data.get("is_primary"):
                primary_count += 1

        if primary_count > 1:
            raise forms.ValidationError(
                "Only one product image can be marked as primary."
            )


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageAdminForm
    formset = ProductImageInlineFormSet
    extra = 1
    readonly_fields = ("crop_tools",)
    fields = (
        "image_original",
        "image_desktop",
        "image_tablet",
        "image_mobile",
        "crop_tools",
        "alt_text",
        "is_primary",
        "sort_order",
    )
    ordering = ("sort_order", "id")

    @admin.display(description="Crop")
    def crop_tools(self, obj):
        if not obj or not obj.pk:
            return "Save this product image before cropping."

        if not obj.image_original:
            return "Upload IMAGE ORIGINAL to use crop tools."

        url = reverse(
            "admin:catalog_productimage_crop",
            args=[obj.product_id, obj.pk],
        )
        label = "Edit crop"
        if obj.has_crop():
            label = "Edit crop / reset"
        return format_html('<a class="button" href="{}">{}</a>', url, label)


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

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/images/<int:image_id>/crop/",
                self.admin_site.admin_view(self.crop_product_image_view),
                name="catalog_productimage_crop",
            ),
        ]
        return custom_urls + urls

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
        calculated_price = obj.calculate_customer_price()
        if calculated_price is None:
            return ""
        return f"{calculated_price:.2f} GEL"

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.supplier_price is not None and "price" not in readonly_fields:
            readonly_fields.append("price")
        return readonly_fields

    def crop_product_image_view(self, request, object_id, image_id):
        product = self.get_object(request, object_id)
        if product is None:
            raise Http404("Product does not exist.")

        image = (
            ProductImage.objects.filter(pk=image_id, product=product)
            .select_related("product")
            .first()
        )
        if image is None:
            raise Http404("Product image does not exist.")

        product_url = reverse("admin:catalog_product_change", args=[product.pk])
        if not image.image_original:
            messages.error(request, "Upload IMAGE ORIGINAL before using crop tools.")
            return HttpResponseRedirect(product_url)

        source_size = self._get_product_image_original_size(image)
        if source_size is None:
            messages.error(request, "Original image could not be opened for cropping.")
            return HttpResponseRedirect(product_url)

        if request.method == "POST":
            action = request.POST.get("action", "manual")
            try:
                if action == "auto":
                    if not image.auto_crop_from_original():
                        messages.warning(request, "Auto crop could not detect removable whitespace.")
                        return HttpResponseRedirect(request.path)
                    message = "Auto crop applied and responsive images regenerated."
                elif action == "reset":
                    image.clear_crop()
                    message = "Crop reset and responsive images regenerated from the original."
                elif action == "white_bg":
                    image.replace_background_with_white = True
                    message = "Flat background replacement applied and responsive images regenerated."
                elif action == "reset_bg":
                    image.replace_background_with_white = False
                    message = "Background replacement reset and responsive images regenerated."
                else:
                    self._apply_manual_crop_from_post(image, request.POST)
                    message = "Crop applied and responsive images regenerated."
            except ValueError as error:
                messages.error(request, str(error))
                return HttpResponseRedirect(request.path)

            image.save(
                update_fields=[
                    "crop_x",
                    "crop_y",
                    "crop_width",
                    "crop_height",
                    "replace_background_with_white",
                    "updated_at",
                ]
            )
            messages.success(request, message)
            next_url = request.POST.get("next") or product_url
            return HttpResponseRedirect(next_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Crop product image: {product.name}",
            "opts": self.model._meta,
            "original": product,
            "product": product,
            "image": image,
            "image_url": image.image_original.url,
            "source_width": source_size[0],
            "source_height": source_size[1],
            "crop": self._crop_context(image),
            "replace_background_with_white": image.replace_background_with_white,
            "product_url": product_url,
            "preserved_filters": urlencode({"_changelist_filters": request.GET.urlencode()}),
        }
        return TemplateResponse(request, "admin/catalog/productimage/crop.html", context)

    @staticmethod
    def _get_product_image_original_size(image):
        image.image_original.open("rb")
        try:
            with Image.open(image.image_original) as source:
                source = ImageOps.exif_transpose(source)
                return source.size
        except Exception:
            return None
        finally:
            image.image_original.close()

    @staticmethod
    def _crop_context(image):
        if image.has_crop():
            return {
                "x": float(image.crop_x),
                "y": float(image.crop_y),
                "width": float(image.crop_width),
                "height": float(image.crop_height),
            }

        return {
            "x": 0.0,
            "y": 0.0,
            "width": 1.0,
            "height": 1.0,
        }

    @staticmethod
    def _apply_manual_crop_from_post(image, post_data):
        crop_values = {}
        for field_name in ("crop_x", "crop_y", "crop_width", "crop_height"):
            raw_value = post_data.get(field_name)
            try:
                value = Decimal(str(raw_value))
            except Exception as exc:
                raise ValueError("Crop values are invalid.") from exc
            if value < 0 or value > 1:
                raise ValueError("Crop values must stay inside the image.")
            crop_values[field_name] = value.quantize(Decimal("0.00001"))

        if crop_values["crop_width"] < Decimal("0.05000") or crop_values["crop_height"] < Decimal("0.05000"):
            raise ValueError("Crop area is too small.")

        if crop_values["crop_x"] + crop_values["crop_width"] > Decimal("1.00000"):
            raise ValueError("Crop width extends outside the image.")

        if crop_values["crop_y"] + crop_values["crop_height"] > Decimal("1.00000"):
            raise ValueError("Crop height extends outside the image.")

        image.crop_x = crop_values["crop_x"]
        image.crop_y = crop_values["crop_y"]
        image.crop_width = crop_values["crop_width"]
        image.crop_height = crop_values["crop_height"]

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
