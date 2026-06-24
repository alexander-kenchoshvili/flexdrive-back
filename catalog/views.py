from decimal import Decimal, InvalidOperation

from django.db.models import Case, Count, F, IntegerField, Max, Min, Prefetch, Q, When
from django.db.models.functions import Length
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, cache_api_response
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
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)
from .serializers import (
    CategorySerializer,
    PLACEMENT_LABELS_KA,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductSuggestionSerializer,
    SIDE_LABELS_KA,
    VehicleEngineSerializer,
    VehicleMakeSerializer,
    VehicleModelSerializer,
)
from .search_cache import get_vehicle_search_catalog


SEARCH_QUERY_MIN_LENGTH = 2
SEARCH_QUERY_MAX_LENGTH = 100


def _validated_search_query(raw_query):
    search_query = str(raw_query or "").strip()
    if not search_query:
        return ""
    if len(search_query) < SEARCH_QUERY_MIN_LENGTH:
        raise ValidationError(
            {"q": f"Search query must contain at least {SEARCH_QUERY_MIN_LENGTH} characters."}
        )
    if len(search_query) > SEARCH_QUERY_MAX_LENGTH:
        raise ValidationError(
            {"q": f"Search query must contain at most {SEARCH_QUERY_MAX_LENGTH} characters."}
        )
    return search_query


_LATIN_GEORGIAN_DIGRAPHS = {
    "ch": ("ჩ",),
    "dz": ("ძ",),
    "gh": ("ღ",),
    "kh": ("ხ",),
    "sh": ("შ",),
    "ts": ("ც",),
    "zh": ("ჟ",),
}

_LATIN_GEORGIAN_CHARS = {
    "a": ("ა",),
    "b": ("ბ",),
    "c": ("ც",),
    "d": ("დ",),
    "e": ("ე",),
    "f": ("ფ",),
    "g": ("გ",),
    "h": ("ჰ",),
    "i": ("ი",),
    "j": ("ჯ",),
    "k": ("კ", "ქ"),
    "l": ("ლ",),
    "m": ("მ",),
    "n": ("ნ",),
    "o": ("ო",),
    "p": ("პ",),
    "q": ("ქ",),
    "r": ("რ",),
    "s": ("ს",),
    "t": ("ტ", "თ"),
    "u": ("უ",),
    "v": ("ვ",),
    "w": ("წ", "ჭ"),
    "x": ("ხ",),
    "y": ("ყ",),
    "z": ("ზ",),
}

_GEORGIAN_LATIN_CHARS = {
    "ა": "a",
    "ბ": "b",
    "გ": "g",
    "დ": "d",
    "ე": "e",
    "ვ": "v",
    "ზ": "z",
    "თ": "t",
    "ი": "i",
    "კ": "k",
    "ლ": "l",
    "მ": "m",
    "ნ": "n",
    "ო": "o",
    "პ": "p",
    "ჟ": "zh",
    "რ": "r",
    "ს": "s",
    "ტ": "t",
    "უ": "u",
    "ფ": "f",
    "ქ": "q",
    "ღ": "gh",
    "ყ": "y",
    "შ": "sh",
    "ჩ": "ch",
    "ც": "ts",
    "ძ": "dz",
    "წ": "w",
    "ჭ": "w",
    "ხ": "kh",
    "ჯ": "j",
    "ჰ": "h",
}

_SEARCH_TERM_VARIANT_LIMIT = 8
_VEHICLE_SEARCH_MAX_TOKENS = 4
_VEHICLE_PREFIX_MIN_LENGTH = 3

_SEARCH_TOKEN_STRIP_CHARS = " \t\r\n.,;:()[]{}\"'“”„"

_SIDE_SEARCH_TERMS = {
    ProductSide.LEFT: ("მარცხენა", "left", "lh"),
    ProductSide.RIGHT: ("მარჯვენა", "right", "rh"),
    ProductSide.BOTH: ("ორივე", "both"),
    ProductSide.CENTER: ("ცენტრი", "center", "middle"),
}

