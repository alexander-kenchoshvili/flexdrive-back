import os
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from common.image_processing import (
    build_contained_webp_content,
    build_conversion_update_fields,
    convert_image_field_to_webp,
    save_generated_webp_to_field,
)


def product_image_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    product_id = instance.product_id or "unsaved"
    return f"catalog/products/{product_id}/images/{uuid.uuid4().hex}{ext}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def clean(self):
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "Category cannot be parent of itself."})

    def __str__(self):
        return self.name


class ProductStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class Product(TimeStampedModel):
    category = models.ForeignKey(
        Category,
        related_name="products",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    sku = models.CharField(max_length=64, unique=True)
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
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    stock_qty = models.PositiveIntegerField(default=0)
    is_new = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=["category", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["is_featured", "is_new"]),
        ]

    def clean(self):
        if self.old_price is not None and self.old_price <= self.price:
            raise ValidationError(
                {
                    "old_price": (
                        "Old price must be greater than current price. "
                        "Leave it empty if product is not on sale."
                    )
                }
            )

    @property
    def in_stock(self):
        return self.stock_qty > 0

    @property
    def on_sale(self):
        return self.old_price is not None and self.old_price > self.price

    def __str__(self):
        return self.name


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
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)

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
