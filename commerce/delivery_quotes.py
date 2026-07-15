import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from django.conf import settings
from django.core import signing

from .models import EasywayCity, EasywayRegion
from .easyway import (
    EasywayClient,
    EasywayConfigurationError,
    EasywayResponseError,
    EasywayTransportError,
)


MONEY_QUANTUM = Decimal("0.01")
MEASUREMENT_QUANTUM = Decimal("0.01")
QUOTE_SIGNING_SALT = "commerce.easyway.delivery-quote.v1"


class DeliveryQuoteError(Exception):
    def __init__(self, detail, *, code="delivery_quote_failed", status_code=400):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code


def build_delivery_quote(*, source, items, region, city, client=None):
    normalized_items = _normalize_items(items)
    if city.region_id != region.pk:
        raise DeliveryQuoteError(
            "არჩეული ქალაქი მითითებულ რეგიონს არ ეკუთვნის.",
            code="delivery_city_region_mismatch",
        )

    measurements = _calculate_measurements(normalized_items)
    package_id = _positive_int_setting(
        "EASYWAY_STANDARD_PACKAGE_ID",
        settings.EASYWAY_STANDARD_PACKAGE_ID,
    )

    if region.is_internal_delivery:
        carrier_cost = Decimal("0.00")
        margin = Decimal("0.00")
        customer_price = _money_setting(
            "EASYWAY_INTERNAL_DELIVERY_PRICE_GEL",
            settings.EASYWAY_INTERNAL_DELIVERY_PRICE_GEL,
        )
        provider = "internal"
    else:
        sender_city_id = _positive_int_setting(
            "EASYWAY_SENDER_CITY_ID",
            settings.EASYWAY_SENDER_CITY_ID,
        )
        try:
            carrier_cost = (client or EasywayClient.from_settings()).get_shipping_price(
                **measurements,
                from_city_id=sender_city_id,
                to_city_id=city.external_id,
                package_id=package_id,
            )
        except EasywayConfigurationError as error:
            raise DeliveryQuoteError(
                "მიწოდების ფასის კონფიგურაცია დაუსრულებელია.",
                code="delivery_quote_configuration_error",
                status_code=503,
            ) from error
        except (EasywayTransportError, EasywayResponseError) as error:
            raise DeliveryQuoteError(
                "EasyWay-დან მიწოდების ფასი ვერ მივიღეთ. სცადეთ ხელახლა.",
                code="easyway_price_unavailable",
                status_code=503,
            ) from error
        margin = _money_setting(
            "EASYWAY_DELIVERY_MARGIN_GEL",
            settings.EASYWAY_DELIVERY_MARGIN_GEL,
        )
        customer_price = (carrier_cost + margin).quantize(MONEY_QUANTUM)
        provider = "easyway"

    payload = {
        "version": 1,
        "source": str(source),
        "provider": provider,
        "region_id": region.external_id,
        "region_name": region.name,
        "city_id": city.external_id,
        "city_name": city.name,
        "carrier_delivery_cost": _decimal_string(carrier_cost),
        "delivery_margin": _decimal_string(margin),
        "customer_delivery_price": _decimal_string(customer_price),
        "package_id": package_id,
        "measurements": {
            key: _decimal_string(value)
            for key, value in measurements.items()
        },
        "contents_fingerprint": _contents_fingerprint(normalized_items),
    }
    return {
        **payload,
        "quote_token": signing.dumps(
            payload,
            salt=QUOTE_SIGNING_SALT,
            compress=True,
        ),
    }


