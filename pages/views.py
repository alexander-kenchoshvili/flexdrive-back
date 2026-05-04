from urllib.parse import urlsplit, urlunsplit

from django.db.models import Count, Max, Q
from django.db.models.functions import Lower
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Category, Product, ProductStatus
from common.cache_utils import (
    CACHE_GROUP_PAGES_BLOG_LIST,
    CACHE_GROUP_PAGES_CONTENT,
    CACHE_GROUP_PAGES_FOOTER,
    CACHE_GROUP_PAGES_MENU,
    CACHE_GROUP_PAGES_SITE_SETTINGS,
    cache_api_response,
)
from .models import (
    BlogPost,
    BlogStatus,
    Page,
    Component,
    ContentItem,
    FooterSettings,
    SiteSettings,
)
from .serializers import (
    PageSerializer,
    MenuSerializer,
    SmartComponentSerializer,
    ContentItemSerializer,
    FooterLinkSerializer,
    FooterSettingsSerializer,
    SiteSettingsSerializer,
    SitemapEntrySerializer,
)
from .inner_components import INNER_COMPONENT_MAP


def _to_absolute_url(request, value):
    if not value:
        return None

    # Django FieldFile (ImageField/FileField)
    if hasattr(value, "url"):
        return request.build_absolute_uri(value.url)

    value_str = str(value)
    if value_str.startswith("http://") or value_str.startswith("https://"):
        return value_str
    return request.build_absolute_uri(value_str)


def _normalize_text(value):
    normalized = str(value or "").strip()
    return normalized or None


def _resolve_page_for_seo(page_slug=None, content_item=None):
    if page_slug:
        page = Page.objects.filter(slug=page_slug).first()
        if page:
            return page

    if content_item and content_item.singlePageRoute_id:
        return content_item.singlePageRoute

    return None


def _build_content_item_canonical_path(page_slug, content_item):
    content_type = (getattr(content_item, "content_type", "") or "").strip().strip("/")
    content_slug = (getattr(content_item, "slug", "") or "").strip().strip("/")
    content_id = getattr(content_item, "id", None)
    base_slug = (page_slug or content_type or "").strip().strip("/")

    if not base_slug or not content_slug or not content_id:
        return None

    return f"/{base_slug}/{content_id}-{content_slug}"


