from django.core.exceptions import ValidationError
from django.db import models
from ckeditor.fields import RichTextField

from common.image_processing import (
    build_conversion_update_fields,
    build_resized_webp_content,
    convert_image_field_to_webp,
    save_generated_webp_to_field,
)
from common.models_mixins import WebPImageMixin



class Page(models.Model):
    class FooterGroup(models.TextChoices):
        NAVIGATION = "navigation", "Navigation"
        HELP = "help", "Help"
        LEGAL = "legal", "Legal"

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.TextField(blank=True, null=True)
    seo_image = models.ImageField(upload_to="seo/", blank=True, null=True)
    seo_noindex = models.BooleanField(default=False)
    seo_canonical_url = models.CharField(max_length=500, blank=True, null=True)

    show_in_menu = models.BooleanField(default=True)
    show_in_footer = models.BooleanField(default=False)
    footer_group = models.CharField(
        max_length=32,
        choices=FooterGroup.choices,
        blank=True,
        null=True,
    )
    footer_order = models.PositiveIntegerField(default=0)
    footer_label = models.CharField(max_length=255, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='children'
    )
    url = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name


class FooterSettings(models.Model):
    brand_name = models.CharField(max_length=255, default="AutoMate")
    brand_description = models.TextField(blank=True, null=True)
    trust_item_1 = models.CharField(max_length=255, blank=True, null=True)
    trust_item_2 = models.CharField(max_length=255, blank=True, null=True)
    trust_item_3 = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    working_hours = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    facebook_url = models.URLField(blank=True, null=True)
    copyright_text = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Footer Settings"
        verbose_name_plural = "Footer Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Footer Settings"


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=255, default="AutoMate")
    default_seo_title = models.CharField(max_length=255, blank=True, null=True)
    default_seo_description = models.TextField(blank=True, null=True)
    default_seo_image = models.ImageField(upload_to="seo/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Site Settings"



class ContactInquiryStatus(models.TextChoices):
    NEW = "new", "New"
    IN_PROGRESS = "in_progress", "In Progress"
    RESOLVED = "resolved", "Resolved"


class ContactInquiry(models.Model):
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=64)
    email = models.EmailField()
    topic_slug = models.SlugField(max_length=255)
    topic_label = models.CharField(max_length=255)
    order_number = models.CharField(max_length=120, blank=True)
    message = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=ContactInquiryStatus.choices,
        default=ContactInquiryStatus.NEW,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"{self.topic_label} - {self.full_name}"


