import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from PIL import Image

from catalog.models import Product
from catalog.suo_lun_image_import import attach_product_images


SUPPORTED_BACKUP_SCHEMA_VERSION = 6
SUPPORTED_IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


@dataclass(frozen=True)
class GalleryBackupImage:
    reference: str
    path: Path
    is_main: bool


@dataclass(frozen=True)
class GalleryBackupMatch:
    product: Product
    images: tuple[GalleryBackupImage, ...]


@dataclass(frozen=True)
class GalleryBackupReport:
    schema_version: int
    approved_count: int
    approved_image_count: int
    matches: tuple[GalleryBackupMatch, ...]
    missing_product_skus: tuple[str, ...]
    missing_html_skus: tuple[str, ...]
    no_image_skus: tuple[str, ...]
    existing_image_skus: tuple[str, ...]
    missing_file_entries: tuple[str, ...]
    invalid_path_entries: tuple[str, ...]
    invalid_image_entries: tuple[str, ...]
    ignored_remote_entries: tuple[str, ...]
    inconsistent_main_skus: tuple[str, ...]

    @property
    def ready_product_count(self):
        return len(self.matches)

    @property
    def ready_image_count(self):
        return sum(len(match.images) for match in self.matches)

    @property
    def has_blockers(self):
        return any(
            (
                self.missing_product_skus,
                self.missing_html_skus,
                self.no_image_skus,
                self.missing_file_entries,
                self.invalid_path_entries,
                self.invalid_image_entries,
                self.inconsistent_main_skus,
            )
        )


@dataclass(frozen=True)
class GalleryBackupImportResult:
    attempted_products: int
    imported_products: int
    imported_images: int
    skipped_products: int
    errors: tuple[str, ...]


class _ReviewGalleryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.galleries = {}
        self._in_card = False
        self._in_sku = False
        self._in_gallery = False
        self._gallery_depth = 0
        self._sku_chunks = []
        self._image_sources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())

        if tag == "article" and "card" in classes:
            self._in_card = True
            self._in_sku = False
            self._in_gallery = False
            self._gallery_depth = 0
            self._sku_chunks = []
            self._image_sources = []
            return

        if not self._in_card:
            return

        if tag == "b" and not self._sku_chunks:
            self._in_sku = True
            return

        if tag == "section":
            if self._in_gallery:
                self._gallery_depth += 1
            elif "gallery" in classes:
                self._in_gallery = True
                self._gallery_depth = 1
            return

        if tag == "img" and self._in_gallery:
            source = str(attributes.get("src") or "").strip()
            if source:
                self._image_sources.append(source)

    def handle_endtag(self, tag):
        if not self._in_card:
            return

        if tag == "b" and self._in_sku:
            self._in_sku = False
            return

        if tag == "section" and self._in_gallery:
            self._gallery_depth -= 1
            if self._gallery_depth <= 0:
                self._in_gallery = False
                self._gallery_depth = 0
            return

        if tag == "article":
            sku = "".join(self._sku_chunks).strip()
            if sku:
                self.galleries[sku] = tuple(self._image_sources)
            self._in_card = False
            self._in_sku = False
            self._in_gallery = False
            self._gallery_depth = 0

    def handle_data(self, data):
        if self._in_card and self._in_sku:
            self._sku_chunks.append(data)


def load_review_html_galleries(html_path):
    parser = _ReviewGalleryParser()
    parser.feed(Path(html_path).read_text(encoding="utf-8"))
    return parser.galleries