def _normalize_sitemap_loc(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    parsed = urlsplit(raw_value)

    if parsed.scheme or parsed.netloc:
        normalized_path = (parsed.path or "/").rstrip("/") or "/"
        return urlunsplit(
            (parsed.scheme, parsed.netloc, normalized_path, parsed.query, "")
        )

    normalized_path = f"/{parsed.path.lstrip('/')}" if parsed.path else "/"
    normalized_path = normalized_path.rstrip("/") or "/"

    if parsed.query:
        return f"{normalized_path}?{parsed.query}"

    return normalized_path


def _build_page_sitemap_loc(page):
    if page.slug == "main":
        return "/"

    if page.url:
        return page.url

    return f"/{page.slug}"


def _build_blog_sitemap_loc(content_item):
    base_slug = (
        (getattr(content_item, "content_type", "") or "").strip().strip("/")
        or (getattr(content_item.singlePageRoute, "slug", "") or "").strip().strip("/")
    )
    content_slug = (getattr(content_item, "slug", "") or "").strip().strip("/")
    content_id = getattr(content_item, "id", None)

    if not base_slug or not content_slug or not content_id:
        return None

    return f"/{base_slug}/{content_id}-{content_slug}"


def _build_page_seo_payload(request, page):
    if not page:
        return {}

    return {
        "title": _normalize_text(page.seo_title) or page.name,
        "description": _normalize_text(page.seo_description),
        "image": _to_absolute_url(request, page.seo_image),
        "noindex": bool(page.seo_noindex),
        "canonical": _normalize_text(page.seo_canonical_url),
    }


def _build_single_view_seo_payload(request, page, content_item, page_slug=None):
    page_payload = _build_page_seo_payload(request, page)

    if not _is_blog_item(content_item):
        return page_payload

    try:
        blog_meta = content_item.blog_post
    except BlogPost.DoesNotExist:
        return page_payload

    canonical_path = _build_content_item_canonical_path(page_slug, content_item)
    return {
        "title": _normalize_text(blog_meta.seo_title)
        or _normalize_text(content_item.title)
        or page_payload.get("title"),
        "description": _normalize_text(blog_meta.seo_description)
        or _normalize_text(blog_meta.excerpt)
        or _normalize_text(content_item.description)
        or page_payload.get("description"),
        "image": _to_absolute_url(request, blog_meta.seo_image)
        or _to_absolute_url(request, blog_meta.cover_image_desktop)
        or _to_absolute_url(request, blog_meta.cover_image_tablet)
        or _to_absolute_url(request, blog_meta.cover_image_mobile)
        or _to_absolute_url(request, blog_meta.teaser_image_desktop)
        or _to_absolute_url(request, blog_meta.teaser_image_tablet)
        or _to_absolute_url(request, blog_meta.teaser_image_mobile)
        or page_payload.get("image"),
        "noindex": bool(blog_meta.seo_noindex or page_payload.get("noindex")),
        "canonical": _normalize_text(blog_meta.seo_canonical_url)
        or canonical_path
        or page_payload.get("canonical"),
    }


def _is_blog_item(content_item):
    return (getattr(content_item.content, "name", "") or "").lower() == "bloglist"


def _serialize_related_blog_posts(request, content_item, limit=3):
    try:
        current_meta = content_item.blog_post
    except BlogPost.DoesNotExist:
        return []

    base_queryset = (
        ContentItem.objects
        .select_related("content", "blog_post")
        .filter(
            content_id=content_item.content_id,
            blog_post__status=BlogStatus.PUBLISHED,
        )
        .exclude(id=content_item.id)
        .order_by("-blog_post__is_featured", "-blog_post__published_at", "-id")
    )

    related_items = []
    if (current_meta.category or "").strip():
        by_category = list(base_queryset.filter(blog_post__category=current_meta.category)[:limit])
        related_items.extend(by_category)
        if len(related_items) < limit:
            remaining = limit - len(related_items)
            excluded_ids = [item.id for item in related_items]
            fallback = list(base_queryset.exclude(id__in=excluded_ids)[:remaining])
            related_items.extend(fallback)
    else:
        related_items = list(base_queryset[:limit])

    return ContentItemSerializer(related_items, many=True, context={"request": request}).data


def _get_blog_list_placement(request):
    placement = (request.query_params.get("placement") or "list").strip().lower()
    if placement not in {"home", "list"}:
        return "list"
    return placement


def _normalize_blog_list_ordering(raw_value, placement):
    allowed_values = {"newest", "oldest", "read_time_asc", "read_time_desc"}
    normalized = (raw_value or "").strip().lower()

    if normalized in allowed_values:
        return normalized

    if placement == "home":
        return "featured"

    return "newest"


def _apply_blog_post_ordering(queryset, ordering):
    if ordering == "featured":
        return queryset.order_by(
            "-blog_post__is_featured",
            "-blog_post__published_at",
            "-id",
        )

    if ordering == "oldest":
        return queryset.order_by(
            "blog_post__published_at",
            "id",
        )

    if ordering == "read_time_asc":
        return queryset.order_by(
            "blog_post__read_time_minutes",
            "-blog_post__published_at",
            "-id",
        )

    if ordering == "read_time_desc":
        return queryset.order_by(
            "-blog_post__read_time_minutes",
            "-blog_post__published_at",
            "-id",
        )

    return queryset.order_by(
        "-blog_post__published_at",
        "-id",
    )



class BlogPostPagination(PageNumberPagination):
    page_size = 9
    page_query_param = "page"

    def get_page_size(self, request):
        placement = _get_blog_list_placement(request)
        if placement == "home":
            return 5
        return 9

    def get_paginated_response(self, data):
        placement = _get_blog_list_placement(self.request)

        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "current_page": self.page.number,
                "total_pages": self.page.paginator.num_pages,
                "page_size": self.get_page_size(self.request),
                "placement": placement,
                "results": data,
            }
        )


class PageDetailAPIView(generics.RetrieveAPIView):
    queryset = Page.objects.prefetch_related('components__component_type')
    serializer_class = PageSerializer
    lookup_field = 'slug'


class MenuListAPIView(generics.ListAPIView):
    queryset = Page.objects.filter(show_in_menu=True).order_by('order')
    serializer_class = MenuSerializer

    @cache_api_response(CACHE_GROUP_PAGES_MENU, "CACHE_TTL_MENU")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class SiteSettingsAPIView(APIView):
    @cache_api_response(CACHE_GROUP_PAGES_SITE_SETTINGS, "CACHE_TTL_SITE_SETTINGS")
    def get(self, request):
        site_settings = SiteSettings.objects.first() or SiteSettings(site_name="FlexDrive")
        serializer = SiteSettingsSerializer(site_settings, context={"request": request})
        return Response(serializer.data)


