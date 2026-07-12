from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.forms.models import BaseInlineFormSet
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
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
    ProductPlacement,
    ProductSide,
    ProductSpec,
    ProductStatus,
    SupplierProductBlock,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)

CROSSMOTORS_SOURCE_NAME = "Cross Motors"
CROSSMOTORS_SKU_PREFIX = "CM-"
PLACEMENT_LABELS_KA = {
    ProductPlacement.FRONT: "წინა",
    ProductPlacement.REAR: "უკანა",
    ProductPlacement.UPPER: "ზედა",
    ProductPlacement.LOWER: "ქვედა",
    ProductPlacement.INNER: "შიდა",
    ProductPlacement.OUTER: "გარე",
}
SIDE_LABELS_KA = {
    ProductSide.LEFT: "მარცხენა",
    ProductSide.RIGHT: "მარჯვენა",
    ProductSide.BOTH: "ორივე",
    ProductSide.CENTER: "ცენტრი",
}


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


def _regenerate_manual_fitment_descriptions(product):
    fitment = (
        product.fitments.select_related("vehicle_model__make")
        .order_by(
            "vehicle_model__make__name",
            "vehicle_model__name",
            "year_from",
            "year_to",
            "engine__name",
        )
        .first()
    )
    if not fitment:
        return

    vehicle = _fitment_vehicle_label(fitment)
    years = _fitment_year_label(fitment)
    placement = PLACEMENT_LABELS_KA.get(product.placement, "")
    side = SIDE_LABELS_KA.get(product.side, "")

    short_parts = [product.name, vehicle, years]
    short_description = " - ".join(part for part in short_parts if part)[:300]

    detail_parts = [part for part in (vehicle, years, placement, side) if part]
    description = (
        f"{product.name} - {', '.join(detail_parts)}."
        if detail_parts
        else product.name
    )

    product.short_description = short_description
    product.description = description
    product.seo_description = short_description
    product.save(
        update_fields=[
            "short_description",
            "description",
            "seo_description",
            "updated_at",
        ]
    )


def _fitment_vehicle_label(fitment):
    if not fitment:
        return ""
    return " ".join(
        part
        for part in (
            fitment.vehicle_model.make.name,
            fitment.vehicle_model.name,
        )
        if part
    )


def _fitment_year_label(fitment):
    if not fitment:
        return ""
    if fitment.year_from == fitment.year_to:
        return str(fitment.year_from)
    return f"{fitment.year_from}-{fitment.year_to}"


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
    actions = (
        "action_publish",
        "action_unpublish",
        "action_mark_featured",
        "action_block_supplier_products",
        "action_allow_supplier_products",
    )

    class Media:
        js = (
            "catalog/admin_product_pricing_preview.js",
            "catalog/admin_product_images_bulk_delete.js",
            "catalog/admin_product_image_camera.js",
        )
        css = {
            "all": ("catalog/admin_product_image_camera.css",),
        }

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/images/delete-selected/",
                self.admin_site.admin_view(self.delete_selected_product_images_view),
                name="catalog_product_images_delete_selected",
            ),
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
            {
                "fields": (
                    "placement",
                    "side",
                    "is_universal_fitment",
                    "preserve_manual_fitment_content",
                )
            },
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

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        if product.preserve_manual_fitment_content:
            _regenerate_manual_fitment_descriptions(product)

    def delete_selected_product_images_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])

        product = self.get_object(request, object_id)
        if product is None:
            raise Http404("Product does not exist.")

        if not self.has_change_permission(request, product) or not self.has_delete_permission(
            request, product
        ):
            raise PermissionDenied

        product_url = reverse("admin:catalog_product_change", args=[product.pk])
        image_ids = request.POST.getlist("image_ids")
        images = ProductImage.objects.filter(pk__in=image_ids, product=product)
        deleted_count = images.count()

        if deleted_count:
            images.delete()
            messages.success(
                request,
                f"Deleted {deleted_count} selected product image"
                f"{'' if deleted_count == 1 else 's'}.",
            )
        else:
            messages.warning(request, "No product images were selected for deletion.")

        return HttpResponseRedirect(f"{product_url}#images-group")

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

                if action in {"manual", "auto"}:
                    self._apply_image_padding_from_post(image, request.POST)
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
                    "image_padding",
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
            "image_padding": image.image_padding,
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

    @staticmethod
    def _apply_image_padding_from_post(image, post_data):
        try:
            value = Decimal(str(post_data.get("image_padding", image.image_padding)))
        except Exception as exc:
            raise ValueError("Image padding is invalid.") from exc
        if value < 0 or value > 40:
            raise ValueError("Image padding must be between 0 and 40 percent.")
        image.image_padding = value.quantize(Decimal("0.01"))

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

    @admin.action(description="Block selected Cross Motors products from supplier import")
    def action_block_supplier_products(self, request, queryset):
        skus = list(
            queryset.filter(sku__startswith=CROSSMOTORS_SKU_PREFIX)
            .values_list("sku", flat=True)
        )
        if not skus:
            self.message_user(
                request,
                "No Cross Motors products were selected.",
                level=messages.WARNING,
            )
            return

        with transaction.atomic():
            SupplierProductBlock.objects.bulk_create(
                [
                    SupplierProductBlock(
                        source_name=CROSSMOTORS_SOURCE_NAME,
                        supplier_sku=sku,
                    )
                    for sku in skus
                ],
                ignore_conflicts=True,
            )
            Product.objects.filter(sku__in=skus).update(status=ProductStatus.ARCHIVED)

        transaction.on_commit(
            lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
        )
        self.message_user(
            request,
            f"Blocked {len(skus)} Cross Motors product(s) from supplier import and archived them.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Allow selected Cross Motors products in supplier import")
    def action_allow_supplier_products(self, request, queryset):
        skus = list(
            queryset.filter(sku__startswith=CROSSMOTORS_SKU_PREFIX)
            .values_list("sku", flat=True)
        )
        if not skus:
            self.message_user(
                request,
                "No Cross Motors products were selected.",
                level=messages.WARNING,
            )
            return

        deleted_count, _ = SupplierProductBlock.objects.filter(
            source_name=CROSSMOTORS_SOURCE_NAME,
            supplier_sku__in=skus,
        ).delete()

        self.message_user(
            request,
            f"Allowed {deleted_count} Cross Motors product(s) to be imported again.",
            level=messages.SUCCESS,
        )


@admin.register(SupplierProductBlock)
class SupplierProductBlockAdmin(admin.ModelAdmin):
    list_display = ("source_name", "supplier_sku", "note", "created_at", "updated_at")
    list_filter = ("source_name",)
    search_fields = ("source_name", "supplier_sku", "note")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("source_name", "supplier_sku")
