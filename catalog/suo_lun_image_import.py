from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import requests
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Prefetch, QuerySet
from PIL import Image

from catalog.models import Product, ProductFitment, ProductImage, ProductStatus


CROSSMOTORS_SITE_URL = "https://www.crossmotors.ge"
CROSSMOTORS_PRODUCT_SITEMAP_URL = (
    "https://www.crossmotors.ge/store-products-sitemap.xml"
)
CROSSMOTORS_PAGES_SITEMAP_URL = "https://www.crossmotors.ge/pages-sitemap.xml"
CROSSMOTORS_ACCESS_TOKENS_URL = f"{CROSSMOTORS_SITE_URL}/_api/v1/access-tokens"
CROSSMOTORS_STOREFRONT_API_URL = (
    f"{CROSSMOTORS_SITE_URL}/_api/wix-ecommerce-storefront-web/api"
)
CROSSMOTORS_STORES_APP_ID = "1380b703-ce81-ff05-f115-39571d94dfcd"
CROSSMOTORS_STOREFRONT_PAGE_SIZE = 100
SUO_LUN_BRAND_NAME = "Suo Lun"
SOURCE_MANUFACTURER_LABEL = "SL - China"
DEFAULT_TIMEOUT = 30
DEFAULT_OPEN_ENDED_YEAR_TO = 2027
DEFAULT_USER_AGENT = "FlexDriveSuoLunImageImporter/1.0"
MAX_IMAGE_BYTES = 10 * 1024 * 1024

PRODUCT_CARD_RE = re.compile(
    r'<div\s+data-slug="(?P<slug>[^"]+)"[^>]*'
    r'aria-label="(?P<aria>[^"]+)"[^>]*'
    r'data-hook="product-item-root"[\s\S]*?'
    r'<a\s+href="(?P<href>https://www\.crossmotors\.ge/product-page/[^"]+)"',
    re.IGNORECASE,
)
WIX_STORES_COLLECTION_ID_RE = re.compile(
    r'"catalog":\{"isCatalogV3":(?:true|false),"category":\{"id":"(?P<id>[0-9a-f-]{36})"',
    re.IGNORECASE,
)

NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
SPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"(?<!\d)(20\d{2}|\d{2})(?!\d)")
SIDE_LEFT_RE = re.compile(r"\b(lh|left)\b|მარცხენა", re.IGNORECASE)
SIDE_RIGHT_RE = re.compile(r"\b(rh|right)\b|მარჯვენა", re.IGNORECASE)

VEHICLE_MAKE_TOKENS = {
    "subaru",
    "volkswagen",
    "vw",
}
SOURCE_NOISE_TOKENS = {
    "sl",
    "china",
    "tyc",
    "tyg",
    "tw",
    "gordon",
    "modified",
    "lh",
    "rh",
    "left",
    "right",
}

