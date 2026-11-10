"""Signed Wingo service, price and schedule quotes; no provider requests."""

from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .delivery_quote_data import (
    DeliveryQuoteError, contents_fingerprint, normalize_quote_items, delivery_order_fields,
)
from .wingo_locations import DeliveryLocation, delivery_cities, delivery_locations, resolve_delivery_location
from .wingo_services import service_policy


QUOTE_SIGNING_SALT = "commerce.wingo.delivery-quote.v4"
LEGACY_QUOTE_SIGNING_SALT = "commerce.wingo.delivery-quote.v3"
STANDARD_TARIFF_BY_GROUP = {
    "tbilisi": "standardTbilisi", "tbilisiSuburbs": "tbilisiSurroundings",
    "standardRegion": "standardRegion", "mountainRegion": "highlandRegion",
}


def build_delivery_quote(*, source, items, region, city, client=None, service_slug="standard"):
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
    now = timezone.now()
    options = []
    for service in (["standard", "fast"] if location.group_type == "tbilisi" else ["standard"]):
        policy = service_policy(location.group_type, service, now=now)
        key = "fastTbilisi" if service == "fast" else STANDARD_TARIFF_BY_GROUP.get(location.group_type)
        try:
            amount = Decimal(tariff["prices"][key]) if tariff and not tariff["hidden"] and key else None
            if amount is None or not amount.is_finite() or amount <= 0:
                raise ValueError
        except (KeyError, TypeError, ValueError, ArithmeticError):
            amount = None
            policy.update(available=False, unavailable_reason="ამ მომსახურების ტარიფი ჯერ ხელმისაწვდომი არ არის.")
        options.append({**policy, "price": format(amount, ".2f") if amount is not None else None})
    selected = next((option for option in options if option["service_slug"] == service_slug), None)
    if selected is None or not selected["available"]:
        tariff_missing = selected is not None and selected["price"] is None
        raise DeliveryQuoteError(selected["unavailable_reason"] if selected else "მიწოდების არჩეული ტიპი ამ დასახლებაში მიუწვდომელია.",
                                 code="delivery_tariff_unavailable" if tariff_missing else "delivery_service_unavailable",
                                 status_code=503 if tariff_missing else 400)
    schedule = {key: selected[key] for key in ("estimated_delivery_date", "estimate_label", "booking_deadline_at", "checkout_deadline_at")}
    expires = now + timedelta(seconds=settings.DELIVERY_QUOTE_MAX_AGE_SECONDS)
    if selected["checkout_deadline_at"]:
        expires = min(expires, parse_datetime(selected["checkout_deadline_at"]))
    payload = {
        "version": 4, "source": source, "provider": "wingo",
        "region_id": location.region_id, "region_name": location.region_name,
        "city_id": location.external_id, "city_name": location.name,
        "provider_region_id": location.provider_region_id, "provider_city_id": location.provider_city_id,
        "delivery_type_id": selected["delivery_type_id"], "weight_range_id": band["id"],
        "service_slug": service_slug, "tariff_revision": snapshot.revision, "group_type": location.group_type,
        "carrier_delivery_cost": selected["price"], "delivery_margin": "0.00",
        "customer_delivery_price": selected["price"], "package_id": None,
        "measurements": {"weight": format(weight, ".2f"), "length": None, "width": None, "height": None},
        "contents_fingerprint": contents_fingerprint(normalized),
        "schedule": schedule, "expires_at": expires.isoformat(),
    }
    return {**payload, "options": options, "server_time": now.isoformat(),
            "quote_token": signing.dumps(payload, salt=QUOTE_SIGNING_SALT, compress=True)}


def validate_delivery_quote(*, quote_token, source, items, region, city, service_slug="standard"):
    if not quote_token:
        raise DeliveryQuoteError("მიწოდების ფასი თავიდან გამოთვალეთ.", code="delivery_quote_required")
    try:
        payload = signing.loads(quote_token, salt=QUOTE_SIGNING_SALT, max_age=settings.DELIVERY_QUOTE_MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        raise DeliveryQuoteError("მიწოდების ფასს ვადა გაუვიდა. გამოთვალეთ თავიდან.", code="delivery_quote_expired") from None
    except signing.BadSignature:
        try:
            payload = signing.loads(quote_token, salt=LEGACY_QUOTE_SIGNING_SALT, max_age=settings.DELIVERY_QUOTE_MAX_AGE_SECONDS)
        except signing.BadSignature:
            raise DeliveryQuoteError("მიწოდების ფასის მონაცემები არასწორია.", code="delivery_quote_invalid") from None
    if not isinstance(payload, dict) or payload.get("version") not in {3, 4} or payload.get("service_slug") != service_slug:
        raise DeliveryQuoteError("მიწოდების არჩევანი შეიცვალა. ფასი თავიდან გამოთვალეთ.", code="delivery_quote_stale")
    current = build_delivery_quote(source=source, items=items, region=region, city=city, service_slug=service_slug)
    for key in ("quote_token", "options", "server_time"):
        current.pop(key)
    comparison = dict(payload)
    if payload["version"] == 3:
        for key in ("schedule", "expires_at", "group_type"):
            current.pop(key)
        current["version"] = 3
    else:
        try:
            expires_at = parse_datetime(payload["expires_at"])
            if expires_at is None or timezone.is_naive(expires_at) or expires_at <= timezone.now():
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise DeliveryQuoteError("მიწოდების შეთავაზებას ვადა გაუვიდა. განაახლეთ არჩევანი.", code="delivery_quote_expired") from None
        comparison.pop("expires_at")
        current.pop("expires_at")
    if comparison != current:
        raise DeliveryQuoteError("კალათა, მისამართი ან ტარიფი შეიცვალა. მიწოდების ფასი თავიდან გამოთვალეთ.",
                                 code="delivery_quote_stale")
    return payload


def resolve_checkout_delivery(*, validated_data, source, items):
    location = resolve_delivery_location(validated_data.get("delivery_region_id"), validated_data.get("delivery_city_id"))
    return validate_delivery_quote(quote_token=validated_data.get("delivery_quote_token"), source=source,
                                   items=items, region=location, city=location,
                                   service_slug=validated_data.get("delivery_service_slug", "standard"))