_PLACEMENT_SEARCH_TERMS = {
    ProductPlacement.FRONT: ("წინა", "front"),
    ProductPlacement.REAR: ("უკანა", "rear", "back"),
    ProductPlacement.UPPER: ("ზედა", "upper", "top"),
    ProductPlacement.LOWER: ("ქვედა", "lower", "bottom"),
    ProductPlacement.INNER: ("შიდა", "inner", "inside"),
    ProductPlacement.OUTER: ("გარე", "outer", "outside"),
}

_SEARCH_WORD_BOUNDARIES = (" ", "(", "-", "/")

_VEHICLE_MAKE_ALIASES = {
    "audi": ("აუდი", "audi"),
    "bmw": ("ბმვ", "bmw"),
    "ford": ("ფორდი", "ფორდ", "ford"),
    "honda": ("ჰონდა", "honda"),
    "lexus": ("ლექსუსი", "ლექსუს", "leksusi", "leksus", "lexus"),
    "mazda": ("მაზდა", "mazda"),
    "mercedes": ("მერსედესი", "მერსედეს", "mersedesi", "mersedes", "mercedes"),
    "mitsubishi": ("მიცუბიში", "mitsubishi"),
    "subaru": ("სუბარუ", "subaru"),
    "tesla": ("ტესლა", "tesla"),
    "toyota": ("ტოიოტა", "toiota", "toyota"),
    "volkswagen": (
        "ფოლკსვაგენი",
        "ფოლკსვაგენ",
        "polksvageni",
        "polksvagen",
        "volkswagen",
    ),
}


def _latin_to_georgian_variants(value):
    normalized = str(value).strip()
    if not normalized:
        return []

    tokens = []
    index = 0
    while index < len(normalized):
        pair = normalized[index : index + 2].lower()
        if pair in _LATIN_GEORGIAN_DIGRAPHS:
            tokens.append(_LATIN_GEORGIAN_DIGRAPHS[pair])
            index += 2
            continue

        char = normalized[index]
        tokens.append(_LATIN_GEORGIAN_CHARS.get(char.lower(), (char,)))
        index += 1

    variants = [""]
    for options in tokens:
        next_variants = []
        for prefix in variants:
            for option in options:
                candidate = f"{prefix}{option}"
                if candidate not in next_variants:
                    next_variants.append(candidate)
                if len(next_variants) >= _SEARCH_TERM_VARIANT_LIMIT:
                    break
            if len(next_variants) >= _SEARCH_TERM_VARIANT_LIMIT:
                break
        variants = next_variants

    return variants


def _georgian_to_latin(value):
    normalized = str(value).strip()
    if not normalized:
        return ""

    return "".join(_GEORGIAN_LATIN_CHARS.get(char, char) for char in normalized)


def _search_terms(value):
    search_query = str(value or "").strip()
    if not search_query:
        return []

    base_terms = [search_query]
    normalized_lower = search_query.lower()
    if len(search_query) > 4 and search_query.endswith("ის"):
        base_terms.append(search_query[:-2])
    if len(search_query) > 4 and normalized_lower.endswith("is"):
        base_terms.append(search_query[:-2])
    if len(search_query) > 3 and search_query.endswith("ს"):
        base_terms.append(search_query[:-1])
    if len(search_query) > 3 and normalized_lower.endswith("s"):
        base_terms.append(search_query[:-1])

    terms = []
    for base_term in base_terms:
        if base_term not in terms:
            terms.append(base_term)

        latin_variant = _georgian_to_latin(base_term)
        if latin_variant and latin_variant != base_term and latin_variant not in terms:
            terms.append(latin_variant)

        for variant in _latin_to_georgian_variants(base_term):
            if variant != base_term and variant not in terms:
                terms.append(variant)
    return terms


