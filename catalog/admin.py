from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.forms.models import BaseInlineFormSet
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.http import urlencode
from PIL import Image, ImageOps
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups

from .background_removal import remove_background_to_white
from .internal_skus import assign_admin_sku, category_sequence

from .models import (
    CUSTOMER_STOCK_RESERVE_QTY,
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductImage,
    ProductPlacement,
    ProductSide,
    ProductSpec,
    ProductStatus,
    ProductSupplierSource,
    SupplierProductBlock,
    SupplierSyncReport,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)
from commerce.models import SupplierStockHold, SupplierStockHoldStatus

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

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("use_ai_background")
            and not cleaned_data.get("image_ai_background")
        ):
            self.add_error(
                "use_ai_background",
                "Create and apply an AI background preview before saving.",
            )
        return cleaned_data

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
        "use_ai_background",
        "image_ai_background",
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


class SupplierStockHoldInline(admin.TabularInline):
    model = SupplierStockHold
    fk_name = "product"
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "order_item",
        "quantity",
        "status",
        "expires_at",
        "released_at",
        "released_by",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


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
            return queryset.filter(stock_qty__gt=CUSTOMER_STOCK_RESERVE_QTY)
        if value == "no":
            return queryset.filter(stock_qty__lte=CUSTOMER_STOCK_RESERVE_QTY)
        return queryset


