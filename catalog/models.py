import os
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Upper
from PIL import Image, ImageOps

from common.image_processing import (
    build_contained_webp_content,
    build_conversion_update_fields,
    build_resized_webp_content,
    convert_image_field_to_webp,
    detect_content_crop_box,
    save_generated_webp_to_field,
)


def product_image_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    product_id = instance.product_id or "unsaved"
    return f"catalog/products/{product_id}/images/{uuid.uuid4().hex}{ext}"


def category_image_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    category_id = instance.pk or instance.slug or "unsaved"
    return f"catalog/categories/{category_id}/images/{uuid.uuid4().hex}{ext}"


CUSTOMER_STOCK_RESERVE_QTY = 5


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    STANDARDIZED_VARIANT_SPECS = {
        "image_desktop": ((1440, 1440), "desktop"),
        "image_tablet": ((1080, 1080), "tablet"),
        "image_mobile": ((720, 720), "mobile"),
    }

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    image_original = models.ImageField(
        upload_to=category_image_upload_to,
        blank=True,
        null=True,
    )
    image_desktop = models.ImageField(
        upload_to=category_image_upload_to,
        blank=True,
        null=True,
    )
    image_tablet = models.ImageField(
        upload_to=category_image_upload_to,
        blank=True,
        null=True,
    )
    image_mobile = models.ImageField(
        upload_to=category_image_upload_to,
        blank=True,
        null=True,
    )
    image_alt_text = models.CharField(max_length=255, blank=True)
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.TextField(blank=True, null=True)
    seo_image = models.ImageField(upload_to="seo/", blank=True, null=True)
    seo_noindex = models.BooleanField(default=False)
    seo_canonical_url = models.CharField(max_length=500, blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        related_name="children",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)
    markup_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("1000.00")),
        ],
        help_text="Default markup percentage used to calculate customer prices for products in this category.",
    )
    default_shipping_weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Default packaged product weight in kilograms for EasyWay quotes.",
    )
    default_shipping_length_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Default packaged product length in centimeters for EasyWay quotes.",
    )
    default_shipping_width_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Default packaged product width in centimeters for EasyWay quotes.",
    )
    default_shipping_height_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Default packaged product height in centimeters for EasyWay quotes.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    markup_percent__gte=Decimal("0.00"),
                    markup_percent__lte=Decimal("1000.00"),
                ),
                name="catalog_category_markup_range",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def clean(self):
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "Category cannot be parent of itself."})

    def save(self, *args, **kwargs):
        tracked_fields = {
            "image_original",
            "image_desktop",
            "image_tablet",
            "image_mobile",
        }
        update_fields = kwargs.get("update_fields")
        update_field_set = set(update_fields) if update_fields is not None else None
        original_changed = False

        if self.pk and (update_field_set is None or "image_original" in update_field_set):
            previous_original_name = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("image_original", flat=True)
                .first()
            )
            original_changed = str(previous_original_name or "") != str(
                self.image_original.name or ""
            )
        elif self.image_original:
            original_changed = True

        variants_missing = any(
            not getattr(self, field_name)
            for field_name in self.STANDARDIZED_VARIANT_SPECS
        )

        super().save(*args, **kwargs)

        if update_field_set is not None and tracked_fields.isdisjoint(update_field_set):
            return

        if self.image_original and (original_changed or variants_missing):
            generated_fields = self._generate_variants_from_original()
            if generated_fields:
                super().save(
                    update_fields=build_conversion_update_fields(self, generated_fields)
                )
            return

        if self.image_original:
            return

        converted_fields = self._convert_variants_to_webp()
        if converted_fields:
            super().save(update_fields=build_conversion_update_fields(self, converted_fields))

    def _generate_variants_from_original(self):
        generated_fields = []
        source_name = str(self.image_original.name or "")

        for field_name, (size, suffix) in self.STANDARDIZED_VARIANT_SPECS.items():
            content = build_contained_webp_content(
                self.image_original,
                size=size,
                background_color=(255, 255, 255),
                quality=85,
            )
            target_field = getattr(self, field_name)
            if save_generated_webp_to_field(
                target_field,
                source_name,
                content,
                suffix=suffix,
            ):
                generated_fields.append(field_name)

        return generated_fields

    def _convert_variants_to_webp(self):
        converted_fields = []
        for field_name in ("image_desktop", "image_tablet", "image_mobile"):
            image_field = getattr(self, field_name)
            if convert_image_field_to_webp(image_field, quality=85):
                converted_fields.append(field_name)

        return converted_fields

    def _fallback_image(self, *field_names):
        for field_name in field_names:
            image = getattr(self, field_name)
            if image:
                return image
        return None

    @property
    def desktop_image(self):
        return self._fallback_image("image_desktop", "image_tablet", "image_mobile")

    @property
    def tablet_image(self):
        return self._fallback_image("image_tablet", "image_desktop", "image_mobile")

    @property
    def mobile_image(self):
        return self._fallback_image("image_mobile", "image_tablet", "image_desktop")

    def __str__(self):
        return self.name