def _search_tokens(value):
    return [token for token in str(value or "").strip().split() if token]


def _normalize_search_token(value):
    return str(value or "").strip(_SEARCH_TOKEN_STRIP_CHARS).lower()


def _expanded_search_terms(raw_terms):
    terms = set()
    for raw_term in raw_terms:
        terms.add(_normalize_search_token(raw_term))
        for variant in _search_terms(raw_term):
            normalized = _normalize_search_token(variant)
            if normalized:
                terms.add(normalized)
    return terms


_VEHICLE_MAKE_ALIAS_LOOKUP = {
    term: slug
    for slug, raw_terms in _VEHICLE_MAKE_ALIASES.items()
    for term in _expanded_search_terms((*raw_terms, slug))
}


def _vehicle_search_terms(value):
    search_terms = _search_terms(value)
    terms = _unique_search_terms(search_terms)
    for term in search_terms:
        alias = _VEHICLE_MAKE_ALIAS_LOOKUP.get(_normalize_search_token(term))
        if alias and alias not in terms:
            terms.append(alias)
    return terms


def _product_search_filter(search_terms, include_descriptions=False):
    query = Q()
    for term in search_terms:
        term_query = (
            Q(name__icontains=term)
            | Q(sku__icontains=term)
            | Q(manufacturer_part_number__icontains=term)
        )
        if include_descriptions:
            term_query |= Q(short_description__icontains=term) | Q(description__icontains=term)
        query |= term_query
    return query


def _unique_search_terms(values):
    terms = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in terms:
            terms.append(normalized)
    return terms


def _build_search_context(raw_query):
    search_query = str(raw_query or "").strip()
    if not search_query:
        return None

    search_parts = _resolve_search_parts(search_query)
    product_query = (
        search_parts["product_query"]
        if search_parts and search_parts["product_query"]
        else search_query
    )
    phrase_terms = _unique_search_terms(_search_terms(product_query))
    token_terms = _unique_search_terms(
        term
        for token in _search_tokens(product_query)
        for term in _search_terms(token)
    )
    return {
        "raw_query": search_query,
        "search_parts": search_parts,
        "phrase_terms": phrase_terms,
        "token_terms": token_terms,
    }


def _name_boundary_whens(search_terms, score):
    whens = []
    for term in search_terms:
        whens.append(When(name__iexact=term, then=score))
        for boundary in _SEARCH_WORD_BOUNDARIES:
            whens.extend(
                [
                    When(name__istartswith=f"{term}{boundary}", then=score),
                    When(name__iendswith=f"{boundary}{term}", then=score),
                ]
            )
            for trailing_boundary in _SEARCH_WORD_BOUNDARIES:
                whens.append(
                    When(
                        name__icontains=f"{boundary}{term}{trailing_boundary}",
                        then=score,
                    )
                )
    return whens


def _in_stock_order_annotation():
    return Case(
        When(stock_qty__gt=CUSTOMER_STOCK_RESERVE_QTY, then=1),
        default=0,
        output_field=IntegerField(),
    )


def _search_relevance_annotations(search_context):
    phrase_terms = search_context["phrase_terms"]
    token_terms = search_context["token_terms"]
    relevance_terms = _unique_search_terms([*phrase_terms, *token_terms])

    identifier_match_whens = []
    startswith_match_whens = []
    contains_match_whens = []
    for term in relevance_terms:
        identifier_match_whens.extend(
            [
                When(sku__iexact=term, then=3),
                When(manufacturer_part_number__iexact=term, then=3),
            ]
        )
        startswith_match_whens.extend(
            [
                When(name__istartswith=term, then=2),
                When(sku__istartswith=term, then=1),
                When(manufacturer_part_number__istartswith=term, then=1),
            ]
        )
        contains_match_whens.append(When(name__icontains=term, then=1))

    return {
        "search_identifier_match": Case(
            *identifier_match_whens,
            default=0,
            output_field=IntegerField(),
        ),
        "search_direct_name_match": Case(
            *_name_boundary_whens(phrase_terms, 8),
            *_name_boundary_whens(token_terms, 6),
            default=0,
            output_field=IntegerField(),
        ),
        "search_startswith_match": Case(
            *startswith_match_whens,
            default=0,
            output_field=IntegerField(),
        ),
        "search_contains_match": Case(
            *contains_match_whens,
            default=0,
            output_field=IntegerField(),
        ),
        "in_stock_order": _in_stock_order_annotation(),
        "search_name_length": Length("name"),
    }


