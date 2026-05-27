import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

from django.db import transaction
from django.db.models import QuerySet
from django.utils.text import slugify
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from catalog.models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductSpec,
    ProductStatus,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)


SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

REQUIRED_HEADERS = (
    "sku",
    "name_ka",
    "category",
    "price_gel",
    "stock_quantity",
)

KNOWN_HEADERS = (
    "sku",
    "supplier_sku",
    "name_ka",
    "name_en",
    "description_ka",
    "category",
    "part_brand",
    "price_gel",
    "stock_quantity",
    "condition",
    "vehicle_make",
    "vehicle_model",
    "year_from",
    "year_to",
    "engine",
    "compatibility_notes",
    "image_url",
    "supplier_name",
    "is_active",
    "currency",
)


@dataclass(frozen=True)
class SupplierProductRow:
    row_number: int
    values: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self):
        return not self.errors


@dataclass(frozen=True)
class SupplierSheetReport:
    spreadsheet_id: str
    sheet_name: str
    headers: tuple[str, ...]
    rows: tuple[SupplierProductRow, ...]
    existing_skus: frozenset[str] = field(default_factory=frozenset)

    @property
    def data_row_count(self):
        return len(self.rows)

    @property
    def valid_row_count(self):
        return sum(1 for row in self.rows if row.is_valid)

    @property
    def error_count(self):
        return sum(len(row.errors) for row in self.rows)

    @property
    def warning_count(self):
        return sum(len(row.warnings) for row in self.rows)

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

    def unique_values(self, key):
        return tuple(
            sorted(
                {
                    str(row.values.get(key)).strip()
                    for row in self.rows
                    if row.values.get(key) not in (None, "")
                }
            )
        )

    def active_counts(self):
        active = sum(
            1
            for row in self.rows
            if row.is_valid and row.values.get("is_active", True) is True
        )
        inactive = sum(
            1
            for row in self.rows
            if row.is_valid and row.values.get("is_active", True) is False
        )
        return active, inactive


@dataclass(frozen=True)
class SupplierSheetImportResult:
    created_products: int = 0
    updated_products: int = 0
    created_categories: int = 0
    updated_categories: int = 0
    created_brands: int = 0
    updated_brands: int = 0
    created_vehicle_makes: int = 0
    updated_vehicle_makes: int = 0
    created_vehicle_models: int = 0
    updated_vehicle_models: int = 0
    created_vehicle_engines: int = 0
    updated_vehicle_engines: int = 0
    created_fitments: int = 0
    updated_fitments: int = 0
    created_specs: int = 0
    updated_specs: int = 0


@dataclass
class _ImportCounters:
    created_products: int = 0
    updated_products: int = 0
    created_categories: int = 0
    updated_categories: int = 0
    created_brands: int = 0
    updated_brands: int = 0
    created_vehicle_makes: int = 0
    updated_vehicle_makes: int = 0
    created_vehicle_models: int = 0
    updated_vehicle_models: int = 0
    created_vehicle_engines: int = 0
    updated_vehicle_engines: int = 0
    created_fitments: int = 0
    updated_fitments: int = 0
    created_specs: int = 0
    updated_specs: int = 0

    def to_result(self):
        return SupplierSheetImportResult(**self.__dict__)


