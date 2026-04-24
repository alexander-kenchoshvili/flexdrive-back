from rest_framework import serializers

from .models import (
    BlogPost,
    BlogStatus,
    Component,
    ComponentType,
    Content,
    ContentItem,
    FooterSettings,
    Page,
    SiteSettings,
)
from .svg_safety import is_safe_svg_markup


class ComponentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComponentType
        fields = ["id", "name"]


class BlogPostMetaSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    teaser_image = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            "excerpt",
            "read_time_minutes",
            "author_name",
            "author_role",
            "category",
            "tags",
            "status",
            "published_at",
            "is_featured",
            "teaser_image",
            "cover_image",
        ]

    def get_tags(self, obj):
        return [tag.strip() for tag in (obj.tags or "").split(",") if tag.strip()]

    def _build_image_payload(self, desktop_image, tablet_image, mobile_image):
        request = self.context.get("request")

        def _absolute_url(value):
            if not value:
                return None
            if request is None:
                return value.url
            return request.build_absolute_uri(value.url)

        return {
            "desktop": _absolute_url(desktop_image),
            "tablet": _absolute_url(tablet_image),
            "mobile": _absolute_url(mobile_image),
        }

    def get_teaser_image(self, obj):
        return self._build_image_payload(
            obj.teaser_desktop_image,
            obj.teaser_tablet_image,
            obj.teaser_mobile_image,
        )

    def get_cover_image(self, obj):
        return self._build_image_payload(
            obj.cover_desktop_image,
            obj.cover_tablet_image,
            obj.cover_mobile_image,
        )


class ContentItemSerializer(serializers.ModelSerializer):
    singlePageRoute = serializers.IntegerField(source="singlePageRoute_id", allow_null=True)
    image = serializers.SerializerMethodField()
    blog_meta = serializers.SerializerMethodField()
    catalog_category = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = [
            "id",
            "title",
            "description",
            "image",
            "slug",
            "singlePageRoute",
            "content_type",
            "position",
            "icon_svg",
            "catalog_category",
            "editor",
            "created_at",
            "blog_meta",
        ]

    def get_image(self, obj):
        request = self.context.get("request")

        try:
            blog_post = obj.blog_post
        except BlogPost.DoesNotExist:
            blog_post = None

        desktop_image = blog_post.teaser_desktop_image if blog_post else obj.image_desktop
        tablet_image = blog_post.teaser_tablet_image if blog_post else obj.image_tablet
        mobile_image = blog_post.teaser_mobile_image if blog_post else obj.image_mobile

        return {
            "desktop": request.build_absolute_uri(desktop_image.url) if request and desktop_image else (desktop_image.url if desktop_image else None),
            "tablet": request.build_absolute_uri(tablet_image.url) if request and tablet_image else (tablet_image.url if tablet_image else None),
            "mobile": request.build_absolute_uri(mobile_image.url) if request and mobile_image else (mobile_image.url if mobile_image else None),
        }

    def get_blog_meta(self, obj):
        try:
            blog_post = obj.blog_post
        except BlogPost.DoesNotExist:
            return None
        return BlogPostMetaSerializer(blog_post, context=self.context).data

    def get_catalog_category(self, obj):
        category = obj.catalog_category
        if not category:
            return None

        return {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
        }

    def validate_icon_svg(self, value):
        if value and not is_safe_svg_markup(value):
            raise serializers.ValidationError(
                "Unsafe SVG is not allowed. Remove script/event-handler/javascript content."
            )
        return value

    def validate_editor(self, value):
        if value and not is_safe_svg_markup(value):
            raise serializers.ValidationError(
                "Unsafe HTML is not allowed in editor content."
            )
        return value


class ContentSerializer(serializers.ModelSerializer):
    listcount = serializers.SerializerMethodField()
    list = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = ["id", "name", "listcount", "list"]

    def get_listcount(self, obj):
        queryset = obj.items.all()
        if (obj.name or "").lower() == "bloglist":
            queryset = queryset.filter(blog_post__status=BlogStatus.PUBLISHED)
        return queryset.count()

    def get_list(self, obj):
        items = obj.items.select_related("blog_post", "catalog_category")
        if (obj.name or "").lower() == "bloglist":
            items = items.filter(blog_post__status=BlogStatus.PUBLISHED).order_by(
                "-blog_post__is_featured",
                "-blog_post__published_at",
                "position",
                "id",
            )
        else:
            items = items.order_by("position", "id")
        return ContentItemSerializer(items, many=True, context=self.context).data