_SIDE_SEARCH_TERM_LOOKUP = {
    term: value
    for value, raw_terms in _SIDE_SEARCH_TERMS.items()
    for term in _expanded_search_terms(raw_terms)
}
_PLACEMENT_SEARCH_TERM_LOOKUP = {
    term: value
    for value, raw_terms in _PLACEMENT_SEARCH_TERMS.items()
    for term in _expanded_search_terms(raw_terms)
}


def _attribute_search_match(value):
    normalized_terms = {
        _normalize_search_token(term)
        for term in _search_terms(value)
        if _normalize_search_token(term)
    }
    if not normalized_terms:
        return None

    for term in normalized_terms:
        side = _SIDE_SEARCH_TERM_LOOKUP.get(term)
        if side:
            return {"field": "side", "value": side}

    for term in normalized_terms:
        placement = _PLACEMENT_SEARCH_TERM_LOOKUP.get(term)
        if placement:
            return {"field": "placement", "value": placement}

    return None


def _attribute_constraint(field, value, token, include_descriptions=False):
    query = Q(**{field: value})
    token_terms = _search_terms(token)
    if token_terms:
        query |= _product_search_filter(
            token_terms,
            include_descriptions=include_descriptions,
        )
    return query


def _first_vehicle_entity_match(records, search_terms):
    normalized_terms = {
        _normalize_search_token(term)
        for term in search_terms
        if _normalize_search_token(term)
    }
    for record in records:
        if (
            _normalize_search_token(record["name"]) in normalized_terms
            or _normalize_search_token(record["slug"]) in normalized_terms
        ):
            return record

    prefix_terms = tuple(
        _normalize_search_token(term)
        for term in search_terms
        if len(_normalize_search_token(term)) >= _VEHICLE_PREFIX_MIN_LENGTH
    )
    if not prefix_terms:
        return None

    for record in records:
        name = _normalize_search_token(record["name"])
        slug = _normalize_search_token(record["slug"])
        if any(name.startswith(term) or slug.startswith(term) for term in prefix_terms):
            return record
    return None


def _vehicle_search_match(value, vehicle_catalog):
    search_terms = _vehicle_search_terms(value)
    if not search_terms:
        return None

    make = _first_vehicle_entity_match(vehicle_catalog["makes"], search_terms)
    if make:
        return {
            "make_id": make["id"],
            "model_id": None,
            "engine_id": None,
        }

    model = _first_vehicle_entity_match(vehicle_catalog["models"], search_terms)
    if model:
        return {
            "make_id": model["make_id"],
            "model_id": model["id"],
            "engine_id": None,
        }

    engine = _first_vehicle_entity_match(vehicle_catalog["engines"], search_terms)
    if engine:
        return {
            "make_id": engine["model__make_id"],
            "model_id": engine["model_id"],
            "engine_id": engine["id"],
        }

    return None


def _merge_vehicle_search_match(current, match):
    if current is None:
        return match

    if current["make_id"] != match["make_id"]:
        return None

    merged = {
        "make_id": current["make_id"],
        "model_id": current.get("model_id"),
        "engine_id": current.get("engine_id"),
    }

    if match.get("model_id"):
        if merged["model_id"] and merged["model_id"] != match["model_id"]:
            return None
        merged["model_id"] = match["model_id"]

    if match.get("engine_id"):
        if merged["engine_id"] and merged["engine_id"] != match["engine_id"]:
            return None
        merged["engine_id"] = match["engine_id"]
        merged["model_id"] = match["model_id"]

    return merged