class ComponentType(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Content(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class ContentItem(WebPImageMixin,models.Model):
    content = models.ForeignKey(Content, related_name='items', on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    editor = RichTextField(blank=True, null=True)
    slug = models.SlugField(max_length=255, unique=False, blank=True, null=True)
    singlePageRoute = models.ForeignKey(
        'Page',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="აირჩიე გვერდი, რომლის ქვეშაც უნდა ჩაჯდეს single view URL."
    )
    content_type = models.CharField(max_length=50, blank=True, null=True)
    position = models.PositiveIntegerField(default=0, db_index=True)
    icon_svg = models.TextField(blank=True, null=True)
    catalog_category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_content_items",
    )
    created_at = models.DateField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)




    def __str__(self):
        return self.title or f"Item of {self.content.name}"


class BlogStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"


class BlogPost(models.Model):
    TEASER_VARIANT_SPECS = {
        "teaser_image_desktop": ((1280, 960), "teaser-desktop"),
        "teaser_image_tablet": ((960, 720), "teaser-tablet"),
        "teaser_image_mobile": ((640, 640), "teaser-mobile"),
    }
    COVER_VARIANT_SPECS = {
        "cover_image_desktop": ((1600, 1200), "cover-desktop"),
        "cover_image_tablet": ((1200, 900), "cover-tablet"),
        "cover_image_mobile": ((800, 800), "cover-mobile"),
    }

    content_item = models.OneToOneField(
        "ContentItem",
        on_delete=models.CASCADE,
        related_name="blog_post",
        limit_choices_to={"content__name": "bloglist"},
    )
    excerpt = models.CharField(max_length=320, blank=True)
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.TextField(blank=True, null=True)
    seo_image = models.ImageField(upload_to="seo/", blank=True, null=True)
    seo_noindex = models.BooleanField(default=False)
    seo_canonical_url = models.CharField(max_length=500, blank=True, null=True)
    read_time_minutes = models.PositiveSmallIntegerField(default=1)
    author_name = models.CharField(max_length=120, blank=True)
    author_role = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=120, blank=True)
    tags = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated tags. Example: safety, maintenance, tips",
    )
    teaser_image_original = models.ImageField(upload_to="blog_posts/teasers/", blank=True, null=True)
    teaser_image_desktop = models.ImageField(upload_to="blog_posts/teasers/", blank=True, null=True)
    teaser_image_tablet = models.ImageField(upload_to="blog_posts/teasers/", blank=True, null=True)
    teaser_image_mobile = models.ImageField(upload_to="blog_posts/teasers/", blank=True, null=True)
    cover_image_original = models.ImageField(upload_to="blog_posts/covers/", blank=True, null=True)
    cover_image_desktop = models.ImageField(upload_to="blog_posts/covers/", blank=True, null=True)
    cover_image_tablet = models.ImageField(upload_to="blog_posts/covers/", blank=True, null=True)
    cover_image_mobile = models.ImageField(upload_to="blog_posts/covers/", blank=True, null=True)
    status = models.CharField(
        max_length=12,
        choices=BlogStatus.choices,
        default=BlogStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-published_at", "-id")
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["is_featured", "published_at"]),
        ]

    def clean(self):
        if self.status == BlogStatus.PUBLISHED and not self.published_at:
            raise ValidationError({"published_at": "Published posts must have published_at date."})

        if self.content_item_id:
            content_name = (self.content_item.content.name or "").lower()
            if content_name != "bloglist":
                raise ValidationError({"content_item": "Only bloglist ContentItem can be linked to BlogPost."})

    def save(self, *args, **kwargs):
        tracked_fields = {
            "teaser_image_original",
            "teaser_image_desktop",
            "teaser_image_tablet",
            "teaser_image_mobile",
            "cover_image_original",
            "cover_image_desktop",
            "cover_image_tablet",
            "cover_image_mobile",
        }
        update_fields = kwargs.get("update_fields")
        update_field_set = set(update_fields) if update_fields is not None else None

        teaser_original_changed = self._did_original_change(
            "teaser_image_original",
            update_field_set,
        )
        cover_original_changed = self._did_original_change(
            "cover_image_original",
            update_field_set,
        )
        teaser_variants_missing = any(
            not getattr(self, field_name) for field_name in self.TEASER_VARIANT_SPECS
        )
        cover_variants_missing = any(
            not getattr(self, field_name) for field_name in self.COVER_VARIANT_SPECS
        )

        super().save(*args, **kwargs)

        if update_field_set is not None and tracked_fields.isdisjoint(update_field_set):
            return

        generated_fields = []
        if self.teaser_image_original and (teaser_original_changed or teaser_variants_missing):
            generated_fields.extend(
                self._generate_variants_from_original(
                    "teaser_image_original",
                    self.TEASER_VARIANT_SPECS,
                )
            )
        if self.cover_image_original and (cover_original_changed or cover_variants_missing):
            generated_fields.extend(
                self._generate_variants_from_original(
                    "cover_image_original",
                    self.COVER_VARIANT_SPECS,
                )
            )

        converted_fields = []
        if not self.teaser_image_original:
            converted_fields.extend(
                self._convert_variants_to_webp(self.TEASER_VARIANT_SPECS.keys())
            )
        if not self.cover_image_original:
            converted_fields.extend(
                self._convert_variants_to_webp(self.COVER_VARIANT_SPECS.keys())
            )

        updated_fields = sorted(set(generated_fields + converted_fields))
        if updated_fields:
            super().save(update_fields=build_conversion_update_fields(self, updated_fields))

    def _did_original_change(self, field_name, update_field_set):
        if self.pk and (update_field_set is None or field_name in update_field_set):
            previous_original_name = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list(field_name, flat=True)
                .first()
            )
            return str(previous_original_name or "") != str(
                getattr(getattr(self, field_name), "name", "") or ""
            )

        return bool(getattr(self, field_name))

    def _generate_variants_from_original(self, source_field_name, variant_specs):
        source_image_field = getattr(self, source_field_name)
        source_name = str(source_image_field.name or "")
        generated_fields = []

        for field_name, (max_size, suffix) in variant_specs.items():
            content = build_resized_webp_content(
                source_image_field,
                max_size=max_size,
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

    def _convert_variants_to_webp(self, field_names):
        converted_fields = []
        for field_name in field_names:
            image_field = getattr(self, field_name)
            if convert_image_field_to_webp(image_field, quality=85):
                converted_fields.append(field_name)

        return converted_fields

    def _fallback_image(self, *images):
        for image in images:
            if image:
                return image
        return None

    @property
    def teaser_desktop_image(self):
        return self._fallback_image(
            self.teaser_image_desktop,
            self.teaser_image_tablet,
            self.teaser_image_mobile,
            self.content_item.image_desktop,
            self.content_item.image_tablet,
            self.content_item.image_mobile,
        )

    @property
    def teaser_tablet_image(self):
        return self._fallback_image(
            self.teaser_image_tablet,
            self.teaser_image_desktop,
            self.teaser_image_mobile,
            self.content_item.image_tablet,
            self.content_item.image_desktop,
            self.content_item.image_mobile,
        )

    @property
    def teaser_mobile_image(self):
        return self._fallback_image(
            self.teaser_image_mobile,
            self.teaser_image_tablet,
            self.teaser_image_desktop,
            self.content_item.image_mobile,
            self.content_item.image_tablet,
            self.content_item.image_desktop,
        )

    @property
    def cover_desktop_image(self):
        return self._fallback_image(
            self.cover_image_desktop,
            self.cover_image_tablet,
            self.cover_image_mobile,
            self.teaser_desktop_image,
            self.teaser_tablet_image,
            self.teaser_mobile_image,
        )

    @property
    def cover_tablet_image(self):
        return self._fallback_image(
            self.cover_image_tablet,
            self.cover_image_desktop,
            self.cover_image_mobile,
            self.teaser_tablet_image,
            self.teaser_desktop_image,
            self.teaser_mobile_image,
        )

    @property
    def cover_mobile_image(self):
        return self._fallback_image(
            self.cover_image_mobile,
            self.cover_image_tablet,
            self.cover_image_desktop,
            self.teaser_mobile_image,
            self.teaser_tablet_image,
            self.teaser_desktop_image,
        )

    def __str__(self):
        return self.content_item.title or f"Blog post #{self.pk}"


class Component(WebPImageMixin,models.Model):
    page = models.ForeignKey(Page, related_name='components', on_delete=models.CASCADE)
    component_type = models.ForeignKey(ComponentType, on_delete=models.PROTECT)
    content = models.ForeignKey(Content, null=True, blank=True,  related_name="components", on_delete=models.SET_NULL)

    position = models.PositiveIntegerField(default=0, db_index=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    subtitle = models.CharField(max_length=255, blank=True, null=True)
    button_text = models.CharField(max_length=255, blank=True, null=True)
    
    enabled = models.BooleanField(default=True)
    created_at = models.DateField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)


    def __str__(self):
        return f"{self.component_type.name} - {self.title or 'No Title'}"
