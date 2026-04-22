from decimal import Decimal, InvalidOperation

from django.db.models import Case, Count, F, IntegerField, Max, Min, Prefetch, Q, When
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, cache_api_response
from .models import Category, Product, ProductImage, ProductSpec, ProductStatus
from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductSuggestionSerializer,
)


def _parse_bool(value, field_name):
    if value is None:
        return None

    normalized = str(value).strip().lower()
    truthy = {"1", "true", "yes"}
    falsy = {"0", "false", "no"}

    if normalized in truthy:
        return True
    if normalized in falsy:
        return False

    raise ValidationError({field_name: "Expected boolean value (true/false, 1/0)."})


def _parse_decimal(value, field_name):
    if value is None or value == "":
        return None

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError({field_name: "Expected decimal value."})

    if parsed < 0:
        raise ValidationError({field_name: "Value must be greater than or equal to 0."})
    return parsed


class CatalogPagination(PageNumberPagination):
    page_size = 9
    page_size_query_param = "page_size"
    max_page_size = 36

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "current_page": self.page.number,
                "total_pages": self.page.paginator.num_pages,
                "page_size": self.get_page_size(self.request),
                "results": data,
                "facets": getattr(self, "facets", {}),
            }
        )


class ProductListAPIView(generics.ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = CatalogPagination

    ORDERING_MAP = {
        "newest": ("-created_at", "id"),
        "oldest": ("created_at", "id"),
        "price_asc": ("price", "id"),
        "price_desc": ("-price", "id"),
        "name_asc": ("name", "id"),
        "name_desc": ("-name", "id"),
    }

    def get_queryset(self):
        queryset = (
            Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                )
            )
        )

        params = self.request.query_params

        category_param = params.get("category")
        if category_param:
            if str(category_param).isdigit():
                queryset = queryset.filter(category_id=int(category_param))
            else:
                queryset = queryset.filter(category__slug=category_param)

        search_query = params.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(sku__icontains=search_query)
                | Q(short_description__icontains=search_query)
                | Q(description__icontains=search_query)
            )

        min_price = _parse_decimal(params.get("min_price"), "min_price")
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)

        max_price = _parse_decimal(params.get("max_price"), "max_price")
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)

        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValidationError({"max_price": "max_price must be greater than or equal to min_price."})

        is_new = _parse_bool(params.get("is_new"), "is_new")
        if is_new is not None:
            queryset = queryset.filter(is_new=is_new)

        is_featured = _parse_bool(params.get("is_featured"), "is_featured")
        if is_featured is not None:
            queryset = queryset.filter(is_featured=is_featured)

        in_stock = _parse_bool(params.get("in_stock"), "in_stock")
        if in_stock is True:
            queryset = queryset.filter(stock_qty__gt=0)
        elif in_stock is False:
            queryset = queryset.filter(stock_qty=0)

        on_sale = _parse_bool(params.get("on_sale"), "on_sale")
        if on_sale is True:
            queryset = queryset.filter(old_price__gt=F("price"))
        elif on_sale is False:
            queryset = queryset.filter(Q(old_price__isnull=True) | Q(old_price__lte=F("price")))

        ordering_key = params.get("ordering", "newest")
        ordering = self.ORDERING_MAP.get(ordering_key)
        if not ordering:
            raise ValidationError(
                {"ordering": f"Invalid value. Allowed: {', '.join(self.ORDERING_MAP.keys())}."}
            )

        return queryset.order_by(*ordering)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        facets = self._build_facets(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            self.paginator.facets = facets
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({"results": serializer.data, "facets": facets})

    def _build_facets(self, queryset):
        category_rows = (
            queryset.values("category_id", "category__name", "category__slug")
            .annotate(count=Count("id"))
            .order_by("category__name")
        )

        category_facets = [
            {
                "id": row["category_id"],
                "name": row["category__name"],
                "slug": row["category__slug"],
                "count": row["count"],
            }
            for row in category_rows
        ]

        price_stats = queryset.aggregate(min_price=Min("price"), max_price=Max("price"))
        return {
            "categories": category_facets,
            "price": {
                "min": str(price_stats["min_price"]) if price_stats["min_price"] is not None else None,
                "max": str(price_stats["max_price"]) if price_stats["max_price"] is not None else None,
            },
        }


class ProductSuggestionAPIView(generics.ListAPIView):
    serializer_class = ProductSuggestionSerializer
    pagination_class = None
    suggestion_limit = 5

    def get_queryset(self):
        raw_query = self.request.query_params.get("q", "")
        search_query = str(raw_query).strip()

        if len(search_query) < 2:
            return Product.objects.none()

        queryset = (
            Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                )
            )
            .filter(Q(name__icontains=search_query) | Q(sku__icontains=search_query))
            .annotate(
                exact_name_match=Case(
                    When(name__iexact=search_query, then=2),
                    default=0,
                    output_field=IntegerField(),
                ),
                startswith_match=Case(
                    When(name__istartswith=search_query, then=2),
                    When(sku__istartswith=search_query, then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
                in_stock_order=Case(
                    When(stock_qty__gt=0, then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
            )
            .order_by(
                "-exact_name_match",
                "-startswith_match",
                "-is_featured",
                "-in_stock_order",
                "name",
                "id",
            )
        )

        return queryset[: self.suggestion_limit]


class ProductDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category")
            .prefetch_related(
                Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id")),
                Prefetch("specs", queryset=ProductSpec.objects.order_by("sort_order", "id")),
            )
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        context = self.get_serializer_context()
        context["related_products"] = self._get_related_products(instance)
        serializer = self.get_serializer(instance, context=context)
        return Response(serializer.data)

    def _get_related_products(self, product):
        return (
            Product.objects.filter(
                status=ProductStatus.PUBLISHED,
                category__is_active=True,
                category_id=product.category_id,
            )
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                )
            )
            .annotate(
                in_stock_order=Case(
                    When(stock_qty__gt=0, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            )
            .order_by("-is_featured", "-in_stock_order", "-created_at", "-id")[:4]
        )


class CategoryListAPIView(generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Category.objects.filter(is_active=True)
            .annotate(
                product_count=Count(
                    "products",
                    filter=Q(products__status=ProductStatus.PUBLISHED),
                )
            )
            .filter(product_count__gt=0)
            .order_by("sort_order", "name")
        )

    @cache_api_response(CACHE_GROUP_CATALOG_CATEGORIES, "CACHE_TTL_CATALOG_CATEGORIES")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
