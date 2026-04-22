from urllib.parse import urlparse


def empty_image_asset():
    return {
        "desktop": None,
        "tablet": None,
        "mobile": None,
        "alt_text": "",
    }


def _safe_file_url(file_field):
    if not file_field:
        return None

    try:
        return file_field.url
    except ValueError:
        return None


def resolve_primary_product_image(product):
    images = list(product.images.all())
    if not images:
        return None

    primary = next((image for image in images if image.is_primary), None)
    return primary or images[0]


def build_product_primary_image_snapshot(product):
    primary = resolve_primary_product_image(product)
    if not primary:
        return empty_image_asset()

    return {
        "desktop": _safe_file_url(primary.desktop_image),
        "tablet": _safe_file_url(primary.tablet_image),
        "mobile": _safe_file_url(primary.mobile_image),
        "alt_text": primary.alt_text,
    }


def serialize_image_asset(asset, request=None):
    asset = asset or {}
    return {
        "desktop": _normalize_image_url(asset.get("desktop"), request=request),
        "tablet": _normalize_image_url(asset.get("tablet"), request=request),
        "mobile": _normalize_image_url(asset.get("mobile"), request=request),
        "alt_text": asset.get("alt_text", "") or "",
    }


def _normalize_image_url(value, *, request=None):
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme or value.startswith("//"):
        return value

    if request is None:
        return value

    return request.build_absolute_uri(value)