class ActiveSupplierHoldListFilter(admin.SimpleListFilter):
    title = "დროებითი დაცვა"
    parameter_name = "active_supplier_hold"

    def lookups(self, request, model_admin):
        return (
            ("yes", "მოქმედებს"),
            ("no", "არ მოქმედებს"),
        )

    def queryset(self, request, queryset):
        active_filter = Q(
            supplier_stock_holds__status=SupplierStockHoldStatus.ACTIVE,
            supplier_stock_holds__expires_at__gt=timezone.now(),
        )
        if self.value() == "yes":
            return queryset.filter(active_filter).distinct()
        if self.value() == "no":
            return queryset.exclude(active_filter).distinct()
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "parent",
        "sort_order",
        "has_shipping_defaults",
        "is_active",
        "has_image",
        "updated_at",
    )
    list_filter = ("is_active", "parent")
    readonly_fields = ("sku_sequence",)
    search_fields = ("name", "slug")
    list_editable = ("sort_order", "is_active")
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
                    "is_active",
                    "sku_sequence",
                )
            },
        ),
        (
            "Delivery defaults",
            {
                "fields": (
                    "default_shipping_weight_kg",
                    "default_shipping_length_cm",
                    "default_shipping_width_cm",
                    "default_shipping_height_cm",
                ),
                "description": (
                    "Packaged weight and dimensions used when a product does not "
                    "have its own EasyWay override."
                ),
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

    @admin.display(boolean=True, description="shipping defaults")
    def has_shipping_defaults(self, obj):
        return all(
            value is not None
            for value in (
                obj.default_shipping_weight_kg,
                obj.default_shipping_length_cm,
                obj.default_shipping_width_cm,
                obj.default_shipping_height_cm,
            )
        )

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


class MarkupDisplayInput(forms.NumberInput):
    def format_value(self, value):
        if value not in (None, ""):
            try:
                value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except (ArithmeticError, ValueError):
                pass
        return super().format_value(value)


class ProductAdminForm(forms.ModelForm):
    pricing_input = forms.ChoiceField(
        choices=(("", "Automatic"), ("price", "Price"), ("markup", "Markup"), ("supplier", "Supplier")),
        required=False,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "price" in self.fields:
            self.fields["price"].required = False
            self.fields["price"].label = "ჩვენი გასაყიდი ფასი (₾)"
            self.fields["price"].help_text = (
                "თანხის ჩაწერა ავტომატურად ითვლის ინდივიდუალურ ფასნამატს. "
                "მომწოდებლის ფასის ცვლილებისას შენარჩუნდება ფასნამატის პროცენტი."
            )
        if "markup_percent_override" in self.fields:
            exact = self.initial.get("markup_percent_override")
            if self.is_bound:
                submitted = self.data.get(self.add_prefix("markup_percent_override"))
                try:
                    rounded_initial = Decimal(str(exact or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if self.data.get(self.add_prefix("pricing_input")) == "markup" or Decimal(submitted or "0") != rounded_initial:
                        exact = submitted
                except (ArithmeticError, ValueError):
                    pass
            self.fields["markup_percent_override"].widget = MarkupDisplayInput(attrs={
                "step": "0.01", "data-exact-markup": str(exact or 0),
            })
            self.fields["markup_percent_override"].label = "ინდივიდუალური ფასნამატი (%)"
            self.fields["markup_percent_override"].help_text = (
                "პროცენტის შეცვლა განაახლებს გასაყიდ ფასს. "
                "ცარიელი ველი ნიშნავს 0%-ს. კატეგორია ფასზე არ მოქმედებს."
            )

    def clean(self):
        data = super().clean()
        category = data.get("category")
        can_assign = category is not None and category_sequence(category) is not None
        self.instance._admin_sku_pending = not self.instance.internal_sku and can_assign
        supplier = data.get("supplier_price")
        price = data.get("price")
        mode = data.get("pricing_input")
        original_markup = self.initial.get("markup_percent_override")
        submitted_markup = data.get("markup_percent_override")
        markup_changed = "markup_percent_override" in self.changed_data
        if original_markup is not None and submitted_markup is not None:
            original_markup = Decimal(str(original_markup))
            if mode != "markup" and submitted_markup == original_markup.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
                # Display rounding is not an edit. Never replace the stored
                # precision when saving another field or changing supplier cost.
                data["markup_percent_override"] = original_markup
                markup_changed = False
        # Also support submissions without JavaScript: an edited price alone
        # selects amount entry; an edited markup takes precedence otherwise.
        from_price = mode == "price" or (
            not mode and "price" in self.changed_data
            and not markup_changed
        )
        if data.get("markup_percent_override") is None and "markup_percent_override" not in self.errors:
            data["markup_percent_override"] = Decimal("0")
        if supplier is None:
            if price is None and "price" not in self.errors:
                self.add_error("price", "შეიყვანეთ გასაყიდი ფასი.")
        elif from_price:
            if price is None:
                if "price" not in self.errors:
                    self.add_error("price", "შეიყვანეთ გასაყიდი ფასი.")
            elif supplier == 0:
                if price != 0:
                    self.add_error("price", "ფასნამატის გამოსათვლელად მომწოდებლის ფასი უნდა იყოს ნულზე მეტი.")
            else:
                markup = (price / supplier - Decimal("1")) * Decimal("100")
                if not Decimal("0") <= markup <= Decimal("1000"):
                    self.add_error("price", "გასაყიდი ფასი უნდა შეესაბამებოდეს 0–1000% ფასნამატს.")
                else:
                    # Ten decimal places preserve cent-exact amount entry even
                    # at the largest supported supplier price.
                    data["markup_percent_override"] = markup.quantize(
                        Decimal("0.0000000001"), rounding=ROUND_HALF_UP,
                    )
        elif "supplier_price" not in self.errors:
            markup = data.get("markup_percent_override")
            if markup is None:
                markup = Decimal("0")
            data["price"] = (supplier * (1 + markup / Decimal("100"))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )
        return data


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "sku" in form.base_fields:
            form.base_fields["sku"].label = "მომწოდებლის / არსებული SKU"
            form.base_fields["sku"].help_text = "მხოლოდ შიდა ინტეგრაციებისთვის. FlexDrive SKU კატეგორიით შენახვისას ავტომატურად შეიქმნება."
        return form

    list_display = (
        "name",
        "sku",
        "internal_sku",
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
        "supplier_stock_list",
        "temporary_hold_list",
        "site_sellable_stock_list",
        "supplier_stock_health_list",
        "supplier_stock_synced_at",
        "has_shipping_measurements",
        "in_stock_flag",
        "updated_at",
    )
    list_filter = (
        "status",
        "supplier_missing",
        "category",
        "brand",
        "placement",
        "side",
        "is_new",
        "is_featured",
        "is_universal_fitment",
        "supplier_source",
        ActiveSupplierHoldListFilter,
        OnSaleListFilter,
        InStockListFilter,
    )
    search_fields = (
        "name",
        "sku",
        "internal_sku",
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
    inlines = (
        ProductImageInline,
        ProductSpecInline,
        ProductFitmentInline,
        SupplierStockHoldInline,
    )
    readonly_fields = (
        "supplier_missing",
        "effective_markup_percent_readonly",
        "calculated_customer_price_readonly",
        "on_sale_readonly",
        "in_stock_readonly",
        "supplier_source",
        "supplier_stock_qty",
        "supplier_stock_synced_at",
        "temporary_hold_readonly",
        "site_sellable_stock_readonly",
        "effective_shipping_measurements_readonly",
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
            "catalog/admin_product_image_camera_v4.js",
        )
        css = {
            "all": ("catalog/admin_product_image_camera_v4.css",),
        }

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "images/ai-background-preview/",
                self.admin_site.admin_view(self.ai_background_preview_view),
                name="catalog_productimage_ai_background_preview",
            ),
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
                    "internal_sku",
                    "manufacturer_part_number",
                    "brand",
                    "category",
                    "status",
                    "supplier_missing",
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
                    "pricing_input",
                    "supplier_price",
                    "markup_percent_override",
                    "calculated_customer_price_readonly",
                    "price",
                    "old_price",
                    "on_sale_readonly",
                )
            },
        ),
        (
            "Delivery measurements",
            {
                "fields": (
                    "shipping_weight_kg",
                    "shipping_length_cm",
                    "shipping_width_cm",
                    "shipping_height_cm",
                    "effective_shipping_measurements_readonly",
                ),
                "description": (
                    "Optional packaged weight and dimension overrides. Leave fields "
                    "empty to use the category defaults."
                ),
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
        (
            "Inventory",
            {
                "fields": (
                    "supplier_source",
                    "supplier_stock_qty",
                    "temporary_hold_readonly",
                    "stock_qty",
                    "site_sellable_stock_readonly",
                    "supplier_stock_synced_at",
                    "in_stock_readonly",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(boolean=True, description="On sale")
    def on_sale_flag(self, obj):
        return obj.on_sale

    @admin.display(boolean=True, description="In stock")
    def in_stock_flag(self, obj):
        return obj.in_stock

    @admin.display(boolean=True, description="Shipping data")
    def has_shipping_measurements(self, obj):
        return obj.has_complete_shipping_measurements

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

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _active_supplier_hold_qty=Coalesce(
                Sum(
                    "supplier_stock_holds__quantity",
                    filter=Q(
                        supplier_stock_holds__status=SupplierStockHoldStatus.ACTIVE,
                        supplier_stock_holds__expires_at__gt=timezone.now(),
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            )
        )

    @admin.display(description="Cross Motors-ის ნაშთი", ordering="supplier_stock_qty")
    def supplier_stock_list(self, obj):
        if obj.supplier_source != ProductSupplierSource.CROSS_MOTORS:
            return "—"
        return obj.supplier_stock_qty if obj.supplier_stock_qty is not None else "—"

    @admin.display(description="დროებით დაკავებული")
    def temporary_hold_list(self, obj):
        if obj.supplier_source != ProductSupplierSource.CROSS_MOTORS:
            return "—"
        return getattr(obj, "_active_supplier_hold_qty", 0)

    @admin.display(description="საიტზე გასაყიდი", ordering="stock_qty")
    def site_sellable_stock_list(self, obj):
        return obj.customer_available_stock_qty

    @admin.display(description="მდგომარეობა")
    def supplier_stock_health_list(self, obj):
        if obj.supplier_source != ProductSupplierSource.CROSS_MOTORS:
            return "—"
        active_hold_qty = getattr(obj, "_active_supplier_hold_qty", 0)
        if obj.supplier_stock_synced_at is None:
            return format_html(
                '<strong style="color:#ba2121">{}</strong>',
                "სინქრონიზაცია არ არის",
            )
        if obj.supplier_stock_synced_at < timezone.now() - timedelta(minutes=30):
            return format_html(
                '<strong style="color:#ba2121">{}</strong>',
                "სინქრონიზაცია დაგვიანებულია",
            )
        if (
            obj.supplier_stock_qty is not None
            and active_hold_qty > obj.supplier_stock_qty
        ):
            return format_html(
                '<strong style="color:#ba2121">{}</strong>',
                "ხელით შემოწმებაა საჭირო",
            )
        if active_hold_qty:
            return format_html(
                '<strong style="color:#b36b00">{}</strong>',
                "დაცვა მოქმედებს",
            )
        return format_html(
            '<strong style="color:#138a36">{}</strong>',
            "ნორმალურია",
        )

    @admin.display(description="დროებით დაკავებული")
    def temporary_hold_readonly(self, obj):
        if not obj or obj.supplier_source != ProductSupplierSource.CROSS_MOTORS:
            return 0
        return (
            obj.supplier_stock_holds.filter(
                status=SupplierStockHoldStatus.ACTIVE,
                expires_at__gt=timezone.now(),
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
        )

    @admin.display(description="საიტზე გასაყიდი")
    def site_sellable_stock_readonly(self, obj):
        if not obj:
            return 0
        return obj.customer_available_stock_qty

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

    @admin.display(description="Applied delivery measurements")
    def effective_shipping_measurements_readonly(self, obj):
        if not obj or not obj.has_complete_shipping_measurements:
            return "Incomplete - add product overrides or category defaults"
        return (
            f"{obj.effective_shipping_weight_kg} kg; "
            f"{obj.effective_shipping_length_cm} x "
            f"{obj.effective_shipping_width_cm} x "
            f"{obj.effective_shipping_height_cm} cm"
        )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        readonly_fields.append("internal_sku")
        if (
            obj
            and obj.supplier_source == ProductSupplierSource.CROSS_MOTORS
            and "stock_qty" not in readonly_fields
        ):
            readonly_fields.append("stock_qty")
        return readonly_fields

    def save_model(self, request, obj, form, change):
        if "status" in form.changed_data:
            obj.supplier_missing = False
        with transaction.atomic():
            assign_admin_sku(obj)
            super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        if product.preserve_manual_fitment_content:
            _regenerate_manual_fitment_descriptions(product)

    def ai_background_preview_view(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not (
            self.has_add_permission(request)
            or self.has_change_permission(request)
        ):
            raise PermissionDenied

        upload = request.FILES.get("image")
        stored_image = None
        if upload is None:
            image_id = request.POST.get("image_id")
            stored_image = (
                ProductImage.objects.filter(pk=image_id)
                .select_related("product")
                .first()
            )
            if stored_image is None or not stored_image.image_original:
                return HttpResponse("Choose or take a photo first.", status=400)
            if not self.has_change_permission(request, stored_image.product):
                raise PermissionDenied
            upload = stored_image.image_original

        if getattr(upload, "size", 0) > 20 * 1024 * 1024:
            return HttpResponse("The image must be 20 MB or smaller.", status=400)

        try:
            content = remove_background_to_white(upload)
        except Exception:
            return HttpResponse(
                "Background removal failed. Try another photo.",
                status=422,
            )
        finally:
            if stored_image is not None:
                stored_image.image_original.close()
        return HttpResponse(content, content_type="image/jpeg")

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
        if queryset.filter(Q(internal_sku__isnull=True) | Q(internal_sku="")).exists():
            self.message_user(request, "ჯერ შეინახეთ თითოეული პროდუქტი საბოლოო კატეგორიით — საჭიროა FlexDrive SKU. არაფერი გამოქვეყნებულა.", level=messages.ERROR)
            return
        queryset.exclude(internal_sku__isnull=True).exclude(internal_sku="").update(status=ProductStatus.PUBLISHED, supplier_missing=False)
        transaction.on_commit(
            lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES)
        )

    @admin.action(description="Move selected products to draft")
    def action_unpublish(self, request, queryset):
        queryset.update(status=ProductStatus.DRAFT, supplier_missing=False)
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
            Product.objects.filter(sku__in=skus).update(status=ProductStatus.ARCHIVED, supplier_missing=False)

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


@admin.register(SupplierSyncReport)
class SupplierSyncReportAdmin(admin.ModelAdmin):
    list_display = ("started_at", "status", "summary", "finished_at")
    list_filter = ("status", "started_at")
    search_fields = ("summary",)
    date_hierarchy = "started_at"
    readonly_fields = ("started_at", "finished_at", "status", "summary", "change_details")
    fields = readonly_fields
    actions = ("delete_selected",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="მნიშვნელოვანი ცვლილებები")
    def change_details(self, obj):
        from .supplier_reports import CHANGE_LABELS, DETAIL_LIMIT

        legacy_skus = {
            item["sku"]
            for group in obj.changes.values()
            for item in group.get("items", [])
            if "internal_sku" not in item
        }
        legacy_codes = dict(
            Product.objects.filter(sku__in=legacy_skus).values_list("sku", "internal_sku")
        ) if legacy_skus else {}

        def display_sku(item):
            internal = item.get("internal_sku", legacy_codes.get(item["sku"]))
            return f"{item['sku']} / {internal}" if internal else item["sku"]

        sections = []
        for key, label in CHANGE_LABELS.items():
            group = obj.changes.get(key, {})
            if not group.get("count"):
                continue
            rows = format_html_join(
                "", "<li><strong>{}</strong> — {} {}</li>",
                ((display_sku(item), item["name"],
                  f"({item['before']} → {item['after']} GEL)" if "before" in item else "")
                 for item in group.get("items", [])),
            )
            note = f"ნაჩვენებია პირველი {DETAIL_LIMIT} პროდუქტი." if group["count"] > DETAIL_LIMIT else ""
            sections.append(format_html(
                "<h3>{}: {}</h3><ul>{}</ul><p>{}</p>", label, group["count"], rows, note,
            ))
        return format_html_join("", "{}", ((section,) for section in sections)) or "—"


@admin.register(SupplierProductBlock)
class SupplierProductBlockAdmin(admin.ModelAdmin):
    list_display = ("source_name", "supplier_sku", "note", "created_at", "updated_at")
    list_filter = ("source_name",)
    search_fields = ("source_name", "supplier_sku", "note")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("source_name", "supplier_sku")