class Brand(TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        return self.name


class VehicleMake(TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        return self.name


class VehicleModel(TimeStampedModel):
    make = models.ForeignKey(
        VehicleMake,
        related_name="models",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("make__sort_order", "make__name", "sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["make", "slug"],
                name="catalog_unique_vehicle_model_slug_per_make",
            ),
        ]
        indexes = [
            models.Index(fields=["make", "is_active", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.make.name} {self.name}"


class VehicleEngine(TimeStampedModel):
    model = models.ForeignKey(
        VehicleModel,
        related_name="engines",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = (
            "model__make__sort_order",
            "model__make__name",
            "model__sort_order",
            "model__name",
            "sort_order",
            "name",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["model", "slug"],
                name="catalog_unique_vehicle_engine_slug_per_model",
            ),
        ]
        indexes = [
            models.Index(fields=["model", "is_active", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.model} {self.name}"


class ProductStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class SupplierProductBlock(TimeStampedModel):
    source_name = models.CharField(max_length=120)
    supplier_sku = models.CharField(max_length=64)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("source_name", "supplier_sku")
        constraints = [
            models.UniqueConstraint(
                fields=["source_name", "supplier_sku"],
                name="catalog_unique_supplier_product_block",
            ),
        ]

    def __str__(self):
        return f"{self.source_name}: {self.supplier_sku}"


class ProductPlacement(models.TextChoices):
    FRONT = "front", "Front"
    REAR = "rear", "Rear"
    UPPER = "upper", "Upper"
    LOWER = "lower", "Lower"
    INNER = "inner", "Inner"
    OUTER = "outer", "Outer"


class ProductSide(models.TextChoices):
    LEFT = "left", "Left"
    RIGHT = "right", "Right"
    BOTH = "both", "Both"
    CENTER = "center", "Center"


class Product(TimeStampedModel):
    category = models.ForeignKey(
        Category,
        related_name="products",
        on_delete=models.PROTECT,
    )
    brand = models.ForeignKey(
        Brand,
        related_name="products",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    sku = models.CharField(max_length=64, unique=True)
    manufacturer_part_number = models.CharField(max_length=120, blank=True)
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.TextField(blank=True, null=True)
    seo_image = models.ImageField(upload_to="seo/", blank=True, null=True)
    seo_noindex = models.BooleanField(default=False)
    seo_canonical_url = models.CharField(max_length=500, blank=True, null=True)
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    supplier_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Private supplier cost. Customer-facing price is calculated from this value and markup.",
    )
    markup_percent_override = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("1000.00")),
        ],
        help_text="Optional product-specific markup percentage. Leave empty to use the category markup.",
    )
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    shipping_weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Optional packaged weight override in kilograms. Leave empty to use the category default.",
    )
    shipping_length_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Optional packaged length override in centimeters. Leave empty to use the category default.",
    )
    shipping_width_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Optional packaged width override in centimeters. Leave empty to use the category default.",
    )
    shipping_height_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Optional packaged height override in centimeters. Leave empty to use the category default.",
    )
    placement = models.CharField(
        max_length=20,
        choices=ProductPlacement.choices,
        blank=True,
    )
    side = models.CharField(
        max_length=20,
        choices=ProductSide.choices,
        blank=True,
    )
    stock_qty = models.PositiveIntegerField(default=0)
    is_new = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_universal_fitment = models.BooleanField(default=False, db_index=True)
    preserve_manual_fitment_content = models.BooleanField(
        default=False,
        help_text=(
            "Keep manually edited fitments, descriptions, and specs during supplier imports. "
            "Supplier price and stock will still be refreshed."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=Decimal("0.00")),
                name="catalog_product_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(supplier_price__isnull=True)
                    | Q(supplier_price__gte=Decimal("0.00"))
                ),
                name="catalog_product_supplier_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(markup_percent_override__isnull=True)
                    | Q(
                        markup_percent_override__gte=Decimal("0.00"),
                        markup_percent_override__lte=Decimal("1000.00"),
                    )
                ),
                name="catalog_product_markup_range",
            ),
            models.CheckConstraint(
                condition=Q(old_price__isnull=True) | Q(old_price__gt=F("price")),
                name="catalog_product_old_price_above_price",
            ),
        ]
        indexes = [
            models.Index(fields=["category", "status"]),
            models.Index(fields=["brand", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["is_featured", "is_new"]),
            models.Index(fields=["placement", "side"]),
            models.Index(fields=["is_universal_fitment", "status"]),
            GinIndex(
                OpClass(Upper("name"), name="gin_trgm_ops"),
                name="catalog_product_name_trgm",
            ),
            GinIndex(
                OpClass(
                    Upper("manufacturer_part_number"),
                    name="gin_trgm_ops",
                ),
                name="catalog_product_mpn_trgm",
            ),
        ]

    def clean(self):
        if self.supplier_price is not None:
            self.price = self.calculate_customer_price()

        if self.old_price is not None and self.old_price <= self.price:
            raise ValidationError(
                {
                    "old_price": (
                        "Old price must be greater than current price. "
                        "Leave it empty if product is not on sale."
                    )
                }
            )

    def save(self, *args, **kwargs):
        pricing_update_fields = {
            "supplier_price",
            "markup_percent_override",
            "category",
            "category_id",
            "price",
        }
        update_fields = kwargs.get("update_fields")
        update_field_set = set(update_fields) if update_fields is not None else None
        should_recalculate_price = (
            self.supplier_price is not None
            and (
                update_field_set is None
                or not pricing_update_fields.isdisjoint(update_field_set)
            )
        )

        if should_recalculate_price:
            self.price = self.calculate_customer_price()
            if update_field_set is not None:
                update_field_set.add("price")
                kwargs["update_fields"] = list(update_field_set)

        super().save(*args, **kwargs)

    @property
    def customer_available_stock_qty(self):
        return max(self.stock_qty - CUSTOMER_STOCK_RESERVE_QTY, 0)

    @property
    def in_stock(self):
        return self.customer_available_stock_qty > 0

    @property
    def price_available(self):
        return self.price > Decimal("0.00")

    @property
    def purchasable(self):
        return self.in_stock and self.price_available

    @property
    def on_sale(self):
        return self.old_price is not None and self.old_price > self.price

    @property
    def effective_markup_percent(self):
        if self.markup_percent_override is not None:
            return self.markup_percent_override

        category = getattr(self, "category", None)
        if category is not None:
            return category.markup_percent

        return Decimal("0.00")

    def _effective_shipping_value(self, product_field, category_field):
        value = getattr(self, product_field)
        if value is not None:
            return value

        category = getattr(self, "category", None)
        if category is None:
            return None
        return getattr(category, category_field)

    @property
    def effective_shipping_weight_kg(self):
        return self._effective_shipping_value(
            "shipping_weight_kg",
            "default_shipping_weight_kg",
        )

    @property
    def effective_shipping_length_cm(self):
        return self._effective_shipping_value(
            "shipping_length_cm",
            "default_shipping_length_cm",
        )

    @property
    def effective_shipping_width_cm(self):
        return self._effective_shipping_value(
            "shipping_width_cm",
            "default_shipping_width_cm",
        )

    @property
    def effective_shipping_height_cm(self):
        return self._effective_shipping_value(
            "shipping_height_cm",
            "default_shipping_height_cm",
        )

    @property
    def has_complete_shipping_measurements(self):
        return all(
            value is not None
            for value in (
                self.effective_shipping_weight_kg,
                self.effective_shipping_length_cm,
                self.effective_shipping_width_cm,
                self.effective_shipping_height_cm,
            )
        )

    def calculate_customer_price(self):
        if self.supplier_price is None:
            return self.price

        supplier_price = Decimal(str(self.supplier_price))
        markup_percent = Decimal(str(self.effective_markup_percent or Decimal("0.00")))
        multiplier = Decimal("1.00") + (markup_percent / Decimal("100"))
        return (supplier_price * multiplier).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def __str__(self):
        return self.name


class ProductFitment(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        related_name="fitments",
        on_delete=models.CASCADE,
    )
    vehicle_model = models.ForeignKey(
        VehicleModel,
        related_name="product_fitments",
        on_delete=models.PROTECT,
    )
    engine = models.ForeignKey(
        VehicleEngine,
        related_name="product_fitments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    year_from = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2100)]
    )
    year_to = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2100)]
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = (
            "vehicle_model__make__name",
            "vehicle_model__name",
            "year_from",
            "year_to",
            "engine__name",
        )
        constraints = [
            models.CheckConstraint(
                condition=Q(year_to__gte=F("year_from")),
                name="catalog_fitment_year_range_valid",
            ),
            models.UniqueConstraint(
                fields=["product", "vehicle_model", "engine", "year_from", "year_to"],
                name="catalog_unique_product_fitment",
            ),
            models.UniqueConstraint(
                fields=["product", "vehicle_model", "year_from", "year_to"],
                condition=Q(engine__isnull=True),
                name="catalog_unique_generic_product_fitment",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "vehicle_model"]),
            models.Index(fields=["vehicle_model", "year_from", "year_to"]),
            models.Index(fields=["engine", "year_from", "year_to"]),
        ]

    def clean(self):
        if self.year_from > self.year_to:
            raise ValidationError(
                {"year_to": "year_to must be greater than or equal to year_from."}
            )

        if (
            self.engine_id
            and self.vehicle_model_id
            and self.engine.model_id != self.vehicle_model_id
        ):
            raise ValidationError(
                {"engine": "Engine must belong to the selected vehicle model."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        year_range = (
            str(self.year_from)
            if self.year_from == self.year_to
            else f"{self.year_from}-{self.year_to}"
        )
        engine = f" {self.engine.name}" if self.engine_id else ""
        return f"{self.product.name}: {self.vehicle_model} {year_range}{engine}"


class ProductImage(TimeStampedModel):
    STANDARDIZED_VARIANT_SPECS = {
        "image_desktop": ((1440, 1440), "desktop"),
        "image_tablet": ((1080, 1080), "tablet"),
        "image_mobile": ((720, 720), "mobile"),
    }

    product = models.ForeignKey(
        Product,
        related_name="images",
        on_delete=models.CASCADE,
    )
    image_original = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    image_desktop = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    image_tablet = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    image_mobile = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    image_ai_background = models.ImageField(
        upload_to=product_image_upload_to, blank=True, null=True
    )
    use_ai_background = models.BooleanField(
        "AI-ით თეთრი ფონის გამოყენება",
        default=False,
    )
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    crop_x = models.DecimalField(max_digits=6, decimal_places=5, blank=True, null=True)
    crop_y = models.DecimalField(max_digits=6, decimal_places=5, blank=True, null=True)
    crop_width = models.DecimalField(max_digits=6, decimal_places=5, blank=True, null=True)
    crop_height = models.DecimalField(max_digits=6, decimal_places=5, blank=True, null=True)
    image_padding = models.DecimalField(max_digits=5, decimal_places=2, default=12)
    replace_background_with_white = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_one_primary_image_per_product",
            )
        ]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def clean(self):
        has_any_image = any(
            [
                self.image_original,
                self.image_desktop,
                self.image_tablet,
                self.image_mobile,
            ]
        )
        if not has_any_image:
            raise ValidationError("At least one image upload is required.")

    def save(self, *args, **kwargs):
        tracked_fields = {
            "image_original",
            "image_desktop",
            "image_tablet",
            "image_mobile",
            "image_ai_background",
            "use_ai_background",
            "crop_x",
            "crop_y",
            "crop_width",
            "crop_height",
            "image_padding",
            "replace_background_with_white",
        }
        crop_fields = {"crop_x", "crop_y", "crop_width", "crop_height"}
        update_fields = kwargs.get("update_fields")
        update_field_set = set(update_fields) if update_fields is not None else None
        original_changed = False
        crop_changed = False
        background_changed = False

        if self.pk and (
            update_field_set is None
            or "image_original" in update_field_set
            or not crop_fields.isdisjoint(update_field_set)
            or "replace_background_with_white" in update_field_set
            or "image_padding" in update_field_set
            or "image_ai_background" in update_field_set
            or "use_ai_background" in update_field_set
        ):
            previous_values = (
                type(self)
                .objects.filter(pk=self.pk)
                .values(
                    "image_original",
                    "image_ai_background",
                    "use_ai_background",
                    "crop_x",
                    "crop_y",
                    "crop_width",
                    "crop_height",
                    "image_padding",
                    "replace_background_with_white",
                )
                .first()
            )
            if previous_values:
                original_changed = str(previous_values["image_original"] or "") != str(
                    self.image_original.name or ""
                )
                crop_changed = any(
                    previous_values[field_name] != getattr(self, field_name)
                    for field_name in crop_fields
                )
                background_changed = (
                    previous_values["replace_background_with_white"]
                    != self.replace_background_with_white
                    or previous_values["image_padding"] != self.image_padding
                    or str(previous_values["image_ai_background"] or "")
                    != str(self.image_ai_background.name or "")
                    or previous_values["use_ai_background"] != self.use_ai_background
                )
        elif self.image_original:
            original_changed = True

        variants_missing = any(
            not getattr(self, field_name)
            for field_name in self.STANDARDIZED_VARIANT_SPECS
        )

        super().save(*args, **kwargs)

        if update_field_set is not None and tracked_fields.isdisjoint(update_field_set):
            return

        if self.image_original and (
            original_changed or crop_changed or background_changed or variants_missing
        ):
            generated_fields = self._generate_variants_from_original()
            if generated_fields:
                super().save(
                    update_fields=build_conversion_update_fields(self, generated_fields)
                )
            return

        if self.image_original:
            return

        converted_fields = self._convert_variants_to_webp()
        if converted_fields:
            super().save(update_fields=build_conversion_update_fields(self, converted_fields))

    def _generate_variants_from_original(self):
        generated_fields = []
        source_image = (
            self.image_ai_background
            if self.use_ai_background and self.image_ai_background
            else self.image_original
        )
        source_name = str(source_image.name or self.image_original.name or "")
        crop_box = self._get_crop_box()

        for field_name, (size, suffix) in self.STANDARDIZED_VARIANT_SPECS.items():
            content = build_resized_webp_content(
                source_image,
                max_size=size,
                crop_box=crop_box,
                padding_ratio=float(self.image_padding or 0) / 100,
                replace_background=self.replace_background_with_white,
                quality=85,
            )
            target_field = getattr(self, field_name)
            if save_generated_webp_to_field(
                target_field,
                source_name,
                content,
                suffix=suffix,
            ):
                generated_fields.append(field_name)

        return generated_fields

    def has_crop(self):
        return all(
            value is not None
            for value in (self.crop_x, self.crop_y, self.crop_width, self.crop_height)
        )

    def clear_crop(self):
        self.crop_x = None
        self.crop_y = None
        self.crop_width = None
        self.crop_height = None

    def set_crop_from_box(self, crop_box, *, image_size):
        left, top, right, bottom = crop_box
        width, height = image_size
        if width <= 0 or height <= 0 or right <= left or bottom <= top:
            self.clear_crop()
            return

        self.crop_x = Decimal(str(max(min(left / width, 1), 0))).quantize(Decimal("0.00001"))
        self.crop_y = Decimal(str(max(min(top / height, 1), 0))).quantize(Decimal("0.00001"))
        self.crop_width = Decimal(str(max(min((right - left) / width, 1), 0))).quantize(Decimal("0.00001"))
        self.crop_height = Decimal(str(max(min((bottom - top) / height, 1), 0))).quantize(Decimal("0.00001"))

    def auto_crop_from_original(self):
        crop_box = detect_content_crop_box(self.image_original)
        if not crop_box:
            return False

        self.image_original.open("rb")
        try:
            with Image.open(self.image_original) as img:
                img = ImageOps.exif_transpose(img)
                self.set_crop_from_box(crop_box, image_size=img.size)
        finally:
            self.image_original.close()
        return self.has_crop()

    def _get_crop_box(self):
        if not self.has_crop() or not self.image_original:
            return None

        self.image_original.open("rb")
        try:
            with Image.open(self.image_original) as img:
                img = ImageOps.exif_transpose(img)
                width, height = img.size
        finally:
            self.image_original.close()

        left = int(Decimal(self.crop_x) * width)
        top = int(Decimal(self.crop_y) * height)
        right = int((Decimal(self.crop_x) + Decimal(self.crop_width)) * width)
        bottom = int((Decimal(self.crop_y) + Decimal(self.crop_height)) * height)

        left = max(min(left, width - 1), 0)
        top = max(min(top, height - 1), 0)
        right = max(min(right, width), left + 1)
        bottom = max(min(bottom, height), top + 1)

        return (left, top, right, bottom)

    def _convert_variants_to_webp(self):
        converted_fields = []
        for field_name in ("image_desktop", "image_tablet", "image_mobile"):
            image_field = getattr(self, field_name)
            if convert_image_field_to_webp(image_field, quality=85):
                converted_fields.append(field_name)

        return converted_fields

    def _fallback_image(self, *field_names):
        for field_name in field_names:
            image = getattr(self, field_name)
            if image:
                return image
        return None

    @property
    def desktop_image(self):
        return self._fallback_image("image_desktop", "image_tablet", "image_mobile")

    @property
    def tablet_image(self):
        return self._fallback_image("image_tablet", "image_desktop", "image_mobile")

    @property
    def mobile_image(self):
        return self._fallback_image("image_mobile", "image_tablet", "image_desktop")

    def __str__(self):
        return f"{self.product.name} image {self.sort_order}"


class ProductSpec(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        related_name="specs",
        on_delete=models.CASCADE,
    )
    key = models.CharField(max_length=120)
    value = models.CharField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "key"],
                name="catalog_unique_spec_key_per_product",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.product.name}: {self.key}"