WIX_STOREFRONT_PRODUCTS_QUERY = """
query getFilteredProducts($mainCollectionId: String!, $offset: Int, $limit: Int) {
  catalog {
    category(categoryId: $mainCollectionId) {
      productsWithMetaData(limit: $limit, offset: $offset, onlyVisible: true) {
        totalCount
        list {
          id
          ribbon
          name
          urlPart
          media {
            fullUrl
            url
            width
            height
            altText
          }
        }
      }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class CrossMotorsSourceProduct:
    source_url: str
    image_url: str
    name: str
    manufacturer: str
    source_page_url: str
    source_vehicle_label: str
    source_year_from: int | None
    source_year_to: int | None
    source_model_tokens: tuple[str, ...]


@dataclass(frozen=True)
class SuoLunImageMatch:
    product: Product
    candidate: CrossMotorsSourceProduct | None
    confidence: str
    action: str
    reason: str
    score: float = 0
    ambiguity_count: int = 0


@dataclass(frozen=True)
class SuoLunImageReport:
    matches: tuple[SuoLunImageMatch, ...]

    @property
    def product_count(self):
        return len(self.matches)

    @property
    def auto_import_count(self):
        return self.count_action("auto_import")

    @property
    def review_count(self):
        return self.count_action("review")

    @property
    def skipped_count(self):
        return self.count_action("skip")

    @property
    def no_candidate_count(self):
        return sum(1 for match in self.matches if match.candidate is None)

    @property
    def existing_image_count(self):
        return sum(1 for match in self.matches if match.reason == "existing_image")

    def count_action(self, action):
        return sum(1 for match in self.matches if match.action == action)

    def by_action(self, action):
        return tuple(match for match in self.matches if match.action == action)


@dataclass(frozen=True)
class SuoLunImageImportResult:
    attempted: int
    imported: int
    skipped: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ExternalSuoLunImageCandidate:
    sku: str
    source: str
    source_url: str
    source_title: str
    image_urls: tuple[str, ...]
    action: str
    confidence: str
    reason: str


@dataclass(frozen=True)
class ExternalSuoLunImageMatch:
    product: Product
    candidate: ExternalSuoLunImageCandidate
    action: str
    confidence: str
    reason: str


@dataclass(frozen=True)
class ExternalSuoLunImageReport:
    matches: tuple[ExternalSuoLunImageMatch, ...]
    candidate_count: int
    missing_product_skus: tuple[str, ...]
    existing_image_skus: tuple[str, ...]
    ignored_count: int

    @property
    def auto_import_count(self):
        return sum(1 for match in self.matches if match.action == "auto_import")

    @property
    def review_count(self):
        return sum(1 for match in self.matches if match.action == "review")

    def by_action(self, action):
        return tuple(match for match in self.matches if match.action == action)


@dataclass(frozen=True)
class ReviewApprovedSuoLunImageReport:
    matches: tuple[SuoLunImageMatch, ...]
    approved_decision_count: int
    missing_product_skus: tuple[str, ...]
    missing_review_data_skus: tuple[str, ...]
    missing_image_url_skus: tuple[str, ...]
    existing_image_skus: tuple[str, ...]


def get_suo_lun_products(queryset: QuerySet | None = None):
    base_queryset = queryset if queryset is not None else Product.objects.all()
    return (
        base_queryset.filter(
            brand__name__iexact=SUO_LUN_BRAND_NAME,
            status=ProductStatus.PUBLISHED,
        )
        .select_related("brand", "category")
        .prefetch_related(
            "images",
            Prefetch(
                "fitments",
                queryset=ProductFitment.objects.select_related("vehicle_model__make"),
            ),
        )
        .order_by("sku")
    )


def fetch_crossmotors_source_products(
    *,
    product_sitemap_url=CROSSMOTORS_PRODUCT_SITEMAP_URL,
    pages_sitemap_url=CROSSMOTORS_PAGES_SITEMAP_URL,
    timeout=DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
):
    client = session or requests.Session()
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    product_sitemap = _fetch_text(
        client,
        product_sitemap_url,
        timeout=timeout,
        headers=headers,
    )
    image_by_url = parse_crossmotors_product_sitemap(product_sitemap)

    pages_sitemap = _fetch_text(
        client,
        pages_sitemap_url,
        timeout=timeout,
        headers=headers,
    )
    page_urls = parse_crossmotors_pages_sitemap(pages_sitemap)

    candidates = []
    seen = set()
    storefront_access_token = None
    for page_url in page_urls:
        if _is_non_product_listing_page(page_url):
            continue

        page_html = _fetch_text(client, page_url, timeout=timeout, headers=headers)
        page_candidates = list(parse_crossmotors_page_products(
            page_url,
            page_html,
            image_by_url=image_by_url,
        ))

        collection_id = parse_crossmotors_storefront_collection_id(page_html)
        if collection_id:
            if not storefront_access_token:
                storefront_access_token = fetch_crossmotors_storefront_access_token(
                    client,
                    timeout=timeout,
                    headers=headers,
                )
            page_candidates.extend(
                fetch_crossmotors_storefront_products(
                    client,
                    page_url,
                    collection_id,
                    storefront_access_token,
                    timeout=timeout,
                    headers=headers,
                )
            )

        for candidate in page_candidates:
            key = (candidate.source_page_url, candidate.source_url)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

    return tuple(candidates)


def parse_crossmotors_product_sitemap(xml_text):
    namespace = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "image": "http://www.google.com/schemas/sitemap-image/1.1",
    }
    root = ElementTree.fromstring(xml_text)
    image_by_url = {}
    for url_node in root.findall("sm:url", namespace):
        loc_node = url_node.find("sm:loc", namespace)
        image_node = url_node.find("image:image/image:loc", namespace)
        if loc_node is None or image_node is None:
            continue
        loc = (loc_node.text or "").strip()
        image_url = (image_node.text or "").strip()
        if loc and image_url:
            image_by_url[loc] = image_url
    return image_by_url


def parse_crossmotors_pages_sitemap(xml_text):
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ElementTree.fromstring(xml_text)
    return tuple(
        (loc_node.text or "").strip()
        for loc_node in root.findall("sm:url/sm:loc", namespace)
        if (loc_node.text or "").strip()
    )


def parse_crossmotors_page_products(page_url, page_html, *, image_by_url):
    source_vehicle_label = _title_from_url(page_url)
    year_from, year_to = _extract_year_range(source_vehicle_label)
    model_tokens = _vehicle_model_tokens(source_vehicle_label)

    candidates = []
    for match in PRODUCT_CARD_RE.finditer(page_html):
        aria_label = html.unescape(match.group("aria")).strip()
        source_url = html.unescape(match.group("href")).strip()
        source_name, manufacturer = _split_aria_label(aria_label)
        image_url = image_by_url.get(source_url, "")

        if not _is_suo_lun_source_label(manufacturer):
            continue

        if not image_url:
            continue

        candidates.append(
            CrossMotorsSourceProduct(
                source_url=source_url,
                image_url=image_url,
                name=source_name,
                manufacturer=manufacturer,
                source_page_url=page_url,
                source_vehicle_label=source_vehicle_label,
                source_year_from=year_from,
                source_year_to=year_to,
                source_model_tokens=tuple(model_tokens),
            )
        )

    return tuple(candidates)


def parse_crossmotors_storefront_collection_id(page_html):
    match = WIX_STORES_COLLECTION_ID_RE.search(page_html or "")
    if not match:
        return ""
    return match.group("id")


def fetch_crossmotors_storefront_access_token(client, *, timeout, headers):
    response = client.get(CROSSMOTORS_ACCESS_TOKENS_URL, timeout=timeout, headers=headers)
    response.raise_for_status()
    payload = response.json()
    app_config = (payload.get("apps") or {}).get(CROSSMOTORS_STORES_APP_ID) or {}
    access_token = app_config.get("accessToken")
    if not access_token:
        raise ValueError("CrossMotors Wix Stores access token was not found.")
    return access_token


def fetch_crossmotors_storefront_products(
    client,
    page_url,
    collection_id,
    access_token,
    *,
    timeout,
    headers,
):
    candidates = []
    offset = 0
    total_count = None
    request_headers = {
        **headers,
        "authorization": access_token,
        "content-type": "application/json",
    }

    while total_count is None or offset < total_count:
        payload = {
            "variables": {
                "mainCollectionId": collection_id,
                "offset": offset,
                "limit": CROSSMOTORS_STOREFRONT_PAGE_SIZE,
            },
            "query": WIX_STOREFRONT_PRODUCTS_QUERY,
            "source": "WixStoresWebClient",
            "operationName": "getFilteredProducts",
        }
        response = client.post(
            CROSSMOTORS_STOREFRONT_API_URL,
            json=payload,
            timeout=timeout,
            headers=request_headers,
        )
        response.raise_for_status()
        products_metadata = (
            response.json()
            .get("data", {})
            .get("catalog", {})
            .get("category", {})
            .get("productsWithMetaData", {})
        )
        total_count = int(products_metadata.get("totalCount") or 0)
        products = products_metadata.get("list") or []
        if not products:
            break

        candidates.extend(
            parse_crossmotors_storefront_products(page_url, products)
        )

        offset += len(products)
        if len(products) < CROSSMOTORS_STOREFRONT_PAGE_SIZE:
            break

    return tuple(candidates)


def parse_crossmotors_storefront_products(page_url, products):
    source_vehicle_label = _title_from_url(page_url)
    year_from, year_to = _extract_year_range(source_vehicle_label)
    model_tokens = _vehicle_model_tokens(source_vehicle_label)

    candidates = []
    for product in products:
        manufacturer = str(product.get("ribbon") or "").strip()
        if not _is_suo_lun_source_label(manufacturer):
            continue

        source_name = str(product.get("name") or "").strip()
        url_part = str(product.get("urlPart") or "").strip()
        image_url = _first_storefront_image_url(product)
        if not source_name or not url_part or not image_url:
            continue

        candidates.append(
            CrossMotorsSourceProduct(
                source_url=f"{CROSSMOTORS_SITE_URL}/product-page/{url_part}",
                image_url=image_url,
                name=source_name,
                manufacturer=manufacturer,
                source_page_url=page_url,
                source_vehicle_label=source_vehicle_label,
                source_year_from=year_from,
                source_year_to=year_to,
                source_model_tokens=tuple(model_tokens),
            )
        )

    return tuple(candidates)


def _first_storefront_image_url(product):
    media_items = product.get("media") or []
    if not media_items:
        return ""

    first_media = media_items[0] or {}
    return str(first_media.get("fullUrl") or first_media.get("url") or "").strip()


def build_suo_lun_image_report(
    products,
    candidates,
    *,
    skip_existing=True,
):
    matches = []
    for product in products:
        if skip_existing and _product_has_images(product):
            matches.append(
                SuoLunImageMatch(
                    product=product,
                    candidate=None,
                    confidence="none",
                    action="skip",
                    reason="existing_image",
                )
            )
            continue

        product_candidates = _rank_candidates(product, candidates)
        if not product_candidates:
            matches.append(
                SuoLunImageMatch(
                    product=product,
                    candidate=None,
                    confidence="none",
                    action="skip",
                    reason="no_candidate",
                )
            )
            continue

        best = product_candidates[0]
        ambiguity_count = len(
            {
                candidate.source_url
                for candidate, score, exact_name, side_quality in product_candidates
                if score >= 0.82 and (exact_name or score >= 0.92)
            }
        )
        candidate, score, exact_name, side_quality = best

        if ambiguity_count > 1:
            action = "review"
            confidence = "medium"
            reason = "ambiguous_candidates"
        elif exact_name and side_quality != "missing":
            action = "auto_import"
            confidence = "high"
            reason = "exact_name_vehicle_context"
        elif score >= 0.92 and side_quality == "ok":
            action = "auto_import"
            confidence = "high"
            reason = "strong_name_vehicle_context"
        else:
            action = "review"
            confidence = "medium"
            reason = "needs_manual_review"

        matches.append(
            SuoLunImageMatch(
                product=product,
                candidate=candidate,
                confidence=confidence,
                action=action,
                reason=reason,
                score=score,
                ambiguity_count=ambiguity_count,
            )
        )

    return SuoLunImageReport(tuple(matches))


def import_suo_lun_images(
    matches,
    *,
    timeout=DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
    limit: int | None = None,
):
    client = session or requests.Session()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    imported = 0
    attempted = 0
    skipped = 0
    errors = []

    for match in matches:
        if limit is not None and attempted >= limit:
            break
        if match.action != "auto_import" or match.candidate is None:
            skipped += 1
            continue
        if _product_has_images(match.product):
            skipped += 1
            continue

        attempted += 1
        try:
            content, filename = download_candidate_image(
                match.candidate.image_url,
                session=client,
                timeout=timeout,
                headers=headers,
            )
            attach_product_image(match.product, content, filename)
            imported += 1
        except Exception as exc:
            errors.append(f"{match.product.sku}: {exc}")

    return SuoLunImageImportResult(
        attempted=attempted,
        imported=imported,
        skipped=skipped,
        errors=tuple(errors),
    )


def build_external_suo_lun_image_report(
    candidate_path,
    products,
    *,
    skip_existing=True,
):
    rows = _load_external_candidate_rows(candidate_path)
    product_by_sku = {product.sku: product for product in products}
    matches = []
    missing_product_skus = []
    existing_image_skus = []
    ignored_count = 0

    for row in rows:
        action = str(row.get("action") or "").strip()
        if action not in {"auto_import", "review"}:
            ignored_count += 1
            continue

        image_urls = tuple(
            str(image_url or "").strip()
            for image_url in row.get("image_urls") or []
            if str(image_url or "").strip()
        )
        if not image_urls:
            ignored_count += 1
            continue

        sku = str(row.get("sku") or "").strip()
        product = product_by_sku.get(sku)
        if product is None:
            missing_product_skus.append(sku)
            continue

        if skip_existing and _product_has_images(product):
            existing_image_skus.append(sku)
            continue

        candidate = ExternalSuoLunImageCandidate(
            sku=sku,
            source=str(row.get("source") or "").strip(),
            source_url=str(row.get("source_url") or "").strip(),
            source_title=str(row.get("source_title") or "").strip(),
            image_urls=image_urls,
            action=action,
            confidence=str(row.get("confidence") or "").strip(),
            reason=str(row.get("reason") or "").strip(),
        )
        matches.append(
            ExternalSuoLunImageMatch(
                product=product,
                candidate=candidate,
                action=action,
                confidence=candidate.confidence,
                reason=candidate.reason,
            )
        )

    return ExternalSuoLunImageReport(
        matches=tuple(matches),
        candidate_count=len(rows),
        missing_product_skus=tuple(sku for sku in missing_product_skus if sku),
        existing_image_skus=tuple(existing_image_skus),
        ignored_count=ignored_count,
    )


def import_external_suo_lun_images(
    matches,
    *,
    timeout=DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
    limit: int | None = None,
    max_images_per_product=5,
):
    client = session or requests.Session()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    imported = 0
    attempted = 0
    skipped = 0
    errors = []

    for match in matches:
        if limit is not None and attempted >= limit:
            break
        if match.action != "auto_import":
            skipped += 1
            continue
        if _product_has_images(match.product):
            skipped += 1
            continue

        attempted += 1
        try:
            downloaded_images = []
            for image_url in match.candidate.image_urls[:max_images_per_product]:
                content, filename = download_candidate_image(
                    image_url,
                    session=client,
                    timeout=timeout,
                    headers=headers,
                )
                downloaded_images.append((content, filename))

            created_images = attach_product_images(match.product, downloaded_images)
            if created_images:
                imported += 1
            else:
                skipped += 1
        except Exception as exc:
            errors.append(f"{match.product.sku}: {exc}")

    return SuoLunImageImportResult(
        attempted=attempted,
        imported=imported,
        skipped=skipped,
        errors=tuple(errors),
    )


def load_review_approved_suo_lun_image_matches(
    decisions_path,
    review_data_path,
    *,
    products=None,
    skip_existing=True,
):
    decisions_payload = _load_json_file(decisions_path)
    review_rows = _load_review_data_rows(review_data_path)
    approved_skus = tuple(_approved_skus_from_decisions(decisions_payload))
    review_row_by_sku = {
        str(row.get("sku") or "").strip(): row
        for row in review_rows
        if str(row.get("sku") or "").strip()
    }
    product_by_sku = {
        product.sku: product
        for product in (products if products is not None else get_suo_lun_products())
    }

    matches = []
    missing_product_skus = []
    missing_review_data_skus = []
    missing_image_url_skus = []
    existing_image_skus = []

    for sku in approved_skus:
        row = review_row_by_sku.get(sku)
        if row is None:
            missing_review_data_skus.append(sku)
            continue

        product = product_by_sku.get(sku)
        if product is None:
            missing_product_skus.append(sku)
            continue

        if skip_existing and _product_has_images(product):
            existing_image_skus.append(sku)
            continue

        candidate_payload = row.get("candidate") or {}
        image_url = str(candidate_payload.get("image_url") or "").strip()
        if not image_url:
            missing_image_url_skus.append(sku)
            continue

        candidate = CrossMotorsSourceProduct(
            source_url=str(candidate_payload.get("source_url") or "").strip(),
            image_url=image_url,
            name=str(candidate_payload.get("name") or "").strip(),
            manufacturer=str(candidate_payload.get("manufacturer") or "").strip(),
            source_page_url=str(candidate_payload.get("source_page_url") or "").strip(),
            source_vehicle_label=str(
                candidate_payload.get("source_vehicle_label") or ""
            ).strip(),
            source_year_from=_parse_optional_int(candidate_payload.get("source_year_from")),
            source_year_to=_parse_optional_int(candidate_payload.get("source_year_to")),
            source_model_tokens=tuple(candidate_payload.get("source_model_tokens") or ()),
        )
        matches.append(
            SuoLunImageMatch(
                product=product,
                candidate=candidate,
                confidence="manual_approved",
                action="auto_import",
                reason="manual_review_approved",
                score=float(row.get("score") or 0),
                ambiguity_count=int(row.get("ambiguity_count") or 0),
            )
        )

    return ReviewApprovedSuoLunImageReport(
        matches=tuple(matches),
        approved_decision_count=len(approved_skus),
        missing_product_skus=tuple(missing_product_skus),
        missing_review_data_skus=tuple(missing_review_data_skus),
        missing_image_url_skus=tuple(missing_image_url_skus),
        existing_image_skus=tuple(existing_image_skus),
    )


def import_review_approved_suo_lun_images(
    matches,
    *,
    timeout=DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
    limit: int | None = None,
):
    return import_suo_lun_images(
        matches,
        timeout=timeout,
        session=session,
        limit=limit,
    )


def download_candidate_image(
    image_url,
    *,
    session: requests.Session | None = None,
    timeout=DEFAULT_TIMEOUT,
    headers=None,
):
    client = session or requests.Session()
    response = client.get(image_url, timeout=timeout, headers=headers or {})
    response.raise_for_status()
    content = response.content

    if not content:
        raise ValueError("Downloaded image is empty.")

    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Downloaded image is larger than allowed.")

    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("Downloaded file is not a valid image.") from exc

    filename = _filename_from_image_url(image_url, response.headers.get("Content-Type", ""))
    return content, filename


def attach_product_image(product, content, filename):
    images = attach_product_images(product, [(content, filename)])
    return images[0] if images else None


def attach_product_images(product, images):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product.pk)
        if product.images.exists():
            return tuple()

        max_sort_order = product.images.aggregate(Max("sort_order"))["sort_order__max"]
        created_images = []
        for index, (content, filename) in enumerate(images):
            product_image = ProductImage(
                product=product,
                is_primary=index == 0,
                sort_order=(max_sort_order or 0) + index + 1,
                alt_text=product.name,
            )
            product_image.image_original.save(filename, ContentFile(content), save=False)
            product_image.full_clean()
            product_image.save()
            created_images.append(product_image)

        return tuple(created_images)


def _load_external_candidate_rows(candidate_path):
    with open(candidate_path, encoding="utf-8") as candidate_file:
        payload = json.load(candidate_file)

    if isinstance(payload, list):
        return payload

    rows = []
    for key in ("auto_import", "review"):
        values = payload.get(key) or []
        for value in values:
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _load_json_file(path):
    with open(path, encoding="utf-8") as source_file:
        return json.load(source_file)


def _load_review_data_rows(path):
    text = Path(path).read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        return json.loads(text)

    match = re.search(
        r"window\.SUO_LUN_REVIEW_ITEMS\s*=\s*(\[.*\])\s*;?\s*$",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Review data file does not contain SUO_LUN_REVIEW_ITEMS.")
    return json.loads(match.group(1))


def _approved_skus_from_decisions(payload):
    decisions = payload.get("decisions") or {}
    for sku, decision in decisions.items():
        if isinstance(decision, dict) and decision.get("status") == "approved":
            cleaned_sku = str(sku or "").strip()
            if cleaned_sku:
                yield cleaned_sku


def _parse_optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_text(client, url, *, timeout, headers):
    response = client.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def _is_non_product_listing_page(url):
    path = urlparse(url).path.strip("/")
    return path in {"", "about", "contact"}


def _is_suo_lun_source_label(label):
    return _normalize_ascii(label) == _normalize_ascii(SOURCE_MANUFACTURER_LABEL)


def _split_aria_label(aria_label):
    cleaned = aria_label.removesuffix(" gallery").strip()
    parts = [part.strip() for part in re.split(r"\.\s+", cleaned) if part.strip()]
    if len(parts) <= 1:
        return cleaned, ""
    manufacturer = parts[-1]
    return ". ".join(parts[:-1]).strip(), manufacturer


def _rank_candidates(product, candidates):
    ranked = []
    for candidate in candidates:
        if not _vehicle_context_matches(product, candidate):
            continue

        side_quality = _side_match_quality(product, candidate)
        if side_quality == "mismatch":
            continue

        score = _token_score(candidate.name, product.name)
        exact_name = _normalize_loose(candidate.name) == _normalize_loose(product.name)
        if not exact_name and score < 0.82:
            continue

        ranked.append((candidate, score, exact_name, side_quality))

    return sorted(
        ranked,
        key=lambda item: (
            item[2],
            item[3] == "ok",
            item[1],
            -len(item[0].name),
        ),
        reverse=True,
    )


def _vehicle_context_matches(product, candidate):
    product_contexts = _product_vehicle_contexts(product)
    if not product_contexts:
        return False

    for context in product_contexts:
        if not _years_overlap(
            context["year_from"],
            context["year_to"],
            candidate.source_year_from,
            candidate.source_year_to,
        ):
            continue

        product_model_tokens = set(_tokenize(context["model"]))
        if any(token in product_model_tokens for token in candidate.source_model_tokens):
            return True

    return False


def _product_vehicle_contexts(product):
    contexts = []
    fitments = list(product.fitments.all())
    for fitment in fitments:
        contexts.append(
            {
                "make": fitment.vehicle_model.make.name,
                "model": fitment.vehicle_model.name,
                "year_from": fitment.year_from,
                "year_to": fitment.year_to,
            }
        )

    if contexts:
        return contexts

    parsed = _parse_vehicle_context_from_description(product.short_description)
    return [parsed] if parsed else []


def _parse_vehicle_context_from_description(description):
    parts = [part.strip() for part in str(description or "").split(" - ") if part.strip()]
    if len(parts) < 3:
        return None

    vehicle = " - ".join(parts[1:])
    year_from, year_to = _extract_year_range(vehicle)
    if not year_from or not year_to:
        return None

    tokens = _tokenize(vehicle)
    model_tokens = [
        token
        for token in tokens
        if token not in VEHICLE_MAKE_TOKENS and not _looks_like_year_token(token)
    ]
    if not model_tokens:
        return None

    return {
        "make": tokens[0] if tokens else "",
        "model": " ".join(model_tokens),
        "year_from": year_from,
        "year_to": year_to,
    }


def _side_match_quality(product, candidate):
    product_side = product.side or _extract_side(product.name)
    candidate_side = _extract_side(candidate.name)

    if product_side and candidate_side and product_side != candidate_side:
        return "mismatch"

    if product_side and not candidate_side:
        return "missing"

    return "ok"


def _extract_side(value):
    if SIDE_LEFT_RE.search(value or ""):
        return "left"
    if SIDE_RIGHT_RE.search(value or ""):
        return "right"
    return ""


def _product_has_images(product):
    images = getattr(product, "_prefetched_objects_cache", {}).get("images")
    if images is not None:
        return bool(images)
    return product.images.exists()


def _title_from_url(url):
    path = urlparse(url).path.strip("/")
    slug = path.split("/")[-1] if path else ""
    return unquote(slug).replace("-", " ").strip()


def _vehicle_model_tokens(value):
    tokens = []
    for token in _tokenize(value):
        if token in VEHICLE_MAKE_TOKENS:
            continue
        if _looks_like_year_token(token):
            continue
        if len(token) <= 1 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _extract_year_range(value):
    years = []
    for match in YEAR_RE.finditer(str(value or "")):
        raw = int(match.group(1))
        year = raw + 2000 if raw < 100 else raw
        if 2010 <= year <= 2035:
            years.append(year)

    if not years:
        return None, None

    if len(years) == 1:
        return years[0], DEFAULT_OPEN_ENDED_YEAR_TO

    return min(years), max(years)


def _years_overlap(first_from, first_to, second_from, second_to):
    if not all([first_from, first_to, second_from, second_to]):
        return False
    return max(first_from, second_from) <= min(first_to, second_to)


def _token_score(first, second):
    first_tokens = set(_tokenize(_normalize_loose(first)))
    second_tokens = set(_tokenize(_normalize_loose(second)))
    if not first_tokens or not second_tokens:
        return 0

    return len(first_tokens & second_tokens) / max(len(first_tokens), len(second_tokens))


def _tokenize(value):
    return tuple(token for token in _normalize(value).split() if token)


def _normalize(value):
    cleaned = _normalize_ascii(value)
    cleaned = NON_WORD_RE.sub(" ", cleaned)
    return SPACE_RE.sub(" ", cleaned).strip()


def _normalize_loose(value):
    tokens = [
        token
        for token in _tokenize(value)
        if token not in SOURCE_NOISE_TOKENS
    ]
    return " ".join(tokens)


def _normalize_ascii(value):
    return SPACE_RE.sub(" ", str(value or "").replace("\xa0", " ").lower()).strip()


def _looks_like_year_token(token):
    if not token.isdigit():
        return False
    if len(token) == 2:
        return 10 <= int(token) <= 35
    if len(token) == 4:
        return 2010 <= int(token) <= 2035
    return False


def _filename_from_image_url(image_url, content_type):
    path = urlparse(image_url).path
    basename = os.path.basename(path) or "suo-lun-product-image"
    stem, ext = os.path.splitext(basename)
    ext = ext.lower()

    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = _extension_from_content_type(content_type)

    return f"{stem or 'suo-lun-product-image'}{ext}"


def _extension_from_content_type(content_type):
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized == "image/png":
        return ".png"
    if normalized == "image/webp":
        return ".webp"
    return ".jpg"