def build_gallery_backup_report(
    backup_path,
    html_path,
    assets_dir,
    *,
    products=None,
    skip_existing=True,
):
    backup = _load_backup(backup_path)
    schema_version = int(backup.get("schemaVersion") or 0)
    if schema_version < SUPPORTED_BACKUP_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported review backup schemaVersion "
            f"{schema_version}; expected {SUPPORTED_BACKUP_SCHEMA_VERSION} or newer."
        )

    statuses = _object_map(backup.get("statuses"))
    approved_skus = tuple(
        str(sku).strip()
        for sku, status in statuses.items()
        if str(status).strip() == "approved" and str(sku).strip()
    )
    galleries = load_review_html_galleries(html_path)
    assets_full = Path(assets_dir).resolve()
    if not assets_full.is_dir():
        raise ValueError(f"Assets directory not found: {assets_full}")

    product_rows = (
        list(products)
        if products is not None
        else list(
            Product.objects.filter(sku__in=approved_skus).prefetch_related("images")
        )
    )
    product_by_sku = {product.sku: product for product in product_rows}

    deleted_map = _object_map(backup.get("deletedImgs"))
    manual_map = _object_map(backup.get("manualImgs"))
    added_map = _object_map(backup.get("addedImgs"))
    main_map = _object_map(backup.get("mainImgs"))

    matches = []
    missing_product_skus = []
    missing_html_skus = []
    no_image_skus = []
    existing_image_skus = []
    missing_file_entries = []
    invalid_path_entries = []
    invalid_image_entries = []
    ignored_remote_entries = []
    inconsistent_main_skus = []
    approved_image_count = 0

    for sku in approved_skus:
        if sku not in galleries:
            missing_html_skus.append(sku)

        deleted = {
            _normalize_reference(value)
            for value in _list_value(deleted_map.get(sku))
            if _normalize_reference(value)
        }
        main_reference = _normalize_reference(main_map.get(sku))
        references = []
        references.extend(galleries.get(sku, ()))
        references.extend(_entry_urls(manual_map.get(sku)))
        references.extend(_entry_urls(added_map.get(sku)))

        images = []
        seen_paths = set()
        for raw_reference in references:
            reference = _normalize_reference(raw_reference)
            if not reference or reference in deleted:
                continue

            resolution = _resolve_local_image(reference, assets_full)
            if resolution["remote"]:
                entry = f"{sku}: {reference}"
                if entry not in ignored_remote_entries:
                    ignored_remote_entries.append(entry)
                continue
            if resolution["error"]:
                entry = f"{sku}: {reference} ({resolution['error']})"
                if entry not in invalid_path_entries:
                    invalid_path_entries.append(entry)
                continue

            image_path = resolution["path"]
            path_key = str(image_path).casefold()
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)

            if not image_path.is_file():
                missing_file_entries.append(f"{sku}: {reference}")
                continue
            if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                invalid_image_entries.append(
                    f"{sku}: {reference} (unsupported extension)"
                )
                continue
            try:
                with Image.open(image_path) as image:
                    image.verify()
            except Exception as exc:
                invalid_image_entries.append(
                    f"{sku}: {reference} ({type(exc).__name__})"
                )
                continue

            images.append(
                GalleryBackupImage(
                    reference=reference,
                    path=image_path,
                    is_main=bool(main_reference and reference == main_reference),
                )
            )

        if main_reference and not any(image.is_main for image in images):
            inconsistent_main_skus.append(sku)

        if images:
            images.sort(key=lambda image: not image.is_main)
            approved_image_count += len(images)
        else:
            no_image_skus.append(sku)

        product = product_by_sku.get(sku)
        if product is None:
            missing_product_skus.append(sku)
            continue
        if skip_existing and _product_has_images(product):
            existing_image_skus.append(sku)
            continue
        if images:
            matches.append(GalleryBackupMatch(product=product, images=tuple(images)))

    return GalleryBackupReport(
        schema_version=schema_version,
        approved_count=len(approved_skus),
        approved_image_count=approved_image_count,
        matches=tuple(matches),
        missing_product_skus=tuple(missing_product_skus),
        missing_html_skus=tuple(missing_html_skus),
        no_image_skus=tuple(no_image_skus),
        existing_image_skus=tuple(existing_image_skus),
        missing_file_entries=tuple(missing_file_entries),
        invalid_path_entries=tuple(invalid_path_entries),
        invalid_image_entries=tuple(invalid_image_entries),
        ignored_remote_entries=tuple(ignored_remote_entries),
        inconsistent_main_skus=tuple(inconsistent_main_skus),
    )


def import_gallery_backup_matches(matches, *, limit=None):
    attempted_products = 0
    imported_products = 0
    imported_images = 0
    skipped_products = 0
    errors = []

    for match in matches:
        if limit is not None and attempted_products >= limit:
            break
        attempted_products += 1

        try:
            payload = [
                (image.path.read_bytes(), image.path.name) for image in match.images
            ]
            created = attach_product_images(match.product, payload)
            if not created:
                skipped_products += 1
                continue
            imported_products += 1
            imported_images += len(created)
        except Exception as exc:
            errors.append(f"{match.product.sku}: {exc}")

    return GalleryBackupImportResult(
        attempted_products=attempted_products,
        imported_products=imported_products,
        imported_images=imported_images,
        skipped_products=skipped_products,
        errors=tuple(errors),
    )


def _load_backup(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Review backup must be a JSON object.")
    return payload


def _object_map(value):
    return value if isinstance(value, dict) else {}


def _list_value(value):
    return value if isinstance(value, list) else []


def _entry_urls(value):
    urls = []
    for entry in _list_value(value):
        if isinstance(entry, dict):
            url = entry.get("url")
        else:
            url = entry
        if str(url or "").strip():
            urls.append(str(url).strip())
    return urls


def _normalize_reference(value):
    return str(value or "").strip().replace("\\", "/")


def _resolve_local_image(reference, assets_full):
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme.lower() in {"http", "https"}:
            return {"path": None, "remote": True, "error": ""}
        return {
            "path": None,
            "remote": False,
            "error": f"unsupported scheme {parsed.scheme or 'unknown'}",
        }

    decoded_path = unquote(parsed.path).replace("\\", "/")
    pure_path = PurePosixPath(decoded_path)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        return {"path": None, "remote": False, "error": "unsafe path"}

    parts = list(pure_path.parts)
    if parts and parts[0].casefold() == assets_full.name.casefold():
        parts = parts[1:]
    if not parts:
        return {"path": None, "remote": False, "error": "empty path"}

    candidate = assets_full.joinpath(*parts).resolve()
    if not candidate.is_relative_to(assets_full):
        return {"path": None, "remote": False, "error": "path escapes assets directory"}
    return {"path": candidate, "remote": False, "error": ""}


def _product_has_images(product):
    prefetched = getattr(product, "_prefetched_objects_cache", {}).get("images")
    if prefetched is not None:
        return bool(prefetched)
    return product.images.exists()