class SitemapEntriesAPIView(APIView):
    def get(self, request):
        entries = []

        page_queryset = (
            Page.objects.filter(seo_noindex=False, components__enabled=True)
            .annotate(last_component_update=Max("components__updated_at"))
            .distinct()
            .order_by("slug", "id")
        )
        for page in page_queryset:
            loc = _normalize_sitemap_loc(
                page.seo_canonical_url or _build_page_sitemap_loc(page)
            )
            if not loc:
                continue

            entries.append(
                {
                    "loc": loc,
                    "lastmod": page.last_component_update,
                }
            )

        category_queryset = (
            Category.objects.filter(
                is_active=True,
                seo_noindex=False,
                products__status=ProductStatus.PUBLISHED,
            )
            .annotate(last_product_update=Max("products__updated_at"))
            .distinct()
            .order_by("slug", "id")
        )
        for category in category_queryset:
            loc = _normalize_sitemap_loc(
                category.seo_canonical_url or f"/catalog/category/{category.slug}"
            )
            if not loc:
                continue

            entries.append(
                {
                    "loc": loc,
                    "lastmod": category.last_product_update or category.updated_at,
                }
            )

        product_queryset = (
            Product.objects.filter(
                status=ProductStatus.PUBLISHED,
                category__is_active=True,
                seo_noindex=False,
            )
            .select_related("category")
            .order_by("slug", "id")
        )
        for product in product_queryset:
            loc = _normalize_sitemap_loc(
                product.seo_canonical_url or f"/catalog/{product.slug}"
            )
            if not loc:
                continue

            entries.append(
                {
                    "loc": loc,
                    "lastmod": product.updated_at,
                }
            )

        blog_queryset = (
            ContentItem.objects.select_related("content", "blog_post", "singlePageRoute")
            .filter(
                content__name__iexact="bloglist",
                blog_post__status=BlogStatus.PUBLISHED,
            )
            .exclude(blog_post__seo_noindex=True)
            .exclude(singlePageRoute__seo_noindex=True)
            .order_by("blog_post__published_at", "id")
        )
        for content_item in blog_queryset:
            try:
                blog_meta = content_item.blog_post
            except BlogPost.DoesNotExist:
                continue

            loc = _normalize_sitemap_loc(
                blog_meta.seo_canonical_url or _build_blog_sitemap_loc(content_item)
            )
            if not loc:
                continue

            entries.append(
                {
                    "loc": loc,
                    "lastmod": blog_meta.updated_at or blog_meta.published_at or content_item.updated_at,
                }
            )

        serializer = SitemapEntrySerializer({"entries": entries})
        return Response(serializer.data)


class FooterAPIView(APIView):
    @cache_api_response(CACHE_GROUP_PAGES_FOOTER, "CACHE_TTL_FOOTER")
    def get(self, request):
        footer_settings = FooterSettings.objects.get(pk=1)
        settings_payload = FooterSettingsSerializer(footer_settings).data

        def _group_payload(group_name):
            queryset = (
                Page.objects
                .filter(show_in_footer=True, footer_group=group_name)
                .order_by("footer_order", "order", "id")
            )
            return FooterLinkSerializer(queryset, many=True).data

        return Response(
            {
                **settings_payload,
                "groups": {
                    "navigation": _group_payload(Page.FooterGroup.NAVIGATION),
                    "help": _group_payload(Page.FooterGroup.HELP),
                    "legal": _group_payload(Page.FooterGroup.LEGAL),
                },
            }
        )


class BlogPostListAPIView(generics.ListAPIView):
    serializer_class = ContentItemSerializer
    pagination_class = BlogPostPagination

    def _base_queryset(self):
        return (
            ContentItem.objects
            .select_related("content", "blog_post")
            .filter(
                content__name__iexact="bloglist",
                blog_post__status=BlogStatus.PUBLISHED,
            )
        )

    def _apply_search_and_tag_filters(self, queryset):
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(editor__icontains=search)
                | Q(blog_post__excerpt__icontains=search)
                | Q(blog_post__author_name__icontains=search)
                | Q(blog_post__category__icontains=search)
                | Q(blog_post__tags__icontains=search)
            )

        tag = (self.request.query_params.get("tag") or "").strip()
        if tag:
            queryset = queryset.filter(blog_post__tags__icontains=tag)

        return queryset

    def _with_optional_category_filter(self, queryset, include_category=True):
        if not include_category:
            return queryset

        category = (self.request.query_params.get("category") or "").strip()
        if category:
            queryset = queryset.filter(blog_post__category__iexact=category)

        return queryset

    def _filtered_queryset(self, include_category=True):
        queryset = self._base_queryset()
        queryset = self._apply_search_and_tag_filters(queryset)
        queryset = self._with_optional_category_filter(queryset, include_category=include_category)
        return queryset

    def _category_facets(self):
        queryset = (
            self._filtered_queryset(include_category=False)
            .exclude(blog_post__category__isnull=True)
            .exclude(blog_post__category__exact="")
            .values("blog_post__category")
            .annotate(count=Count("id"))
            .order_by(Lower("blog_post__category"))
        )

        return [
            {
                "name": item["blog_post__category"],
                "count": item["count"],
            }
            for item in queryset
        ]

    def get_queryset(self):
        placement = _get_blog_list_placement(self.request)
        ordering = _normalize_blog_list_ordering(
            self.request.query_params.get("ordering"),
            placement,
        )
        queryset = self._filtered_queryset(include_category=True)
        return _apply_blog_post_ordering(queryset, ordering)

    @cache_api_response(CACHE_GROUP_PAGES_BLOG_LIST, "CACHE_TTL_BLOG_LIST")
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        placement = _get_blog_list_placement(request)

        response.data["ordering"] = _normalize_blog_list_ordering(
            request.query_params.get("ordering"),
            placement,
        )
        response.data["filters"] = {
            "category": (request.query_params.get("category") or "").strip() or None,
            "search": (request.query_params.get("search") or "").strip() or None,
            "tag": (request.query_params.get("tag") or "").strip() or None,
        }
        response.data["facets"] = {
            "categories": self._category_facets(),
        }
        return response


