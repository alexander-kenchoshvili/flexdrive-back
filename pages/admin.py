from django import forms
from django.contrib import admin
from .models import (
    Page,
    ComponentType,
    Component,
    Content,
    ContentItem,
    BlogPost,
    FooterSettings,
    ContactInquiry,
    SiteSettings,
)
from .svg_safety import is_safe_svg_markup

class ComponentInline(admin.TabularInline):
    model = Component
    extra = 1
    fields = ("position", "component_type", "title", "subtitle", "button_text", "content", "enabled")
    ordering = ("position", "id")
    show_change_link = True


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'show_in_menu',
        'show_in_footer',
        'footer_group',
        'order',
        'footer_order',
        'parent',
        'url',
        'seo_noindex',
    )
    list_editable = (
        'show_in_menu',
        'show_in_footer',
        'footer_group',
        'order',
        'footer_order',
        'parent',
        'url',
        'seo_noindex',
    )
    prepopulated_fields = {"slug": ("name",)}
    fields = (
        'name',
        'slug',
        'show_in_menu',
        'show_in_footer',
        'footer_group',
        'footer_order',
        'footer_label',
        'order',
        'parent',
        'url',
        'seo_title',
        'seo_description',
        'seo_image',
        'seo_noindex',
        'seo_canonical_url',
    )
    inlines = [ComponentInline]


@admin.register(ComponentType)
class ComponentTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(FooterSettings)
class FooterSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Brand",
            {
                "fields": (
                    "brand_name",
                    "brand_description",
                    "trust_item_1",
                    "trust_item_2",
                    "trust_item_3",
                )
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "phone",
                    "email",
                    "working_hours",
                    "city",
                )
            },
        ),
        (
            "Socials & Legal",
            {
                "fields": (
                    "instagram_url",
                    "facebook_url",
                    "copyright_text",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        if FooterSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Global SEO",
            {
                "fields": (
                    "site_name",
                    "default_seo_title",
                    "default_seo_description",
                    "default_seo_image",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        if SiteSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "phone",
        "topic_label",
        "status",
        "order_number",
        "created_at",
    )
    list_filter = ("status", "topic_slug", "created_at")
    search_fields = (
        "full_name",
        "email",
        "phone",
        "topic_label",
        "order_number",
        "message",
    )
    ordering = ("-created_at", "-id")
    list_editable = ("status",)
    readonly_fields = (
        "full_name",
        "phone",
        "email",
        "topic_slug",
        "topic_label",
        "order_number",
        "message",
        "created_at",
        "updated_at",
    )
    fields = (
        "status",
        "topic_label",
        "topic_slug",
        "full_name",
        "phone",
        "email",
        "order_number",
        "message",
        "created_at",
        "updated_at",
    )


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ('page', 'position', 'component_type', 'title', 'content', 'enabled')
    list_filter = ('page', 'component_type', 'enabled')
    search_fields = ('title', 'component_type__name', 'content__name', 'page__name')
    ordering = ('page', 'position', 'id')
    list_editable = ('position', 'enabled')


class ContentItemInline(admin.TabularInline):
    model = ContentItem
    extra = 1
    fields = ("title", "content_type", "catalog_category", "position", "singlePageRoute")
    ordering = ("position", "id")
    show_change_link = True

    base_fields = (
        "title",
        "description",
        "content_type",
        "position",
        "singlePageRoute",
    )
    category_fields = (
        "title",
        "content_type",
        "catalog_category",
        "position",
        "singlePageRoute",
    )
    image_fields = (
        "image_desktop",
        "image_tablet",
        "image_mobile",
    )

    def get_fields(self, request, obj=None):
        content_name = (getattr(obj, "name", "") or "").lower()
        if content_name == "value_proposition_cards":
            return self.base_fields + self.image_fields
        return self.category_fields


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [ContentItemInline]


class ContentItemAdminForm(forms.ModelForm):
    def clean_icon_svg(self):
        value = self.cleaned_data.get("icon_svg")
        if value and not is_safe_svg_markup(value):
            raise forms.ValidationError(
                "Unsafe SVG is not allowed. Remove script/event-handler/javascript content."
            )
        return value

    def clean_editor(self):
        value = self.cleaned_data.get("editor")
        if value and not is_safe_svg_markup(value):
            raise forms.ValidationError(
                "Unsafe HTML is not allowed in editor content."
            )
        return value

    class Meta:
        model = ContentItem
        fields = "__all__"
        widgets = {
            "icon_svg": forms.Textarea(
                attrs={"rows": 8, "style": "width: 48rem; font-family: monospace;"}
            ),
        }


class BlogPostInline(admin.StackedInline):
    model = BlogPost
    extra = 0
    can_delete = False
    fields = (
        "excerpt",
        "seo_title",
        "seo_description",
        "seo_image",
        "seo_noindex",
        "seo_canonical_url",
        "read_time_minutes",
        "author_name",
        "author_role",
        "category",
        "tags",
        "teaser_image_original",
        "teaser_image_desktop",
        "teaser_image_tablet",
        "teaser_image_mobile",
        "cover_image_original",
        "cover_image_desktop",
        "cover_image_tablet",
        "cover_image_mobile",
        "status",
        "published_at",
        "is_featured",
    )


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    form = ContentItemAdminForm
    inlines = [BlogPostInline]
    list_display = ("content", "title", "content_type", "catalog_category", "position", "singlePageRoute")
    list_filter = ("content", "content_type", "catalog_category")
    search_fields = ("title", "description", "content_type")
    ordering = ("content", "position", "id")
    list_editable = ("position",)
    base_fields = (
        "content",
        "title",
        "description",
        "content_type",
        "position",
        "icon_svg",
        "catalog_category",
        "singlePageRoute",
        "slug",
        "editor",
    )
    image_fields = (
        "image_desktop",
        "image_tablet",
        "image_mobile",
    )

    def get_inline_instances(self, request, obj=None):
        if obj and obj.content and (obj.content.name or "").lower() == "bloglist":
            return super().get_inline_instances(request, obj)
        return []

    def get_fields(self, request, obj=None):
        if obj and obj.content and (obj.content.name or "").lower() == "bloglist":
            return self.base_fields
        return self.base_fields + self.image_fields


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = (
        "content_item",
        "status",
        "published_at",
        "is_featured",
        "category",
        "read_time_minutes",
    )
    list_filter = ("status", "is_featured", "category")
    search_fields = (
        "content_item__title",
        "excerpt",
        "author_name",
        "category",
        "tags",
    )
    autocomplete_fields = ("content_item",)
    fields = (
        "content_item",
        "excerpt",
        "read_time_minutes",
        "author_name",
        "author_role",
        "category",
        "tags",
        "teaser_image_original",
        "teaser_image_desktop",
        "teaser_image_tablet",
        "teaser_image_mobile",
        "cover_image_original",
        "cover_image_desktop",
        "cover_image_tablet",
        "cover_image_mobile",
        "status",
        "published_at",
        "is_featured",
    )