def _resolve_search_parts(raw_query):
    tokens = _search_tokens(raw_query)
    if not tokens:
        return None

    vehicle_catalog = get_vehicle_search_catalog()
    vehicle_filter = None
    attribute_filters = {}
    product_tokens = []
    index = 0

    while index < len(tokens):
        matched_vehicle = False
        max_size = min(_VEHICLE_SEARCH_MAX_TOKENS, len(tokens) - index)

        for size in range(max_size, 0, -1):
            phrase = " ".join(tokens[index : index + size])
            match = _vehicle_search_match(phrase, vehicle_catalog)
            if not match:
                continue

            merged = _merge_vehicle_search_match(vehicle_filter, match)
            if not merged:
                continue

            vehicle_filter = merged
            index += size
            matched_vehicle = True
            break

        if matched_vehicle:
            continue

        attribute_match = _attribute_search_match(tokens[index])
        if attribute_match:
            field = attribute_match["field"]
            value = attribute_match["value"]
            existing = attribute_filters.get(field)

            if not existing or existing["value"] == value:
                attribute_filters[field] = {"value": value, "token": tokens[index]}
                index += 1
                continue

        product_tokens.append(tokens[index])
        index += 1

    if vehicle_filter is None and not attribute_filters:
        return None

    return {
        "vehicle_filter": vehicle_filter,
        "attribute_filters": attribute_filters,
        "product_query": " ".join(product_tokens).strip(),
    }


