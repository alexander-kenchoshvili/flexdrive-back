"""Cross Motors supplier API import helpers.

The importer intentionally keeps the external API shape separate from our
catalog model. Cross Motors fields are normalized into product, brand, vehicle
fitment, and specs data before any database write happens.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urljoin

import requests
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductPlacement,
    ProductSide,
    ProductSpec,
    ProductStatus,
    SupplierProductBlock,
    VehicleMake,
    VehicleModel,
)


CROSSMOTORS_SOURCE_NAME = "Cross Motors"
CROSSMOTORS_SKU_PREFIX = "CM-"
NEW_SUPPLIER_CATEGORY_NAME = "ახალი"
DEFAULT_BASE_URL = "https://portal.crossmotors.ge"
DEFAULT_PAGE_SIZE = 1000
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_PAGES = 200
DEFAULT_UNCATEGORIZED_CATEGORY = "დასაკატეგორიზებელი"

PLACEMENT_LABELS = {
    ProductPlacement.FRONT: "წინა",
    ProductPlacement.REAR: "უკანა",
    ProductPlacement.UPPER: "ზედა",
    ProductPlacement.LOWER: "ქვედა",
    ProductPlacement.INNER: "შიდა",
    ProductPlacement.OUTER: "გარე",
}
SIDE_LABELS = {
    ProductSide.LEFT: "მარცხენა",
    ProductSide.RIGHT: "მარჯვენა",
    ProductSide.BOTH: "ორივე",
    ProductSide.CENTER: "ცენტრი",
}

_CATEGORY_RULES = (
    (
        "ფარები და განათება",
        (
            "ფარი",
            "ფარ",
            "სტოპ",
            "სანისლე",
            "ტუმანიკ",
            "ნისლის",
            "ნათურა",
            "ლედ",
            "led",
            "დღის განათ",
        ),
    ),
    (
        "ვიზუალის ნაწილები",
        (
            "ბამპერ",
            "ცხაურ",
            "ბადე",
            "საბუქსირე ხუფ",
        ),
    ),
    (
        "სარკეები",
        (
            "სარკე",
            "სარკის",
        ),
    ),
    (
        "რადიატორები და გაგრილება",
        (
            "რადიატორ",
            "ვინტილატორ",
            "წყლის ავზ",
            "კონდინციონერის",
            "კონდიციონერის",
        ),
    ),
    (
        "ძარის ნაწილები",
        (
            "კაპოტ",
            "კრილო",
            "ფრთა",
            "კარი",
            "პადკრილნიკ",
            "ხუფი",
            "მოლდინგ",
            "ბალკა",
            "ბრიზგავიკ",
            "სპოილერ",
            "პანელ",
        ),
    ),
    (
        "შუშები",
        (
            "შუშ",
            "საქარე",
        ),
    ),
    (
        "სავალი ნაწილები",
        (
            "ამორტიზატ",
            "სტერჟინ",
            "შარავო",
            "რაზვალ",
            "საილენ",
            "ბერკეტ",
            "ყუმბარ",
        ),
    ),
    (
        "ძრავები და ფილტრები",
        (
            "ზეთი",
            "ზეთები",
            "ფილტრ",
            "ჰაერის",
            "სვეჩ",
            "ძრავ",
            "პომპა",
            "თერმოსტატ",
        ),
    ),
    (
        "ელექტროობა",
        (
            "ელექტრო",
            "სენსორ",
            "კამერა",
            "ეკრან",
            "პარკინგ",
            "დინამო",
            "აკუმულატ",
            "wifi",
            "wi-fi",
        ),
    ),
)

_YEAR_RANGE_4_DIGIT_RE = re.compile(
    r"(?<!\d)(?P<start>19\d{2}|20\d{2})\s*[-–]\s*(?P<end>19\d{2}|20\d{2})?(?!\d)"
)
_YEAR_RANGE_2_DIGIT_RE = re.compile(
    r"(?<!\d)'?(?P<start>\d{2})\s*[-–]\s*'?(?P<end>\d{2})?(?!\d)"
)
_YEAR_SINGLE_4_DIGIT_RE = re.compile(r"(?<!\d)(?P<year>19\d{2}|20\d{2})(?!\d)")
_YEAR_SINGLE_2_DIGIT_RE = re.compile(r"(?:^|\s)'?(?P<year>\d{2})\s*$")
_SIDE_TOKEN_RE = re.compile(r"\(\s*(LH|RH)\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class CrossMotorsProductRow:
    row_number: int
    raw: dict[str, Any]
    values: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    excluded_reason: str = ""

    @property
    def is_valid(self):
        return not self.errors and not self.excluded_reason

    @property
    def is_original(self):
        return self.excluded_reason == "original"


@dataclass(frozen=True)
class CrossMotorsReport:
    rows: tuple[CrossMotorsProductRow, ...]
    existing_skus: frozenset[str] = field(default_factory=frozenset)
    synced_at: str = ""
    source_name: str = CROSSMOTORS_SOURCE_NAME

    @property
    def data_row_count(self):
        return len(self.rows)

    @property
    def original_count(self):
        return sum(1 for row in self.rows if row.is_original)

    @property
    def blocked_count(self):
        return sum(1 for row in self.rows if row.excluded_reason == "blocked")

    @property
    def importable_count(self):
        return sum(1 for row in self.rows if not row.excluded_reason)

    @property
    def valid_row_count(self):
        return sum(1 for row in self.rows if row.is_valid)

    @property
    def error_count(self):
        return sum(len(row.errors) for row in self.rows if not row.excluded_reason)

    @property
    def warning_count(self):
        return sum(len(row.warnings) for row in self.rows if not row.excluded_reason)

    @property
    def create_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid and row.values["sku"] not in self.existing_skus
        )

    @property
    def update_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid and row.values["sku"] in self.existing_skus
        )

    @property
    def missing_price_count(self):
        return sum(1 for row in self.rows if row.is_valid and row.values["supplier_price"] is None)

    @property
    def missing_price_in_stock_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid
            and row.values["supplier_price"] is None
            and row.values["stock_qty"] > 0
        )

    @property
    def purchase_ready_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid
            and row.values["supplier_price"] is not None
            and row.values["stock_qty"] > 0
        )

    @property
    def out_of_stock_count(self):
        return sum(1 for row in self.rows if row.is_valid and row.values["stock_qty"] <= 0)

    @property
    def missing_generation_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid and not row.values["generation_raw"]
        )

    @property
    def unparsed_generation_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid and row.values["generation_status"] == "unparsed"
        )

    @property
    def missing_manufacturer_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid and not row.values["part_manufacturer"]
        )

    @property
    def unknown_category_count(self):
        return sum(
            1
            for row in self.rows
            if row.is_valid and row.values["category_confidence"] == "unknown"
        )

    def unique_values(self, key):
        return tuple(
            sorted(
                {
                    str(row.values.get(key)).strip()
                    for row in self.rows
                    if row.is_valid and row.values.get(key) not in (None, "")
                }
            )
        )

    def warnings_containing(self, text):
        return tuple(
            row
            for row in self.rows
            if row.is_valid and any(text in warning for warning in row.warnings)
        )


@dataclass(frozen=True)
class CrossMotorsImportResult:
    created_products: int = 0
    updated_products: int = 0
    archived_original_products: int = 0
    archived_missing_products: int = 0
    created_categories: int = 0
    updated_categories: int = 0
    created_brands: int = 0
    updated_brands: int = 0
    created_vehicle_makes: int = 0
    updated_vehicle_makes: int = 0
    created_vehicle_models: int = 0
    updated_vehicle_models: int = 0
    created_fitments: int = 0
    created_specs: int = 0
    updated_specs: int = 0


@dataclass
class _ImportCounters:
    created_products: int = 0
    updated_products: int = 0
    archived_original_products: int = 0
    archived_missing_products: int = 0
    created_categories: int = 0
    updated_categories: int = 0
    created_brands: int = 0
    updated_brands: int = 0
    created_vehicle_makes: int = 0
    updated_vehicle_makes: int = 0
    created_vehicle_models: int = 0
    updated_vehicle_models: int = 0
    created_fitments: int = 0
    created_specs: int = 0
    updated_specs: int = 0

    def to_result(self):
        return CrossMotorsImportResult(**self.__dict__)


def fetch_crossmotors_stock(
    *,
    base_url=DEFAULT_BASE_URL,
    token,
    page_size=DEFAULT_PAGE_SIZE,
    timeout=DEFAULT_TIMEOUT,
    max_pages=DEFAULT_MAX_PAGES,
    in_stock_only=None,
):
    if not token:
        raise ValueError("Cross Motors API token is required.")

    endpoint = urljoin(base_url.rstrip("/") + "/", "api/v1/stock")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    items = []
    page_sizes = []
    synced_at = ""

    for page in range(1, max_pages + 1):
        params = {
            "page": page,
            "limit": page_size,
        }
        if in_stock_only is not None:
            params["in_stock_only"] = "true" if in_stock_only else "false"

        response = requests.get(
            endpoint,
            headers=headers,
            params=params,
            timeout=timeout,
        )
        if response.status_code == 401:
            raise ValueError("Cross Motors API returned 401 unauthorized.")
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError(f"Unexpected Cross Motors API response on page {page}.")

        batch = payload["items"]
        if page == 1:
            synced_at = str(payload.get("synced_at") or "")

        items.extend(batch)
        page_sizes.append(len(batch))

        if len(batch) < page_size:
            return items, {"page_sizes": page_sizes, "synced_at": synced_at}

        time.sleep(0.1)

    raise ValueError(f"Stopped after {max_pages} full Cross Motors API pages.")


def build_crossmotors_report(
    items,
    *,
    synced_at="",
    product_queryset: QuerySet | None = None,
    open_ended_year_to=None,
):
    if product_queryset is None:
        product_queryset = Product.objects.all()

    open_ended_year_to = open_ended_year_to or date.today().year + 1
    rows = tuple(
        _parse_item(
            item,
            row_number=index,
            open_ended_year_to=open_ended_year_to,
        )
        for index, item in enumerate(items, start=1)
    )
    skus = {row.values["sku"] for row in rows if row.values.get("sku")}
    blocked_skus = set(
        SupplierProductBlock.objects.filter(
            source_name=CROSSMOTORS_SOURCE_NAME,
            supplier_sku__in=skus,
        ).values_list("supplier_sku", flat=True)
    )
    if blocked_skus:
        rows = tuple(
            (
                CrossMotorsProductRow(
                    row_number=row.row_number,
                    raw=row.raw,
                    values=row.values,
                    errors=row.errors,
                    warnings=row.warnings,
                    excluded_reason="blocked",
                )
                if row.values.get("sku") in blocked_skus and not row.is_original
                else row
            )
            for row in rows
        )
    existing_skus = set(product_queryset.filter(sku__in=skus).values_list("sku", flat=True))

    return CrossMotorsReport(
        rows=rows,
        existing_skus=frozenset(existing_skus),
        synced_at=synced_at,
    )


@transaction.atomic
def import_crossmotors_report(report, *, archive_missing=False):
    if report.error_count:
        raise ValueError("Cannot import Cross Motors data with validation errors.")

    counters = _ImportCounters()
    category_sort_orders = {}
    categories_by_name = {}
    brand_sort_orders = {}
    make_sort_orders = {}
    imported_skus = set()

    for row in report.rows:
        sku = row.values.get("sku")
        if row.is_original:
            if sku and _archive_product_by_sku(sku):
                counters.archived_original_products += 1
            continue

        if not row.is_valid:
            continue

        values = row.values
        imported_skus.add(values["sku"])

        category = None
        if values["sku"] not in report.existing_skus:
            category = categories_by_name.get(NEW_SUPPLIER_CATEGORY_NAME)
            if category is None:
                category, category_created = _get_or_create_category(
                    NEW_SUPPLIER_CATEGORY_NAME,
                    sort_order=category_sort_orders.setdefault(
                        NEW_SUPPLIER_CATEGORY_NAME,
                        len(category_sort_orders) + 1,
                    ),
                )
                categories_by_name[NEW_SUPPLIER_CATEGORY_NAME] = category
                _increment_counter(counters, "categories", category_created)

        brand = None
        if values["part_manufacturer"]:
            brand, brand_created = _get_or_create_brand(
                values["part_manufacturer"],
                sort_order=brand_sort_orders.setdefault(
                    values["part_manufacturer"],
                    len(brand_sort_orders) + 1,
                ),
            )
            _increment_counter(counters, "brands", brand_created)

        product, product_created = _upsert_product(values, category=category, brand=brand)
        if product_created:
            counters.created_products += 1
        else:
            counters.updated_products += 1

        spec_result = _upsert_specs(product, values)
        counters.created_specs += spec_result["created"]
        counters.updated_specs += spec_result["updated"]

        fitment_result = _replace_fitment(
            product,
            values,
            make_sort_orders=make_sort_orders,
        )
        for key, created in fitment_result.items():
            _increment_counter(counters, key, created)

    if archive_missing:
        counters.archived_missing_products = (
            Product.objects.filter(
                sku__startswith=CROSSMOTORS_SKU_PREFIX,
                status=ProductStatus.PUBLISHED,
            )
            .exclude(sku__in=imported_skus)
            .update(status=ProductStatus.ARCHIVED)
        )

    return counters.to_result()


@transaction.atomic
def import_crossmotors_report_bulk(report, *, archive_missing=False, batch_size=1000):
    if report.error_count:
        raise ValueError("Cannot import Cross Motors data with validation errors.")

    counters = _ImportCounters()
    valid_rows = [row for row in report.rows if row.is_valid]
    original_skus = [
        row.values.get("sku")
        for row in report.rows
        if row.is_original and row.values.get("sku")
    ]
    now = timezone.now()

    if original_skus:
        counters.archived_original_products = Product.objects.filter(
            sku__in=original_skus,
        ).exclude(status=ProductStatus.ARCHIVED).update(
            status=ProductStatus.ARCHIVED,
            updated_at=now,
        )

    if not valid_rows:
        return counters.to_result()

    existing_skus = set(
        Product.objects.filter(
            sku__in=[row.values["sku"] for row in valid_rows]
        ).values_list("sku", flat=True)
    )

    categories = _bulk_get_or_create_categories(
        valid_rows,
        counters,
        now,
        batch_size,
        existing_skus=existing_skus,
    )
    brands = _bulk_get_or_create_brands(valid_rows, counters, now, batch_size)
    makes = _bulk_get_or_create_vehicle_makes(valid_rows, counters, now, batch_size)
    models = _bulk_get_or_create_vehicle_models(valid_rows, makes, counters, now, batch_size)

    product_result = _bulk_upsert_products(
        valid_rows,
        categories=categories,
        brands=brands,
        now=now,
        batch_size=batch_size,
    )
    counters.created_products = product_result["created"]
    counters.updated_products = product_result["updated"]

    spec_result = _bulk_upsert_specs(
        valid_rows,
        products=product_result["products"],
        now=now,
        batch_size=batch_size,
    )
    counters.created_specs = spec_result["created"]
    counters.updated_specs = spec_result["updated"]

    counters.created_fitments = _bulk_replace_fitments(
        valid_rows,
        products=product_result["products"],
        makes=makes,
        models=models,
        now=now,
        batch_size=batch_size,
    )

    if archive_missing:
        imported_skus = {row.values["sku"] for row in valid_rows}
        counters.archived_missing_products = (
            Product.objects.filter(
                sku__startswith=CROSSMOTORS_SKU_PREFIX,
                status=ProductStatus.PUBLISHED,
            )
            .exclude(sku__in=imported_skus)
            .update(status=ProductStatus.ARCHIVED, updated_at=now)
        )

    return counters.to_result()


def _bulk_get_or_create_categories(rows, counters, now, batch_size, *, existing_skus):
    new_product_rows = [
        row for row in rows if row.values["sku"] not in existing_skus
    ]
    names = [NEW_SUPPLIER_CATEGORY_NAME] if new_product_rows else []
    sort_orders = {name: index for index, name in enumerate(names, start=1)}
    existing = _casefolded_map(Category.objects.all())

    to_create = [
        Category(
            name=name,
            slug=slug,
            sort_order=sort_orders[name],
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        for name, slug in _unique_slugs_for_missing(
            Category,
            [name for name in names if name.casefold() not in existing],
            fallback_prefix="category",
        ).items()
    ]
    if to_create:
        Category.objects.bulk_create(to_create, batch_size=batch_size)
    counters.created_categories += len(to_create)

    relevant_names = {name.casefold() for name in names}
    inactive = [
        item
        for key, item in existing.items()
        if key in relevant_names and not item.is_active
    ]
    if inactive:
        for item in inactive:
            item.is_active = True
            item.updated_at = now
        Category.objects.bulk_update(inactive, ["is_active", "updated_at"], batch_size=batch_size)

    refreshed = _casefolded_map(Category.objects.filter(name__in=names))
    counters.updated_categories += max(len(names) - len(to_create), 0)
    return refreshed


def _bulk_get_or_create_brands(rows, counters, now, batch_size):
    names = _ordered_unique(row.values["part_manufacturer"] for row in rows if row.values["part_manufacturer"])
    sort_orders = {name: index for index, name in enumerate(names, start=1)}
    existing = _casefolded_map(Brand.objects.all())

    to_create = [
        Brand(
            name=name,
            slug=slug,
            sort_order=sort_orders[name],
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        for name, slug in _unique_slugs_for_missing(
            Brand,
            [name for name in names if name.casefold() not in existing],
            fallback_prefix="brand",
        ).items()
    ]
    if to_create:
        Brand.objects.bulk_create(to_create, batch_size=batch_size)

    inactive = [item for item in existing.values() if not item.is_active]
    if inactive:
        for item in inactive:
            item.is_active = True
            item.updated_at = now
        Brand.objects.bulk_update(inactive, ["is_active", "updated_at"], batch_size=batch_size)

    refreshed = _casefolded_map(Brand.objects.filter(name__in=names))
    for row in rows:
        if row.values["part_manufacturer"]:
            _increment_counter(
                counters,
                "brands",
                row.values["part_manufacturer"].casefold() not in existing,
            )
    return refreshed


def _bulk_get_or_create_vehicle_makes(rows, counters, now, batch_size):
    names = _ordered_unique(row.values["vehicle_make"] for row in rows if row.values["vehicle_make"])
    sort_orders = {name: index for index, name in enumerate(names, start=1)}
    existing = _casefolded_map(VehicleMake.objects.all())

    to_create = [
        VehicleMake(
            name=name,
            slug=slug,
            sort_order=sort_orders[name],
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        for name, slug in _unique_slugs_for_missing(
            VehicleMake,
            [name for name in names if name.casefold() not in existing],
            fallback_prefix="make",
        ).items()
    ]
    if to_create:
        VehicleMake.objects.bulk_create(to_create, batch_size=batch_size)

    inactive = [item for item in existing.values() if not item.is_active]
    if inactive:
        for item in inactive:
            item.is_active = True
            item.updated_at = now
        VehicleMake.objects.bulk_update(inactive, ["is_active", "updated_at"], batch_size=batch_size)

    refreshed = _casefolded_map(VehicleMake.objects.filter(name__in=names))
    fitment_rows = [
        row for row in rows
        if row.values["vehicle_make"]
        and row.values["vehicle_model"]
        and row.values["year_from"]
        and row.values["year_to"]
    ]
    for row in fitment_rows:
        _increment_counter(
            counters,
            "vehicle_makes",
            row.values["vehicle_make"].casefold() not in existing,
        )
    return refreshed


def _bulk_get_or_create_vehicle_models(rows, makes, counters, now, batch_size):
    desired = {}
    for row in rows:
        values = row.values
        make = makes.get((values.get("vehicle_make") or "").casefold())
        model_name = values.get("vehicle_model")
        if not (make and model_name and values["year_from"] and values["year_to"]):
            continue
        slug = _build_slug(model_name, fallback_prefix="model")
        desired[(make.id, slug)] = (make, model_name, slug)

    if not desired:
        return {}

    make_ids = {make_id for make_id, _slug in desired}
    existing_models = {
        (model.make_id, model.slug): model
        for model in VehicleModel.objects.filter(make_id__in=make_ids)
    }
    to_create = []
    to_update = []
    for key, (make, model_name, slug) in desired.items():
        existing = existing_models.get(key)
        if existing is None:
            to_create.append(
                VehicleModel(
                    make=make,
                    name=model_name,
                    slug=slug,
                    sort_order=0,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue
        changed = False
        if existing.name != model_name:
            existing.name = model_name
            changed = True
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            existing.updated_at = now
            to_update.append(existing)

    if to_create:
        VehicleModel.objects.bulk_create(to_create, batch_size=batch_size)
    if to_update:
        VehicleModel.objects.bulk_update(to_update, ["name", "is_active", "updated_at"], batch_size=batch_size)

    refreshed = {
        (model.make_id, model.slug): model
        for model in VehicleModel.objects.filter(make_id__in=make_ids)
    }
    for row in rows:
        values = row.values
        make = makes.get((values.get("vehicle_make") or "").casefold())
        if not (make and values["vehicle_model"] and values["year_from"] and values["year_to"]):
            continue
        slug = _build_slug(values["vehicle_model"], fallback_prefix="model")
        _increment_counter(counters, "vehicle_models", (make.id, slug) not in existing_models)
    return refreshed


def _bulk_upsert_products(rows, *, categories, brands, now, batch_size):
    skus = [row.values["sku"] for row in rows]
    existing = {
        product.sku: product
        for product in Product.objects.filter(sku__in=skus).select_related("category")
    }
    created = []
    updated = []
    existing_slugs = set(Product.objects.values_list("slug", flat=True))

    for row in rows:
        values = row.values
        product = existing.get(values["sku"])
        is_created = product is None
        if is_created:
            category = categories[NEW_SUPPLIER_CATEGORY_NAME.casefold()]
            product = Product(
                sku=values["sku"],
                slug=_build_unique_slug_from_set(
                    values["clean_name"] or values["name"],
                    values["sku"],
                    existing_slugs,
                ),
                category=category,
                created_at=now,
            )
        else:
            category = product.category

        brand = brands.get((values.get("part_manufacturer") or "").casefold())
        product.brand = brand
        product.name = values["name"]
        product.manufacturer_part_number = values["oem"]
        product.short_description = values["short_description"]
        product.description = values["description"]
        product.supplier_price = values["supplier_price"]
        product.price = _calculate_customer_price(product, category)
        product.old_price = None
        product.placement = values["placement"]
        product.side = values["side"]
        product.stock_qty = values["stock_qty"]
        product.status = ProductStatus.PUBLISHED
        product.seo_title = f"{values['clean_name'] or values['name']} | FlexDrive"
        product.seo_description = values["short_description"]
        product.is_universal_fitment = False
        product.updated_at = now

        if is_created:
            created.append(product)
        else:
            updated.append(product)

    if created:
        Product.objects.bulk_create(created, batch_size=batch_size)
    if updated:
        Product.objects.bulk_update(
            updated,
            [
                "brand",
                "name",
                "manufacturer_part_number",
                "short_description",
                "description",
                "supplier_price",
                "price",
                "old_price",
                "placement",
                "side",
                "stock_qty",
                "status",
                "seo_title",
                "seo_description",
                "is_universal_fitment",
                "updated_at",
            ],
            batch_size=batch_size,
        )

    products = Product.objects.in_bulk(skus, field_name="sku")
    return {"created": len(created), "updated": len(updated), "products": products}


def _bulk_upsert_specs(rows, *, products, now, batch_size):
    desired = []
    for row in rows:
        product = products[row.values["sku"]]
        for key, value, sort_order in _desired_specs(row.values):
            desired.append(
                ProductSpec(
                    product=product,
                    key=key,
                    value=value,
                    sort_order=sort_order,
                    created_at=now,
                    updated_at=now,
                )
            )

    if not desired:
        return {"created": 0, "updated": 0}

    product_ids = {spec.product_id for spec in desired}
    keys = {spec.key for spec in desired}
    existing = set(
        ProductSpec.objects.filter(product_id__in=product_ids, key__in=keys)
        .values_list("product_id", "key")
    )
    ProductSpec.objects.bulk_create(
        desired,
        update_conflicts=True,
        update_fields=["value", "sort_order", "updated_at"],
        unique_fields=["product", "key"],
        batch_size=batch_size,
    )
    created = sum(1 for spec in desired if (spec.product_id, spec.key) not in existing)
    return {"created": created, "updated": len(desired) - created}


def _bulk_replace_fitments(rows, *, products, makes, models, now, batch_size):
    product_ids = [products[row.values["sku"]].id for row in rows]
    ProductFitment.objects.filter(product_id__in=product_ids).delete()

    fitments = []
    for row in rows:
        values = row.values
        if not (
            values["vehicle_make"]
            and values["vehicle_model"]
            and values["year_from"]
            and values["year_to"]
        ):
            continue
        model_slug = _build_slug(values["vehicle_model"], fallback_prefix="model")
        make = makes.get(values["vehicle_make"].casefold())
        model = models.get((make.id, model_slug)) if make else None
        if not model:
            continue
        fitments.append(
            ProductFitment(
                product=products[values["sku"]],
                vehicle_model=model,
                year_from=values["year_from"],
                year_to=values["year_to"],
                notes=values.get("generation_raw", ""),
                created_at=now,
                updated_at=now,
            )
        )

    if fitments:
        ProductFitment.objects.bulk_create(fitments, batch_size=batch_size)
    return len(fitments)


def _desired_specs(values):
    desired_specs = []
    sort_order = 1

    def add_spec(key, value):
        nonlocal sort_order
        if value in (None, ""):
            return
        desired_specs.append((key, str(value), sort_order))
        sort_order += 1

    add_spec("OEM", values.get("oem"))
    add_spec("მწარმოებელი", values.get("part_manufacturer"))
    add_spec("მანქანა", _vehicle_label(values))
    add_spec("თაობა", values.get("generation_raw"))
    add_spec("მდებარეობა", PLACEMENT_LABELS.get(values.get("placement"), ""))
    add_spec("მხარე", SIDE_LABELS.get(values.get("side"), ""))
    return desired_specs


def _calculate_customer_price(product, category):
    if product.supplier_price is None:
        return Decimal("0.00")

    markup_percent = (
        product.markup_percent_override
        if product.markup_percent_override is not None
        else category.markup_percent
    )
    multiplier = Decimal("1.00") + (Decimal(str(markup_percent or Decimal("0.00"))) / Decimal("100"))
    return (Decimal(str(product.supplier_price)) * multiplier).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _ordered_unique(values):
    result = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _casefolded_map(queryset):
    return {item.name.casefold(): item for item in queryset}


def _unique_slugs_for_missing(model, names, *, fallback_prefix):
    existing_slugs = set(model.objects.values_list("slug", flat=True))
    result = {}
    for name in names:
        base = _build_slug(name, fallback_prefix=fallback_prefix)
        candidate = base
        suffix = 2
        while candidate in existing_slugs:
            candidate = f"{base[:140 - len(str(suffix)) - 1]}-{suffix}"
            suffix += 1
        existing_slugs.add(candidate)
        result[name] = candidate
    return result


def _build_unique_slug_from_set(name, sku, existing_slugs):
    base = _build_slug(f"{name} {sku}", fallback_prefix="product")
    candidate = base[:255]
    suffix = 2
    while candidate in existing_slugs:
        suffix_text = f"-{suffix}"
        candidate = f"{base[:255 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    existing_slugs.add(candidate)
    return candidate


def _parse_item(item, *, row_number, open_ended_year_to):
    raw = item if isinstance(item, dict) else {}
    values = {}
    errors = []
    warnings = []

    if not isinstance(item, dict):
        return CrossMotorsProductRow(
            row_number=row_number,
            raw={},
            values={},
            errors=("API item must be an object.",),
        )

    supplier_code = _clean_text(raw.get("code"))
    values["supplier_code"] = supplier_code
    values["sku"] = f"{CROSSMOTORS_SKU_PREFIX}{supplier_code}" if supplier_code else ""
    if not supplier_code:
        errors.append("Missing required value: code.")

    name = _clean_text(raw.get("name"))
    values["name"] = name
    values["clean_name"] = _clean_name(name)
    if not name:
        errors.append("Missing required value: name.")

    values["oem"] = _clean_text(raw.get("oem"))
    values["vehicle_make"] = _clean_text(raw.get("brand"))
    values["vehicle_model"] = _clean_text(raw.get("model"))
    values["generation_raw"] = _clean_text(raw.get("generation"))
    values["part_manufacturer"] = _clean_text(raw.get("manufacturer"))
    values["currency"] = _clean_text(raw.get("currency")) or "GEL"

    values["is_original"] = _is_original_part(values)
    excluded_reason = "original" if values["is_original"] else ""

    supplier_price, price_error = _parse_optional_decimal(raw.get("dealer_price"), "dealer_price")
    values["supplier_price"] = supplier_price
    if price_error:
        errors.append(price_error)
    elif supplier_price is None and not excluded_reason:
        warnings.append("dealer_price is empty; product will be visible with 0.00 GEL placeholder.")

    stock_qty, stock_error = _parse_stock_qty(raw.get("qty"))
    values["stock_qty"] = stock_qty
    if stock_error:
        errors.append(stock_error)

    if values["currency"] != "GEL" and not excluded_reason:
        errors.append("currency must be GEL for the current storefront.")

    if not values["part_manufacturer"] and not excluded_reason:
        warnings.append("manufacturer is empty; product brand will be empty.")

    year_from, year_to, generation_status = _parse_generation_years(
        values["generation_raw"],
        open_ended_year_to=open_ended_year_to,
    )
    values["year_from"] = year_from
    values["year_to"] = year_to
    values["generation_status"] = generation_status
    if not values["generation_raw"] and not excluded_reason:
        warnings.append("generation is empty; vehicle year fitment will not be created.")
    elif generation_status == "unparsed" and not excluded_reason:
        warnings.append(
            f"generation format is not recognized: {values['generation_raw']}"
        )

    values["placement"] = _parse_placement(name)
    values["side"] = _parse_side(name)
    category, category_confidence = _guess_category(values)
    values["category"] = category
    values["category_confidence"] = category_confidence
    if category_confidence == "unknown" and not excluded_reason:
        warnings.append("category could not be inferred; fallback category will be used.")

    values["description"] = _build_description(values)
    values["short_description"] = _build_short_description(values)

    return CrossMotorsProductRow(
        row_number=row_number,
        raw=raw,
        values=values,
        errors=tuple(errors),
        warnings=tuple(warnings),
        excluded_reason=excluded_reason,
    )


def _is_original_part(values):
    text = " ".join(
        (
            values.get("vehicle_make") or "",
            values.get("vehicle_model") or "",
            values.get("part_manufacturer") or "",
        )
    ).lower()
    return "original" in text or "ორიგინ" in text


def _parse_generation_years(value, *, open_ended_year_to):
    generation = _clean_text(value)
    if not generation:
        return None, None, "missing"

    match = _YEAR_RANGE_4_DIGIT_RE.search(generation)
    if match:
        year_from = int(match.group("start"))
        raw_year_to = match.group("end")
        year_to = int(raw_year_to) if raw_year_to else year_from
        return _normalize_year_range(year_from, year_to)

    match = _YEAR_RANGE_2_DIGIT_RE.search(generation)
    if match:
        year_from = _expand_two_digit_year(int(match.group("start")))
        raw_year_to = match.group("end")
        year_to = _expand_two_digit_year(int(raw_year_to)) if raw_year_to else year_from
        return _normalize_year_range(year_from, year_to)

    match = _YEAR_SINGLE_4_DIGIT_RE.search(generation)
    if match:
        year = int(match.group("year"))
        return year, year, "single"

    match = _YEAR_SINGLE_2_DIGIT_RE.search(generation)
    if match:
        year = _expand_two_digit_year(int(match.group("year")))
        return year, year, "single"

    return None, None, "unparsed"


def _normalize_year_range(year_from, year_to):
    if year_from > year_to:
        return None, None, "unparsed"
    if year_from < 1900 or year_to > 2100:
        return None, None, "unparsed"
    return year_from, year_to, "parsed"


def _expand_two_digit_year(value):
    return 2000 + value if value <= 39 else 1900 + value


def _parse_side(name):
    normalized = _clean_text(name)
    match = _SIDE_TOKEN_RE.search(normalized)
    if match:
        side = match.group(1).upper()
        return ProductSide.LEFT if side == "LH" else ProductSide.RIGHT

    lowered = normalized.lower()
    if "მარცხენა" in lowered or "მარცხ" in lowered:
        return ProductSide.LEFT
    if "მარჯვენა" in lowered or "მარჯ" in lowered:
        return ProductSide.RIGHT
    return ""


def _parse_placement(name):
    lowered = _clean_text(name).lower()
    if "წინა" in lowered:
        return ProductPlacement.FRONT
    if "უკანა" in lowered:
        return ProductPlacement.REAR
    if "ზედა" in lowered:
        return ProductPlacement.UPPER
    if "ქვედა" in lowered:
        return ProductPlacement.LOWER
    if "შიდა" in lowered:
        return ProductPlacement.INNER
    if "გარე" in lowered:
        return ProductPlacement.OUTER
    return ""


def _guess_category(values):
    text = " ".join(
        (
            values.get("name") or "",
            values.get("vehicle_make") or "",
            values.get("vehicle_model") or "",
            values.get("part_manufacturer") or "",
        )
    ).lower()

    for category, keywords in _CATEGORY_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            return category, "auto"

    return DEFAULT_UNCATEGORIZED_CATEGORY, "unknown"


def _clean_name(name):
    cleaned = _SIDE_TOKEN_RE.sub("", _clean_text(name))
    return re.sub(r"\s+", " ", cleaned).strip()


def _build_short_description(values):
    parts = [
        values.get("clean_name") or values.get("name"),
        _vehicle_label(values),
        _year_label(values),
    ]
    text = " - ".join(part for part in parts if part)
    return text[:300] if text else "ავტონაწილი FlexDrive-ის კატალოგისთვის."


def _build_description(values):
    details = []
    vehicle = _vehicle_label(values)
    years = _year_label(values)
    placement = PLACEMENT_LABELS.get(values.get("placement"), "")
    side = SIDE_LABELS.get(values.get("side"), "")

    if vehicle:
        details.append(vehicle)
    if years:
        details.append(years)
    if placement:
        details.append(placement)
    if side:
        details.append(side)

    if not details:
        return values.get("clean_name") or values.get("name") or ""

    return f"{values.get('clean_name') or values.get('name')} - {', '.join(details)}."


def _vehicle_label(values):
    return " ".join(
        part
        for part in (values.get("vehicle_make"), values.get("vehicle_model"))
        if part
    )


def _year_label(values):
    year_from = values.get("year_from")
    year_to = values.get("year_to")
    if not (year_from and year_to):
        return ""
    if year_from == year_to:
        return str(year_from)
    return f"{year_from}-{year_to}"


def _parse_optional_decimal(value, field_name):
    raw_value = _clean_text(value)
    if not raw_value:
        return None, None

    try:
        parsed = Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return None, f"{field_name} must be a decimal number."

    if parsed < 0:
        return None, f"{field_name} cannot be negative."

    return parsed.quantize(Decimal("0.01")), None


def _parse_stock_qty(value):
    raw_value = _clean_text(value)
    if not raw_value:
        return 0, None

    try:
        parsed = int(Decimal(raw_value))
    except (InvalidOperation, ValueError):
        return 0, "qty must be an integer."

    if parsed < 0:
        return 0, "qty cannot be negative."

    return parsed, None


def _archive_product_by_sku(sku):
    product = Product.objects.filter(sku=sku).first()
    if not product or product.status == ProductStatus.ARCHIVED:
        return False
    product.status = ProductStatus.ARCHIVED
    product.save(update_fields=["status", "updated_at"])
    return True


def _upsert_product(values, *, category, brand):
    product = Product.objects.filter(sku=values["sku"]).first()
    created = product is None
    if product is None:
        product = Product(
            sku=values["sku"],
            slug=_build_unique_product_slug(values["clean_name"] or values["name"], values["sku"]),
        )
        product.category = category

    product.brand = brand
    product.name = values["name"]
    product.manufacturer_part_number = values["oem"]
    product.short_description = values["short_description"]
    product.description = values["description"]
    product.supplier_price = values["supplier_price"]
    product.price = (
        values["supplier_price"]
        if values["supplier_price"] is not None
        else Decimal("0.00")
    )
    product.old_price = None
    product.placement = values["placement"]
    product.side = values["side"]
    product.stock_qty = values["stock_qty"]
    product.status = ProductStatus.PUBLISHED
    product.seo_title = f"{values['clean_name'] or values['name']} | FlexDrive"
    product.seo_description = values["short_description"]
    product.is_universal_fitment = False
    product.save()

    return product, created


def _upsert_specs(product, values):
    desired_specs = []
    sort_order = 1

    def add_spec(key, value):
        nonlocal sort_order
        if value in (None, ""):
            return
        desired_specs.append((key, str(value), sort_order))
        sort_order += 1

    add_spec("OEM", values.get("oem"))
    add_spec("მწარმოებელი", values.get("part_manufacturer"))
    add_spec("მანქანა", _vehicle_label(values))
    add_spec("თაობა", values.get("generation_raw"))
    add_spec("მდებარეობა", PLACEMENT_LABELS.get(values.get("placement"), ""))
    add_spec("მხარე", SIDE_LABELS.get(values.get("side"), ""))

    created_count = 0
    updated_count = 0
    for key, value, order in desired_specs:
        _spec, created = ProductSpec.objects.update_or_create(
            product=product,
            key=key,
            defaults={"value": value, "sort_order": order},
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    return {"created": created_count, "updated": updated_count}


def _replace_fitment(product, values, *, make_sort_orders):
    make_name = values.get("vehicle_make")
    model_name = values.get("vehicle_model")
    year_from = values.get("year_from")
    year_to = values.get("year_to")
    product.fitments.all().delete()

    if not (make_name and model_name and year_from and year_to):
        return {}

    counters = {}
    make, make_created = _get_or_create_vehicle_make(
        make_name,
        sort_order=make_sort_orders.setdefault(make_name, len(make_sort_orders) + 1),
    )
    counters["vehicle_makes"] = make_created

    model, model_created = _get_or_create_vehicle_model(make, model_name)
    counters["vehicle_models"] = model_created

    ProductFitment.objects.create(
        product=product,
        vehicle_model=model,
        year_from=year_from,
        year_to=year_to,
        notes=values.get("generation_raw", ""),
    )
    counters["fitments"] = True

    return counters


def _get_or_create_category(name, *, sort_order):
    existing = Category.objects.filter(name__iexact=name).first()
    if existing:
        changed = False
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            existing.save(update_fields=["is_active", "updated_at"])
        return existing, False

    slug = _build_unique_slug(Category, name, fallback_prefix="category")
    return Category.objects.create(
        name=name,
        slug=slug,
        sort_order=sort_order,
        is_active=True,
    ), True


def _get_or_create_brand(name, *, sort_order):
    existing = Brand.objects.filter(name__iexact=name).first()
    if existing:
        changed = False
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            existing.save(update_fields=["is_active", "updated_at"])
        return existing, False

    slug = _build_unique_slug(Brand, name, fallback_prefix="brand")
    return Brand.objects.create(
        name=name,
        slug=slug,
        sort_order=sort_order,
        is_active=True,
    ), True


def _get_or_create_vehicle_make(name, *, sort_order):
    existing = VehicleMake.objects.filter(name__iexact=name).first()
    if existing:
        changed = False
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            existing.save(update_fields=["is_active", "updated_at"])
        return existing, False

    slug = _build_unique_slug(VehicleMake, name, fallback_prefix="make")
    return VehicleMake.objects.create(
        name=name,
        slug=slug,
        sort_order=sort_order,
        is_active=True,
    ), True


def _get_or_create_vehicle_model(make, name):
    slug = _build_slug(name, fallback_prefix="model")
    existing = VehicleModel.objects.filter(make=make, slug=slug).first()
    if existing:
        changed = False
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if existing.name != name:
            existing.name = name
            changed = True
        if changed:
            existing.save(update_fields=["name", "is_active", "updated_at"])
        return existing, False

    return VehicleModel.objects.create(
        make=make,
        name=name,
        slug=slug,
        sort_order=0,
        is_active=True,
    ), True


def _increment_counter(counters, entity_name, created):
    field_name = f"{'created' if created else 'updated'}_{entity_name}"
    setattr(counters, field_name, getattr(counters, field_name) + 1)


def _to_text(value):
    if value is None:
        return ""
    return str(value)


def _clean_text(value):
    return _to_text(value).strip()


def _build_unique_product_slug(name, sku):
    base = _build_slug(f"{name} {sku}", fallback_prefix="product")
    candidate = base[:255]
    suffix = 2
    while Product.objects.filter(slug=candidate).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[:255 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _build_unique_slug(model, value, *, fallback_prefix):
    base = _build_slug(value, fallback_prefix=fallback_prefix)
    candidate = base
    suffix = 2
    while model.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _build_slug(value, *, fallback_prefix):
    transliterated = _transliterate_georgian(_clean_text(value))
    candidate = slugify(transliterated) or _hash_slug(value, fallback_prefix)
    return candidate[:140]


def _hash_slug(value, fallback_prefix):
    digest = hashlib.sha1(_clean_text(value).encode("utf-8")).hexdigest()[:10]
    return f"{fallback_prefix}-{digest}"


def _transliterate_georgian(value):
    return value.translate(
        str.maketrans(
            {
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
                "ყ": "q",
                "შ": "sh",
                "ჩ": "ch",
                "ც": "ts",
                "ძ": "dz",
                "წ": "ts",
                "ჭ": "ch",
                "ხ": "kh",
                "ჯ": "j",
                "ჰ": "h",
            }
        )
    )
