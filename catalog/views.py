from decimal import Decimal, InvalidOperation

from django.db.models import Case, Count, F, IntegerField, Max, Min, Prefetch, Q, When
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, cache_api_response
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
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)
from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductSuggestionSerializer,
    VehicleEngineSerializer,
    VehicleMakeSerializer,
    VehicleModelSerializer,
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


def _parse_year(value):
    if value is None or value == "":
        return None

    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        raise ValidationError({"year": "Expected integer year."})

    if parsed < 1900 or parsed > 2100:
        raise ValidationError({"year": "Year must be between 1900 and 2100."})
    return parsed


def _get_by_slug_or_id(queryset, value, field_name):
    if value is None or value == "":
        return None

    normalized = str(value).strip()
    lookup = {"pk": int(normalized)} if normalized.isdigit() else {"slug": normalized}
    instance = queryset.filter(**lookup).first()
    if not instance:
        raise ValidationError({field_name: "Invalid value."})
    return instance


def _required_param(params, field_name):
    value = params.get(field_name)
    if value is None or value == "":
        raise ValidationError({field_name: "This query parameter is required."})
    return value


def _validate_choice(value, choices, field_name):
    if value is None or value == "":
        return None

    normalized = str(value).strip()
    allowed = {choice_value for choice_value, _label in choices}
    if normalized not in allowed:
        raise ValidationError({field_name: f"Invalid value. Allowed: {', '.join(sorted(allowed))}."})
    return normalized


def _matching_fitment_filter(vehicle_filter):
    make = vehicle_filter["make"]
    vehicle_model = vehicle_filter.get("model")
    year = vehicle_filter.get("year")
    engine = vehicle_filter.get("engine")

    base_filter = Q(
        vehicle_model__is_active=True,
        vehicle_model__make__is_active=True,
    )

    if vehicle_model:
        base_filter &= Q(vehicle_model=vehicle_model, vehicle_model__make=make)
    else:
        base_filter &= Q(vehicle_model__make=make)

    if year is not None:
        base_filter &= Q(year_from__lte=year, year_to__gte=year)

    if engine:
        return base_filter & (Q(engine=engine) | Q(engine__isnull=True))

    return base_filter & (Q(engine__isnull=True) | Q(engine__is_active=True))