def validate_delivery_quote(*, quote_token, source, items, region, city):
    if not quote_token:
        raise DeliveryQuoteError(
            "მიწოდების ფასი თავიდან გამოთვალეთ.",
            code="delivery_quote_required",
        )
    try:
        payload = signing.loads(
            quote_token,
            salt=QUOTE_SIGNING_SALT,
            max_age=settings.EASYWAY_QUOTE_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as error:
        raise DeliveryQuoteError(
            "მიწოდების ფასს ვადა გაუვიდა. გამოთვალეთ თავიდან.",
            code="delivery_quote_expired",
        ) from error
    except signing.BadSignature as error:
        raise DeliveryQuoteError(
            "მიწოდების ფასის მონაცემები არასწორია.",
            code="delivery_quote_invalid",
        ) from error

    normalized_items = _normalize_items(items)
    expected = {
        "version": 1,
        "source": str(source),
        "region_id": region.external_id,
        "city_id": city.external_id,
        "contents_fingerprint": _contents_fingerprint(normalized_items),
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise DeliveryQuoteError(
            "კალათა ან მიწოდების მისამართი შეიცვალა. ფასი გამოთვალეთ თავიდან.",
            code="delivery_quote_stale",
        )

    try:
        customer_price = Decimal(str(payload["customer_delivery_price"]))
        carrier_cost = Decimal(str(payload["carrier_delivery_cost"]))
        margin = Decimal(str(payload["delivery_margin"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as error:
        raise DeliveryQuoteError(
            "მიწოდების ფასის მონაცემები არასწორია.",
            code="delivery_quote_invalid",
        ) from error
    if any(
        not value.is_finite() or value < Decimal("0.00")
        for value in (customer_price, carrier_cost, margin)
    ):
        raise DeliveryQuoteError(
            "მიწოდების ფასის მონაცემები არასწორია.",
            code="delivery_quote_invalid",
        )
    return payload


def resolve_checkout_delivery(*, validated_data, source, items):
    region = EasywayRegion.objects.filter(
        external_id=validated_data.get("delivery_region_id"),
        is_active=True,
    ).first()
    city = EasywayCity.objects.filter(
        external_id=validated_data.get("delivery_city_id"),
        region=region,
        is_active=True,
    ).first()
    if region is None or city is None:
        raise DeliveryQuoteError(
            "არჩეული მიწოდების მისამართი აღარ არის ხელმისაწვდომი.",
            code="delivery_location_unavailable",
        )
    payload = validate_delivery_quote(
        quote_token=validated_data.get("delivery_quote_token"),
        source=source,
        items=items,
        region=region,
        city=city,
    )
    return payload


def delivery_order_fields(payload):
    measurements = payload["measurements"]
    return {
        "delivery_provider": payload["provider"],
        "delivery_region_id": payload["region_id"],
        "delivery_region_name": payload["region_name"],
        "delivery_city_id": payload["city_id"],
        "delivery_city_name": payload["city_name"],
        "carrier_delivery_cost": Decimal(payload["carrier_delivery_cost"]),
        "delivery_margin": Decimal(payload["delivery_margin"]),
        "delivery_price": Decimal(payload["customer_delivery_price"]),
        "shipping_weight_kg": Decimal(measurements["weight"]),
        "shipping_length_cm": Decimal(measurements["length"]),
        "shipping_width_cm": Decimal(measurements["width"]),
        "shipping_height_cm": Decimal(measurements["height"]),
        "delivery_package_id": payload["package_id"],
    }


def _normalize_items(items):
    normalized = []
    for item in items:
        product = item.product
        quantity = int(item.quantity)
        measurements = {
            "weight": product.effective_shipping_weight_kg,
            "length": product.effective_shipping_length_cm,
            "width": product.effective_shipping_width_cm,
            "height": product.effective_shipping_height_cm,
        }
        if quantity <= 0 or any(value is None for value in measurements.values()):
            raise DeliveryQuoteError(
                "ერთ ან მეტ პროდუქტს მიწოდების ზომა/წონა არ აქვს მითითებული.",
                code="shipping_measurements_missing",
            )
        normalized.append(
            {
                "product_id": product.pk,
                "quantity": quantity,
                **{
                    key: Decimal(str(value))
                    for key, value in measurements.items()
                },
            }
        )
    if not normalized:
        raise DeliveryQuoteError("კალათა ცარიელია.", code="delivery_items_empty")
    return normalized


def _calculate_measurements(items):
    weight = sum(
        (item["weight"] * item["quantity"] for item in items),
        Decimal("0.00"),
    )
    length = max(item["length"] for item in items)
    width = max(item["width"] for item in items)
    total_volume = sum(
        (
            item["length"]
            * item["width"]
            * item["height"]
            * item["quantity"]
            for item in items
        ),
        Decimal("0.00"),
    )
    minimum_height = max(item["height"] for item in items)
    packed_height = total_volume / (length * width)
    height = max(minimum_height, packed_height)
    return {
        "length": length.quantize(MEASUREMENT_QUANTUM, rounding=ROUND_CEILING),
        "width": width.quantize(MEASUREMENT_QUANTUM, rounding=ROUND_CEILING),
        "height": height.quantize(MEASUREMENT_QUANTUM, rounding=ROUND_CEILING),
        "weight": weight.quantize(MEASUREMENT_QUANTUM, rounding=ROUND_CEILING),
    }


def _contents_fingerprint(items):
    value = [
        {
            key: (_decimal_string(raw) if isinstance(raw, Decimal) else raw)
            for key, raw in sorted(item.items())
        }
        for item in sorted(items, key=lambda row: row["product_id"])
    ]
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _money_setting(name, value):
    try:
        normalized = Decimal(str(value)).quantize(MONEY_QUANTUM)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise DeliveryQuoteError(
            f"{name} must be a non-negative money amount.",
            code="delivery_quote_configuration_error",
            status_code=503,
        ) from error
    if not normalized.is_finite() or normalized < Decimal("0.00"):
        raise DeliveryQuoteError(
            f"{name} must be a non-negative money amount.",
            code="delivery_quote_configuration_error",
            status_code=503,
        )
    return normalized


def _positive_int_setting(name, value):
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise DeliveryQuoteError(
            f"{name} must be a positive integer.",
            code="delivery_quote_configuration_error",
            status_code=503,
        ) from error
    if normalized <= 0:
        raise DeliveryQuoteError(
            f"{name} must be a positive integer.",
            code="delivery_quote_configuration_error",
            status_code=503,
        )
    return normalized


def _decimal_string(value):
    return format(Decimal(str(value)).quantize(MONEY_QUANTUM), ".2f")
