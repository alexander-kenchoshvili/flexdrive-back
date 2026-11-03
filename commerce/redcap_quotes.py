"""Signed RedCap quotes from stored tariffs; no checkout-time courier HTTP."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import hashlib
import json

from django.conf import settings
from django.core import signing

from .models import RedcapReferenceData
from .redcap import RedcapError, positive_decimal
from .redcap_references import tariff_price


QUOTE_SIGNING_SALT = "commerce.redcap.delivery-quote.v2"
STANDARD_SERVICE_BY_ZONE = {
    "city": "same_day", "suburban": "Dgesshemog", "region_city": "RegionCity",
    "region_village": "sofeli", "region_mountain": "Magalmtiani",
}


class DeliveryQuoteError(Exception):
    def __init__(self, detail, *, code="delivery_quote_failed", status_code=400):
        super().__init__(detail)
        self.detail, self.code, self.status_code = detail, code, status_code


@dataclass(frozen=True)
class DeliveryLocation:
    external_id: int
    name: str
    zone_slug: str
    snapshot: RedcapReferenceData
    is_internal_delivery: bool = False

    @property
    def pk(self):
        return self.external_id

    @property
    def region_id(self):
        return self.external_id


def delivery_locations():
    snapshot = RedcapReferenceData.objects.filter(pk=1).first()
    if snapshot is None:
        return []
    return [DeliveryLocation(row["id"], row["name"], row["zone_slug"], snapshot) for row in snapshot.locations]


def resolve_delivery_location(region_id, city_id):
    if region_id != city_id:
        raise DeliveryQuoteError("არჩეული საკურიერო ზონა არასწორია.", code="delivery_city_region_mismatch")
    location = next((row for row in delivery_locations() if row.external_id == region_id), None)
    if location is None:
        raise DeliveryQuoteError("მიწოდების ზონა ხელმისაწვდომი არ არის. სცადეთ ხელახლა.", code="delivery_location_unavailable")
    return location


def _normalize_items(items):
    result = []
    for item in items:
        try:
            weight = positive_decimal(item.product.effective_shipping_weight_kg)
            quantity = int(item.quantity)
            if quantity <= 0:
                raise ValueError
        except (RedcapError, TypeError, ValueError) as exc:
            raise DeliveryQuoteError("ერთ ან მეტ პროდუქტს შეფუთული წონა არ აქვს მითითებული.", code="shipping_weight_missing") from exc
        result.append({"product_id": item.product.pk, "quantity": quantity, "weight": weight})
    if not result:
        raise DeliveryQuoteError("კალათა ცარიელია.", code="delivery_items_empty")
    return result


def _fingerprint(items):
    content = [{**row, "weight": format(row["weight"], "f")} for row in sorted(items, key=lambda row: row["product_id"])]
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_delivery_quote(*, source, items, region, city, client=None):
    if not isinstance(region, DeliveryLocation) or region.external_id != city.external_id:
        raise DeliveryQuoteError("არჩეული საკურიერო ზონა არასწორია.", code="delivery_city_region_mismatch")
    normalized = _normalize_items(items)
    # Item units count once; parcel count never multiplies this total/tariff.
    weight = sum((row["weight"] * row["quantity"] for row in normalized), Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    service = STANDARD_SERVICE_BY_ZONE[region.zone_slug]
    try:
        amount = tariff_price(snapshot=region.snapshot, location_id=region.external_id, service=service, weight=weight)
    except RedcapError as exc:
        raise DeliveryQuoteError("ამ წონისა და ზონის მიწოდების ფასი ვერ დადგინდა. დაგვიკავშირდით.",
                                 code="delivery_tariff_unavailable", status_code=503) from exc
    payload = {
        "version": 2, "source": str(source), "provider": "redcap",
        "region_id": region.external_id, "region_name": region.name,
        "city_id": region.external_id, "city_name": region.name,
        "service_slug": service, "tariff_revision": region.snapshot.revision,
        "carrier_delivery_cost": format(amount, ".2f"), "delivery_margin": "0.00",
        "customer_delivery_price": format(amount, ".2f"), "package_id": None,
        "measurements": {"weight": format(weight, ".2f"), "length": None, "width": None, "height": None},
        "contents_fingerprint": _fingerprint(normalized),
    }
    return {**payload, "quote_token": signing.dumps(payload, salt=QUOTE_SIGNING_SALT, compress=True)}


def validate_delivery_quote(*, quote_token, source, items, region, city):
    if not quote_token:
        raise DeliveryQuoteError("მიწოდების ფასი თავიდან გამოთვალეთ.", code="delivery_quote_required")
    try:
        payload = signing.loads(quote_token, salt=QUOTE_SIGNING_SALT, max_age=settings.DELIVERY_QUOTE_MAX_AGE_SECONDS)
    except signing.SignatureExpired as exc:
        raise DeliveryQuoteError("მიწოდების ფასს ვადა გაუვიდა. გამოთვალეთ თავიდან.", code="delivery_quote_expired") from exc
    except signing.BadSignature as exc:
        raise DeliveryQuoteError("მიწოდების ფასის მონაცემები არასწორია.", code="delivery_quote_invalid") from exc
    current = build_delivery_quote(source=source, items=items, region=region, city=city)
    current.pop("quote_token")
    if not isinstance(payload, dict) or payload != current:
        raise DeliveryQuoteError("კალათა, ზონა ან ტარიფი შეიცვალა. მიწოდების ფასი თავიდან გამოთვალეთ.", code="delivery_quote_stale")
    return payload


def resolve_checkout_delivery(*, validated_data, source, items):
    location = resolve_delivery_location(validated_data.get("delivery_region_id"), validated_data.get("delivery_city_id"))
    return validate_delivery_quote(quote_token=validated_data.get("delivery_quote_token"), source=source,
                                   items=items, region=location, city=location)


def delivery_order_fields(payload):
    """Decode new quotes and frozen legacy bank snapshots without carrier HTTP."""
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
        raise DeliveryQuoteError("მიწოდების მონაცემების ვერსია არასწორია.", code="delivery_quote_invalid")
    measurements = payload["measurements"]
    result = {
        "delivery_provider": payload["provider"],
        "delivery_region_id": payload["region_id"], "delivery_region_name": payload["region_name"],
        "delivery_city_id": payload["city_id"], "delivery_city_name": payload["city_name"],
        "carrier_delivery_cost": Decimal(payload["carrier_delivery_cost"]),
        "delivery_margin": Decimal(payload["delivery_margin"]), "delivery_price": Decimal(payload["customer_delivery_price"]),
        "shipping_weight_kg": Decimal(measurements["weight"]), "delivery_package_id": payload.get("package_id"),
        **{f"shipping_{key}_cm": Decimal(measurements[key]) if measurements.get(key) is not None else None
           for key in ("length", "width", "height")},
    }
    if payload["version"] == 2:
        result["delivery_service_slug"] = payload["service_slug"]
        result["delivery_tariff_revision"] = payload["tariff_revision"]
    return result