def _resolve_vehicle_filter(params):
    make_param = params.get("make")
    model_param = params.get("model")
    year_param = params.get("year")
    engine_param = params.get("engine")

    has_vehicle_filter = any([make_param, model_param, year_param, engine_param])
    if not has_vehicle_filter:
        return None

    if not make_param:
        raise ValidationError(
            {"make": "This query parameter is required before vehicle filtering."}
        )

    make = _get_by_slug_or_id(
        VehicleMake.objects.filter(is_active=True),
        make_param,
        "make",
    )

    if not model_param and engine_param:
        raise ValidationError(
            {"model": "This query parameter is required before engine filtering."}
        )

    model = None
    if model_param:
        model = _get_by_slug_or_id(
            VehicleModel.objects.filter(is_active=True, make=make),
            model_param,
            "model",
        )

    if not year_param and engine_param:
        raise ValidationError(
            {"year": "This query parameter is required before engine filtering."}
        )

    year = _parse_year(year_param)

    engine = None
    if engine_param:
        engine = _get_by_slug_or_id(
            VehicleEngine.objects.filter(is_active=True, model=model),
            engine_param,
            "engine",
        )

    return {
        "make": make,
        "model": model,
        "year": year,
        "engine": engine,
    }


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

    vehicle_filter = None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["vehicle_filter"] = self.vehicle_filter
        return context

    def get_queryset(self):
        self.vehicle_filter = None
        queryset = (
            Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category", "brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                )
            )
        )

        params = self.request.query_params
        self.vehicle_filter = _resolve_vehicle_filter(params)

        if self.vehicle_filter:
            fitment_filter = _matching_fitment_filter(self.vehicle_filter)
            matching_fitments = ProductFitment.objects.filter(fitment_filter)
            queryset = (
                queryset.filter(
                    Q(is_universal_fitment=True) | Q(fitments__in=matching_fitments)
                )
                .distinct()
                .prefetch_related(
                    Prefetch(
                        "fitments",
                        queryset=matching_fitments
                        .select_related("vehicle_model__make", "engine")
                        .order_by("year_from", "year_to", "engine__name"),
                        to_attr="matching_fitments",
                    )
                )
            )

        category_param = params.get("category")
        if category_param:
            if str(category_param).isdigit():
                queryset = queryset.filter(category_id=int(category_param))
            else:
                queryset = queryset.filter(category__slug=category_param)

        brand_param = params.get("brand")
        if brand_param:
            brand = _get_by_slug_or_id(
                Brand.objects.filter(is_active=True),
                brand_param,
                "brand",
            )
            queryset = queryset.filter(brand=brand)

        placement = _validate_choice(params.get("placement"), ProductPlacement.choices, "placement")
        if placement:
            queryset = queryset.filter(placement=placement)

        side = _validate_choice(params.get("side"), ProductSide.choices, "side")
        if side:
            queryset = queryset.filter(side=side)

        search_query = params.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(sku__icontains=search_query)
                | Q(manufacturer_part_number__icontains=search_query)
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
            .annotate(count=Count("id", distinct=True))
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

        brand_rows = (
            queryset.exclude(brand__isnull=True)
            .values("brand_id", "brand__name", "brand__slug")
            .annotate(count=Count("id", distinct=True))
            .order_by("brand__name")
        )
        brand_facets = [
            {
                "id": row["brand_id"],
                "name": row["brand__name"],
                "slug": row["brand__slug"],
                "count": row["count"],
            }
            for row in brand_rows
        ]

        placement_labels = dict(ProductPlacement.choices)
        placement_rows = (
            queryset.exclude(placement="")
            .values("placement")
            .annotate(count=Count("id", distinct=True))
            .order_by("placement")
        )
        placement_facets = [
            {
                "value": row["placement"],
                "label": placement_labels.get(row["placement"], row["placement"]),
                "count": row["count"],
            }
            for row in placement_rows
        ]

        side_labels = dict(ProductSide.choices)
        side_rows = (
            queryset.exclude(side="")
            .values("side")
            .annotate(count=Count("id", distinct=True))
            .order_by("side")
        )
        side_facets = [
            {
                "value": row["side"],
                "label": side_labels.get(row["side"], row["side"]),
                "count": row["count"],
            }
            for row in side_rows
        ]

        price_stats = queryset.aggregate(min_price=Min("price"), max_price=Max("price"))
        return {
            "categories": category_facets,
            "brands": brand_facets,
            "placements": placement_facets,
            "sides": side_facets,
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
            .select_related("category", "brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                )
            )
            .filter(
                Q(name__icontains=search_query)
                | Q(sku__icontains=search_query)
                | Q(manufacturer_part_number__icontains=search_query)
            )
            .annotate(
                exact_name_match=Case(
                    When(name__iexact=search_query, then=2),
                    When(manufacturer_part_number__iexact=search_query, then=2),
                    default=0,
                    output_field=IntegerField(),
                ),
                startswith_match=Case(
                    When(name__istartswith=search_query, then=2),
                    When(sku__istartswith=search_query, then=1),
                    When(manufacturer_part_number__istartswith=search_query, then=1),
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
    vehicle_filter = None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["vehicle_filter"] = self.vehicle_filter
        return context

    def get_queryset(self):
        self.vehicle_filter = _resolve_vehicle_filter(self.request.query_params)
        fitment_queryset = (
            ProductFitment.objects.filter(
                vehicle_model__is_active=True,
                vehicle_model__make__is_active=True,
            )
            .filter(Q(engine__isnull=True) | Q(engine__is_active=True))
            .select_related(
                "vehicle_model__make",
                "engine",
            )
        )
        prefetches = [
            Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id")),
            Prefetch("specs", queryset=ProductSpec.objects.order_by("sort_order", "id")),
            Prefetch("fitments", queryset=fitment_queryset),
        ]

        if self.vehicle_filter:
            prefetches.append(
                Prefetch(
                    "fitments",
                    queryset=fitment_queryset.filter(
                        _matching_fitment_filter(self.vehicle_filter)
                    ),
                    to_attr="matching_fitments",
                )
            )

        return (
            Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category", "brand")
            .prefetch_related(*prefetches)
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
            .select_related("category", "brand")
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


class VehicleMakeListAPIView(generics.ListAPIView):
    serializer_class = VehicleMakeSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            VehicleMake.objects.filter(
                is_active=True,
                models__is_active=True,
                models__product_fitments__product__status=ProductStatus.PUBLISHED,
                models__product_fitments__product__category__is_active=True,
            )
            .filter(
                Q(models__product_fitments__engine__isnull=True)
                | Q(models__product_fitments__engine__is_active=True)
            )
            .distinct()
            .order_by("sort_order", "name")
        )


class VehicleModelListAPIView(generics.ListAPIView):
    serializer_class = VehicleModelSerializer
    pagination_class = None

    def get_queryset(self):
        make = _get_by_slug_or_id(
            VehicleMake.objects.filter(is_active=True),
            _required_param(self.request.query_params, "make"),
            "make",
        )
        return (
            VehicleModel.objects.filter(
                make=make,
                is_active=True,
                product_fitments__product__status=ProductStatus.PUBLISHED,
                product_fitments__product__category__is_active=True,
            )
            .filter(
                Q(product_fitments__engine__isnull=True)
                | Q(product_fitments__engine__is_active=True)
            )
            .select_related("make")
            .distinct()
            .order_by("sort_order", "name")
        )


class VehicleYearListAPIView(generics.GenericAPIView):
    pagination_class = None

    def get(self, request, *args, **kwargs):
        make = _get_by_slug_or_id(
            VehicleMake.objects.filter(is_active=True),
            _required_param(request.query_params, "make"),
            "make",
        )
        model_param = request.query_params.get("model")
        model = None
        if model_param:
            model = _get_by_slug_or_id(
                VehicleModel.objects.filter(is_active=True, make=make),
                model_param,
                "model",
            )
        fitments = (
            ProductFitment.objects.filter(
                vehicle_model__is_active=True,
                vehicle_model__make=make,
                product__status=ProductStatus.PUBLISHED,
                product__category__is_active=True,
            )
            .filter(Q(engine__isnull=True) | Q(engine__is_active=True))
        )
        if model:
            fitments = fitments.filter(vehicle_model=model)

        fitment_ranges = fitments.values_list("year_from", "year_to").distinct()

        years = set()
        for year_from, year_to in fitment_ranges:
            years.update(range(year_from, year_to + 1))

        return Response([{"year": year} for year in sorted(years)])


class VehicleEngineListAPIView(generics.ListAPIView):
    serializer_class = VehicleEngineSerializer
    pagination_class = None

    def get_queryset(self):
        make = _get_by_slug_or_id(
            VehicleMake.objects.filter(is_active=True),
            _required_param(self.request.query_params, "make"),
            "make",
        )
        model = _get_by_slug_or_id(
            VehicleModel.objects.filter(is_active=True, make=make),
            _required_param(self.request.query_params, "model"),
            "model",
        )
        year = _parse_year(_required_param(self.request.query_params, "year"))

        return (
            VehicleEngine.objects.filter(
                model=model,
                is_active=True,
                product_fitments__year_from__lte=year,
                product_fitments__year_to__gte=year,
                product_fitments__product__status=ProductStatus.PUBLISHED,
                product_fitments__product__category__is_active=True,
            )
            .distinct()
            .order_by("sort_order", "name")
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