def fetch_sheet_values(
    *,
    credentials_file=None,
    credentials_info=None,
    spreadsheet_id,
    sheet_name,
    cell_range="A:T",
    timeout=30,
):
    if credentials_info is not None:
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=[SHEETS_READONLY_SCOPE],
        )
    elif credentials_file:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=[SHEETS_READONLY_SCOPE],
        )
    else:
        raise ValueError(
            "Google Sheets credentials are required. Provide credentials_file "
            "or credentials_info."
        )

    session = AuthorizedSession(credentials)
    encoded_range = quote(f"{sheet_name}!{cell_range}", safe="")
    url = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        f"{spreadsheet_id}/values/{encoded_range}"
    )

    try:
        response = session.get(
            url,
            params={
                "majorDimension": "ROWS",
                "valueRenderOption": "UNFORMATTED_VALUE",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json().get("values", [])
    finally:
        session.close()


def build_supplier_sheet_report(
    *,
    spreadsheet_id,
    sheet_name,
    values,
    product_queryset: QuerySet | None = None,
):
    if not values:
        raise ValueError("Sheet range is empty.")

    headers = _normalize_headers(values[0])
    _validate_headers(headers)

    existing_skus = _load_existing_skus(headers, values[1:], product_queryset)
    parsed_rows = tuple(
        _parse_row(row_number=index, headers=headers, raw_row=row)
        for index, row in enumerate(values[1:], start=2)
        if any(_to_text(cell) for cell in row)
    )

    return SupplierSheetReport(
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        headers=tuple(headers),
        rows=parsed_rows,
        existing_skus=frozenset(existing_skus),
    )


@transaction.atomic
def import_supplier_sheet_report(report):
    if report.error_count:
        raise ValueError("Cannot import supplier sheet with validation errors.")

    counters = _ImportCounters()
    category_sort_orders = {}
    brand_sort_orders = {}
    make_sort_orders = {}

    for row in report.rows:
        if not row.is_valid:
            continue

        values = row.values
        category, category_created = _get_or_create_category(
            values["category"],
            sort_order=category_sort_orders.setdefault(
                values["category"],
                len(category_sort_orders) + 1,
            ),
        )
        _increment_counter(counters, "categories", category_created)

        brand = None
        if values["brand"]:
            brand, brand_created = _get_or_create_brand(
                values["brand"],
                sort_order=brand_sort_orders.setdefault(
                    values["brand"],
                    len(brand_sort_orders) + 1,
                ),
            )
            _increment_counter(counters, "brands", brand_created)

        product, product_created = _upsert_product(values, category=category, brand=brand)
        if product_created:
            counters.created_products += 1
        else:
            counters.updated_products += 1

        spec_created = _upsert_condition_spec(product, values)
        if spec_created is True:
            counters.created_specs += 1
        elif spec_created is False:
            counters.updated_specs += 1

        fitment_result = _upsert_fitment(
            product,
            values,
            make_sort_orders=make_sort_orders,
        )
        if fitment_result:
            for key, created in fitment_result.items():
                _increment_counter(counters, key, created)

    return counters.to_result()


def _normalize_headers(raw_headers):
    return [_to_text(header).strip().lower() for header in raw_headers]


def _validate_headers(headers):
    missing = [header for header in REQUIRED_HEADERS if header not in headers]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"Missing required header(s): {missing_list}.")


def _load_existing_skus(headers, data_rows, product_queryset):
    if product_queryset is None:
        product_queryset = Product.objects.all()

    sku_index = headers.index("sku")
    skus = {
        _to_text(row[sku_index]).strip()
        for row in data_rows
        if len(row) > sku_index and _to_text(row[sku_index]).strip()
    }
    if not skus:
        return set()

    return set(product_queryset.filter(sku__in=skus).values_list("sku", flat=True))


def _parse_row(*, row_number, headers, raw_row):
    padded_row = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
    raw_values = {
        header: padded_row[index] if index < len(padded_row) else ""
        for index, header in enumerate(headers)
    }
    values = {}
    errors = []
    warnings = []

    for header in headers:
        if header not in KNOWN_HEADERS:
            warnings.append(f"Unknown column '{header}' will be ignored.")

    for header in ("sku", "name_ka", "category"):
        if not _to_text(raw_values.get(header)).strip():
            errors.append(f"Missing required value: {header}.")

    values["sku"] = _clean_text(raw_values.get("sku"))
    values["supplier_sku"] = _clean_text(raw_values.get("supplier_sku"))
    values["name"] = _clean_text(raw_values.get("name_ka"))
    values["name_en"] = _clean_text(raw_values.get("name_en"))
    values["description"] = _clean_text(raw_values.get("description_ka"))
    values["category"] = _clean_text(raw_values.get("category"))
    values["brand"] = _clean_text(raw_values.get("part_brand"))
    values["condition"] = _clean_text(raw_values.get("condition"))
    values["vehicle_make"] = _clean_text(raw_values.get("vehicle_make"))
    values["vehicle_model"] = _clean_text(raw_values.get("vehicle_model"))
    values["engine"] = _clean_text(raw_values.get("engine"))
    values["compatibility_notes"] = _clean_text(raw_values.get("compatibility_notes"))
    values["image_url"] = _clean_text(raw_values.get("image_url"))
    values["supplier_name"] = _clean_text(raw_values.get("supplier_name"))
    values["currency"] = _clean_text(raw_values.get("currency")) or "GEL"

    supplier_price, price_error = _parse_decimal(raw_values.get("price_gel"), "price_gel")
    values["supplier_price"] = supplier_price
    if price_error:
        errors.append(price_error)

    stock_qty, stock_error = _parse_int(
        raw_values.get("stock_quantity"),
        "stock_quantity",
        minimum=0,
    )
    values["stock_qty"] = stock_qty
    if stock_error:
        errors.append(stock_error)

    year_from, year_from_error = _parse_optional_int(
        raw_values.get("year_from"),
        "year_from",
        minimum=1900,
        maximum=2100,
    )
    year_to, year_to_error = _parse_optional_int(
        raw_values.get("year_to"),
        "year_to",
        minimum=1900,
        maximum=2100,
    )
    values["year_from"] = year_from
    values["year_to"] = year_to
    if year_from_error:
        errors.append(year_from_error)
    if year_to_error:
        errors.append(year_to_error)
    if year_from and year_to and year_from > year_to:
        errors.append("year_from cannot be greater than year_to.")

    is_active, is_active_error = _parse_optional_bool(raw_values.get("is_active"))
    values["is_active"] = True if is_active is None else is_active
    if is_active_error:
        errors.append(f"is_active {is_active_error}")

    if values["currency"] != "GEL":
        errors.append("currency must be GEL for the current storefront.")

    if values["name_en"]:
        warnings.append("name_en is present but is not used by the current Georgian UI.")
    if values["image_url"]:
        warnings.append("image_url is present but image import is not implemented yet.")
    if not values["supplier_name"]:
        warnings.append("supplier_name is empty; importer will use configured supplier metadata later.")

    return SupplierProductRow(
        row_number=row_number,
        values=values,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _to_text(value):
    if value is None:
        return ""
    return str(value)


def _clean_text(value):
    return _to_text(value).strip()


def _parse_decimal(value, field_name):
    raw_value = _clean_text(value)
    if not raw_value:
        return None, f"Missing required value: {field_name}."

    try:
        parsed = Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return None, f"{field_name} must be a decimal number."

    if parsed < 0:
        return None, f"{field_name} cannot be negative."

    return parsed, None


def _parse_int(value, field_name, *, minimum=None, maximum=None):
    raw_value = _clean_text(value)
    if not raw_value:
        return None, f"Missing required value: {field_name}."

    try:
        parsed = int(raw_value)
    except ValueError:
        return None, f"{field_name} must be an integer."

    range_error = _validate_int_range(parsed, field_name, minimum=minimum, maximum=maximum)
    if range_error:
        return None, range_error

    return parsed, None


def _parse_optional_int(value, field_name, *, minimum=None, maximum=None):
    raw_value = _clean_text(value)
    if not raw_value:
        return None, None

    try:
        parsed = int(raw_value)
    except ValueError:
        return None, f"{field_name} must be an integer."

    range_error = _validate_int_range(parsed, field_name, minimum=minimum, maximum=maximum)
    if range_error:
        return None, range_error

    return parsed, None


def _validate_int_range(value, field_name, *, minimum=None, maximum=None):
    if minimum is not None and value < minimum:
        return f"{field_name} must be greater than or equal to {minimum}."
    if maximum is not None and value > maximum:
        return f"{field_name} must be less than or equal to {maximum}."
    return None


def _parse_optional_bool(value):
    raw_value = _clean_text(value)
    if not raw_value:
        return None, None

    normalized = raw_value.lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True, None
    if normalized in {"false", "0", "no", "n"}:
        return False, None

    return None, "must be TRUE or FALSE."


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


def _upsert_product(values, *, category, brand):
    product = Product.objects.filter(sku=values["sku"]).first()
    created = product is None
    if product is None:
        product = Product(
            sku=values["sku"],
            slug=_build_unique_product_slug(values["name"], values["sku"]),
        )

    product.category = category
    product.brand = brand
    product.name = values["name"]
    product.short_description = _short_description(values["description"], values)
    product.description = values["description"]
    product.supplier_price = values["supplier_price"]
    product.old_price = None
    product.stock_qty = values["stock_qty"]
    product.status = (
        ProductStatus.PUBLISHED
        if values.get("is_active", True)
        else ProductStatus.ARCHIVED
    )
    product.seo_title = f"{values['name']} | FlexDrive"
    product.seo_description = product.short_description
    product.is_universal_fitment = False
    product.save()

    return product, created


def _upsert_condition_spec(product, values):
    condition = values.get("condition")
    if not condition:
        return None

    spec, created = ProductSpec.objects.update_or_create(
        product=product,
        key="მდგომარეობა",
        defaults={
            "value": _condition_display_value(condition),
            "sort_order": 1,
        },
    )
    return created


def _upsert_fitment(product, values, *, make_sort_orders):
    make_name = values.get("vehicle_make")
    model_name = values.get("vehicle_model")
    year_from = values.get("year_from")
    year_to = values.get("year_to")
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

    engine = None
    engine_name = values.get("engine")
    if engine_name:
        engine, engine_created = _get_or_create_vehicle_engine(model, engine_name)
        counters["vehicle_engines"] = engine_created

    _fitment, fitment_created = ProductFitment.objects.update_or_create(
        product=product,
        vehicle_model=model,
        engine=engine,
        year_from=year_from,
        year_to=year_to,
        defaults={
            "notes": values.get("compatibility_notes", ""),
        },
    )
    counters["fitments"] = fitment_created

    return counters


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


def _get_or_create_vehicle_engine(model, name):
    slug = _build_slug(name, fallback_prefix="engine")
    existing = VehicleEngine.objects.filter(model=model, slug=slug).first()
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

    return VehicleEngine.objects.create(
        model=model,
        name=name,
        slug=slug,
        sort_order=0,
        is_active=True,
    ), True


def _increment_counter(counters, entity_name, created):
    field_name = f"{'created' if created else 'updated'}_{entity_name}"
    setattr(counters, field_name, getattr(counters, field_name) + 1)


def _short_description(description, values):
    text = description or "ავტონაწილი FlexDrive-ის კატალოგისთვის."
    if len(text) <= 300:
        return text
    return f"{text[:297].rstrip()}..."


def _condition_display_value(condition):
    return {
        "new": "ახალი",
        "aftermarket": "ანალოგი",
        "oem": "OEM",
        "used - good": "მეორადი - კარგი",
    }.get(condition.lower(), condition)


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