class GetCurrentContentAPIView(APIView):
    @cache_api_response(CACHE_GROUP_PAGES_CONTENT, "CACHE_TTL_PAGE_CONTENT", include_body=True)
    def post(self, request):

        single_id = request.data.get("single_id", None)
        single_slug = request.data.get("single_slug", None)
        page_slug = request.data.get("slug", None)

        secondary_data = {}

        if single_id:
            # SINGLE VIEW
            try:
                content_item = ContentItem.objects.select_related("content", "blog_post").get(id=single_id)
            except ContentItem.DoesNotExist:
                return Response(
                    {"error": "ContentItem not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            if _is_blog_item(content_item):
                try:
                    blog_meta = content_item.blog_post
                except BlogPost.DoesNotExist:
                    return Response(
                        {"error": "Blog post metadata not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if blog_meta.status != BlogStatus.PUBLISHED:
                    return Response(
                        {"error": "ContentItem not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            content = content_item.content
            component = (
                Component.objects
                .filter(content=content, enabled=True)
                .select_related("component_type")
                .order_by("position", "id")
                .first()
            )

            if not component:
                return Response(
                    {"error": "Component not found for this ContentItem"},
                    status=status.HTTP_404_NOT_FOUND
                )

            unic_id = f"{component.component_type.name}_{component.id}"

            # Serialize ContentItem
            content_item_serializer = ContentItemSerializer(content_item, context={"request": request})

            # Serialize Component - გამოვიყენებთ conf ნაწილისთვის
            component_serializer = SmartComponentSerializer(component, context={"request": request})
            component_data = component_serializer.data

            conf_data = component_data.get("conf", {})

            content_name = getattr(content_item.content, "name", None)


            if content_name in INNER_COMPONENT_MAP:
                conf_data["componentName"] = INNER_COMPONENT_MAP[content_name]
            else:
                conf_data["componentName"] = component.component_type.name


            # ავაწყოთ იგივე სტრუქტურა, რაც NORMAL PAGE-ზე:
            payload_data = dict(content_item_serializer.data)
            if _is_blog_item(content_item):
                payload_data["related_posts"] = _serialize_related_blog_posts(request, content_item)

            secondary_data[unic_id] = {
                "conf": conf_data,
                "data": payload_data
            }

            seo_page = _resolve_page_for_seo(page_slug=page_slug, content_item=content_item)
            actual_slug = (getattr(content_item, "slug", "") or "").strip().strip("/")
            requested_slug = (single_slug or "").strip().strip("/")
            canonical_path = _build_content_item_canonical_path(page_slug, content_item)
            if requested_slug and requested_slug == actual_slug:
                canonical_path = None

            return Response({
                "secondary": secondary_data,
                "seo": _build_single_view_seo_payload(
                    request,
                    seo_page,
                    content_item,
                    page_slug=page_slug,
                ),
                "canonical_path": canonical_path,
            })


        else:
            # NORMAL PAGE
            if page_slug is None:
                return Response({"error": "slug is required"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                page = Page.objects.get(slug=page_slug)
            except Page.DoesNotExist:
                return Response({"error": "Page not found"}, status=status.HTTP_404_NOT_FOUND)

            components = (
                page.components
                .filter(enabled=True)
                .select_related("component_type", "content")
                .order_by("position", "id")
            )

            for comp in components:
                unic_id = f"{comp.component_type.name}_{comp.id}"
                serializer = SmartComponentSerializer(comp, context={"request": request})
                secondary_data[unic_id] = serializer.data

            return Response({
                "secondary": secondary_data,
                "seo": _build_page_seo_payload(request, page),
                "canonical_path": None,
            })