class ComponentSerializer(serializers.ModelSerializer):
    component_type = ComponentTypeSerializer()
    contentData = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Component
        fields = [
            "id",
            "component_type",
            "title",
            "subtitle",
            "button_text",
            "image",
            "contentData",
            "enabled",
        ]

    def get_contentData(self, obj):
        if obj.content:
            return ContentSerializer(obj.content, context=self.context).data
        return None

    def get_image(self, obj):
        request = self.context["request"]
        return {
            "desktop": request.build_absolute_uri(obj.image_desktop.url) if obj.image_desktop else None,
            "tablet": request.build_absolute_uri(obj.image_tablet.url) if obj.image_tablet else None,
            "mobile": request.build_absolute_uri(obj.image_mobile.url) if obj.image_mobile else None,
        }


class PageSerializer(serializers.ModelSerializer):
    components = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "id",
            "name",
            "slug",
            "seo_title",
            "seo_description",
            "seo_image",
            "seo_noindex",
            "seo_canonical_url",
            "components",
        ]

    def get_components(self, obj):
        components = (
            obj.components
            .filter(enabled=True)
            .select_related("component_type", "content")
            .order_by("position", "id")
        )
        return ComponentSerializer(components, many=True, context=self.context).data


class MenuSerializer(serializers.ModelSerializer):
    final_url = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "id",
            "name",
            "slug",
            "url",
            "final_url",
            "parent",
            "order",
            "show_in_menu",
        ]

    def get_final_url(self, obj):
        if obj.slug == "main":
            return "/"
        return obj.url if obj.url else f"/{obj.slug}/"


class FooterLinkSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "id",
            "label",
            "slug",
            "url",
            "footer_order",
        ]

    def get_label(self, obj):
        return obj.footer_label or obj.name

    def get_url(self, obj):
        if obj.slug == "main":
            return "/"
        return obj.url if obj.url else f"/{obj.slug}/"


class FooterSettingsSerializer(serializers.ModelSerializer):
    brand = serializers.SerializerMethodField()
    trust_items = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()
    socials = serializers.SerializerMethodField()

    class Meta:
        model = FooterSettings
        fields = [
            "brand",
            "trust_items",
            "contact",
            "socials",
            "copyright_text",
        ]

    def get_brand(self, obj):
        return {
            "name": obj.brand_name or "FlexDrive",
            "description": obj.brand_description or "",
        }

    def get_trust_items(self, obj):
        return [
            item.strip()
            for item in [obj.trust_item_1, obj.trust_item_2, obj.trust_item_3]
            if item and item.strip()
        ]

    def get_contact(self, obj):
        return {
            "phone": obj.phone,
            "email": obj.email,
            "working_hours": obj.working_hours,
            "city": obj.city,
        }

    def get_socials(self, obj):
        items = []

        if obj.email:
            items.append(
                {
                    "type": "email",
                    "label": obj.email,
                    "url": f"mailto:{obj.email}",
                }
            )
        if obj.instagram_url:
            items.append(
                {
                    "type": "instagram",
                    "label": "Instagram",
                    "url": obj.instagram_url,
                }
            )
        if obj.facebook_url:
            items.append(
                {
                    "type": "facebook",
                    "label": "Facebook",
                    "url": obj.facebook_url,
                }
            )

        return items


class SiteSettingsSerializer(serializers.ModelSerializer):
    default_seo_image = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = [
            "site_name",
            "default_seo_title",
            "default_seo_description",
            "default_seo_image",
        ]

    def get_default_seo_image(self, obj):
        request = self.context.get("request")
        if not obj.default_seo_image:
            return None
        if request:
            return request.build_absolute_uri(obj.default_seo_image.url)
        return obj.default_seo_image.url


class SitemapEntryItemSerializer(serializers.Serializer):
    loc = serializers.CharField()
    lastmod = serializers.DateTimeField(allow_null=True)


class SitemapEntrySerializer(serializers.Serializer):
    entries = SitemapEntryItemSerializer(many=True)


class SmartComponentSerializer(serializers.ModelSerializer):
    conf = serializers.SerializerMethodField()
    data = serializers.SerializerMethodField()

    class Meta:
        model = Component
        fields = ["conf", "data"]

    def get_conf(self, obj):
        return {
            "unicId": f"ui{obj.id}",
            "enabled": "1" if obj.enabled else "0",
            "componentName": obj.component_type.name,
            "useHeader": "1",
            "listLayout": "1",
            "singleLayout": "1",
        }

    def get_data(self, obj):
        content_data = None
        if obj.content:
            content_data = ContentSerializer(obj.content, context=self.context).data

        request = self.context["request"]
        return {
            "title": obj.title,
            "subtitle": obj.subtitle,
            "buttonText": obj.button_text,
            "image": {
                "desktop": request.build_absolute_uri(obj.image_desktop.url) if obj.image_desktop else None,
                "tablet": request.build_absolute_uri(obj.image_tablet.url) if obj.image_tablet else None,
                "mobile": request.build_absolute_uri(obj.image_mobile.url) if obj.image_mobile else None,
            },
            "contentData": content_data,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
