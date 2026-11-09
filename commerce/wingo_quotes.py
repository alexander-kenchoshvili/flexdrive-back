"""Standard-only signed quotes using local Wingo tariffs; no provider requests."""

from decimal import Decimal, ROUND_CEILING

from django.conf import settings
from django.core import signing

from .delivery_quote_data import (
    DeliveryQuoteError, contents_fingerprint, normalize_quote_items, delivery_order_fields,
)
from .wingo_locations import DeliveryLocation, delivery_cities, delivery_locations, resolve_delivery_location


QUOTE_SIGNING_SALT = "commerce.wingo.delivery-quote.v3"
STANDARD_TARIFF_BY_GROUP = {
    "tbilisi": "standardTbilisi", "tbilisiSuburbs": "tbilisiSurroundings",
    "standardRegion": "standardRegion", "mountainRegion": "highlandRegion",
}


def build_delivery_quote(*, source, items, region, city, client=None):
    if (not isinstance(region, DeliveryLocation) or not isinstance(city, DeliveryLocation)
            or region.region_id != city.region_id or region.external_id != city.external_id):
        raise DeliveryQuoteError("არჩეული რეგიონი და დასახლება არ ემთხვევა.", code="delivery_city_region_mismatch")
    if source not in {"cart", "buy_now"}:
        raise DeliveryQuoteError("შეკვეთის წყარო არასწორია.", code="delivery_quote_invalid")
    # Re-resolve instead of trusting a location object obtained before a refresh.
    location = resolve_delivery_location(region.region_id, city.external_id)
    normalized = normalize_quote_items(items)
    weight = sum((row["weight"] * row["quantity"] for row in normalized), Decimal(0)).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING)
    snapshot = location.snapshot
    band = next((row for row in snapshot.weight_ranges
                 if Decimal(row["min_weight"]) <= weight <= Decimal(row["max_weight"])), None)
    tariff = next((row for row in snapshot.tariffs if band and row["weight_range_id"] == band["id"]), None)
    key = STANDARD_TARIFF_BY_GROUP.get(location.group_type)
    try:
        amount = Decimal(tariff["prices"][key]) if tariff and not tariff["hidden"] and key else None
        if amount is None or not amount.is_finite() or amount <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise DeliveryQuoteError("ამ წონისა და დასახლების მიწოდების ფასი ვერ დადგინდა. დაგვიკავშირდით.",
                                 code="delivery_tariff_unavailable", status_code=503) from None
    payload = {
        "version": 3, "source": source, "provider": "wingo",
        "region_id": location.region_id, "region_name": location.region_name,
        "city_id": location.external_id, "city_name": location.name,
        "provider_region_id": location.provider_region_id, "provider_city_id": location.provider_city_id,
        "delivery_type_id": 1, "weight_range_id": band["id"],
        "service_slug": "standard", "tariff_revision": snapshot.revision,
        "carrier_delivery_cost": format(amount, ".2f"), "delivery_margin": "0.00",
        "customer_delivery_price": format(amount, ".2f"), "package_id": None,
        "measurements": {"weight": format(weight, ".2f"), "length": None, "width": None, "height": None},
        "contents_fingerprint": contents_fingerprint(normalized),
    }
    return {**payload, "quote_token": signing.dumps(payload, salt=QUOTE_SIGNING_SALT, compress=True)}


def validate_delivery_quote(*, quote_token, source, items, region, city):
    if not quote_token:
        raise DeliveryQuoteError("მიწოდების ფასი თავიდან გამოთვალეთ.", code="delivery_quote_required")
    try:
        payload = signing.loads(quote_token, salt=QUOTE_SIGNING_SALT, max_age=settings.DELIVERY_QUOTE_MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        raise DeliveryQuoteError("მიწოდების ფასს ვადა გაუვიდა. გამოთვალეთ თავიდან.", code="delivery_quote_expired") from None
    except signing.BadSignature:
        raise DeliveryQuoteError("მიწოდების ფასის მონაცემები არასწორია.", code="delivery_quote_invalid") from None
    current = build_delivery_quote(source=source, items=items, region=region, city=city)
    current.pop("quote_token")
    if payload != current:
        raise DeliveryQuoteError("კალათა, მისამართი ან ტარიფი შეიცვალა. მიწოდების ფასი თავიდან გამოთვალეთ.",
                                 code="delivery_quote_stale")
    return payload


def resolve_checkout_delivery(*, validated_data, source, items):
    location = resolve_delivery_location(validated_data.get("delivery_region_id"), validated_data.get("delivery_city_id"))
    return validate_delivery_quote(quote_token=validated_data.get("delivery_quote_token"), source=source,
                                   items=items, region=location, city=location)