def _apply_catalog_search(queryset, search_context, include_descriptions=False):
    if not search_context:
        return queryset

    search_query = search_context["raw_query"]
    search_parts = search_context["search_parts"]
    if search_parts:
        vehicle_filter = search_parts["vehicle_filter"]
        if vehicle_filter:
            fitment_filter = _matching_fitment_filter(vehicle_filter)
            matching_fitments = ProductFitment.objects.filter(fitment_filter)
            queryset = queryset.filter(
                Q(is_universal_fitment=True) | Q(fitments__in=matching_fitments)
            ).distinct()

        for field, match in search_parts["attribute_filters"].items():
            queryset = queryset.filter(
                _attribute_constraint(
                    field,
                    match["value"],
                    match["token"],
                    include_descriptions=include_descriptions,
                )
            )

        product_query = search_parts["product_query"]
        if product_query:
            queryset = queryset.filter(
                _product_search_filter(
                    _search_terms(product_query),
                    include_descriptions=include_descriptions,
                )
            )
        return queryset

    search_terms = _search_terms(search_query)
    if search_terms:
        return queryset.filter(
            _product_search_filter(search_terms, include_descriptions=include_descriptions)
        )

    return queryset


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
    make_id = vehicle_filter.get("make_id")
    if make_id is None:
        make_id = vehicle_filter["make"].pk

    vehicle_model_id = vehicle_filter.get("model_id")
    if vehicle_model_id is None and vehicle_filter.get("model"):
        vehicle_model_id = vehicle_filter["model"].pk

    year = vehicle_filter.get("year")
    engine_id = vehicle_filter.get("engine_id")
    if engine_id is None and vehicle_filter.get("engine"):
        engine_id = vehicle_filter["engine"].pk

    base_filter = Q(
        vehicle_model__is_active=True,
        vehicle_model__make__is_active=True,
    )

    if vehicle_model_id:
        base_filter &= Q(
            vehicle_model_id=vehicle_model_id,
            vehicle_model__make_id=make_id,
        )
    else:
        base_filter &= Q(vehicle_model__make_id=make_id)

    if year is not None:
        base_filter &= Q(year_from__lte=year, year_to__gte=year)

    if engine_id:
        return base_filter & (Q(engine_id=engine_id) | Q(engine__isnull=True))

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

    def get_throttles(self):
        self.throttle_scope = (
            "catalog_search"
            if str(self.request.query_params.get("q", "")).strip()
            else None
        )
        return super().get_throttles()

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

        search_context = _build_search_context(_validated_search_query(params.get("q")))
        queryset = _apply_catalog_search(
            queryset,
            search_context,
            include_descriptions=True,
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
            queryset = queryset.filter(stock_qty__gt=CUSTOMER_STOCK_RESERVE_QTY)
        elif in_stock is False:
            queryset = queryset.filter(stock_qty__lte=CUSTOMER_STOCK_RESERVE_QTY)

        on_sale = _parse_bool(params.get("on_sale"), "on_sale")
        if on_sale is True:
            queryset = queryset.filter(old_price__gt=F("price"))
        elif on_sale is False:
            queryset = queryset.filter(Q(old_price__isnull=True) | Q(old_price__lte=F("price")))

        ordering_param = params.get("ordering")
        if search_context and not ordering_param:
            return queryset.annotate(
                **_search_relevance_annotations(search_context),
            ).order_by(
                "-in_stock_order",
                "-search_identifier_match",
                "-search_direct_name_match",
                "-search_startswith_match",
                "-search_contains_match",
                "-is_featured",
                "search_name_length",
                "name",
                "id",
            )

        ordering_key = ordering_param or "newest"
        ordering = self.ORDERING_MAP.get(ordering_key)
        if not ordering:
            raise ValidationError(
                {"ordering": f"Invalid value. Allowed: {', '.join(self.ORDERING_MAP.keys())}."}
            )

        return queryset.annotate(
            in_stock_order=_in_stock_order_annotation(),
        ).order_by("-in_stock_order", *ordering)

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

        placement_rows = (
            queryset.exclude(placement="")
            .values("placement")
            .annotate(count=Count("id", distinct=True))
            .order_by("placement")
        )
        placement_facets = [
            {
                "value": row["placement"],
                "label": PLACEMENT_LABELS_KA.get(row["placement"], row["placement"]),
                "count": row["count"],
            }
            for row in placement_rows
        ]

        side_rows = (
            queryset.exclude(side="")
            .values("side")
            .annotate(count=Count("id", distinct=True))
            .order_by("side")
        )
        side_facets = [
            {
                "value": row["side"],
                "label": SIDE_LABELS_KA.get(row["side"], row["side"]),
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
    throttle_scope = "catalog_search"
    suggestion_limit = 5

    def get_queryset(self):
        raw_query = self.request.query_params.get("q")
        if not str(raw_query or "").strip():
            return Product.objects.none()
        search_query = _validated_search_query(raw_query)

        queryset = (
            Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
            .select_related("category", "brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "id"),
                ),
                Prefetch(
                    "fitments",
                    queryset=ProductFitment.objects.select_related(
                        "vehicle_model__make",
                        "engine",
                    ).order_by(
                        "vehicle_model__make__sort_order",
                        "vehicle_model__make__name",
                        "vehicle_model__sort_order",
                        "vehicle_model__name",
                        "year_from",
                        "year_to",
                        "engine__name",
                    ),
                ),
            )
        )
        search_context = _build_search_context(search_query)
        queryset = (
            _apply_catalog_search(queryset, search_context)
            .annotate(
                **_search_relevance_annotations(search_context),
            )
            .order_by(
                "-in_stock_order",
                "-search_identifier_match",
                "-search_direct_name_match",
                "-search_startswith_match",
                "-search_contains_match",
                "-is_featured",
                "search_name_length",
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
                in_stock_order=_in_stock_order_annotation()
            )
            .order_by("-in_stock_order", "-is_featured", "-created_at", "-id")[:4]
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
