"""Provider-independent quote values and decoding of frozen payment snapshots."""

from decimal import Decimal, InvalidOperation
import hashlib
import json


class DeliveryQuoteError(Exception):
    def __init__(self, detail, *, code="delivery_quote_failed", status_code=400):
        super().__init__(detail)
        self.detail, self.code, self.status_code = detail, code, status_code


def normalize_quote_items(items):
    result = []
    for item in items:
        try:
            raw_weight = item.product.effective_shipping_weight_kg
            weight = Decimal(str(raw_weight))
            quantity = int(item.quantity)
            if (isinstance(raw_weight, bool) or not weight.is_finite() or weight <= 0
                    or isinstance(item.quantity, bool) or quantity <= 0
                    or Decimal(str(item.quantity)) != quantity):
                raise ValueError
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            raise DeliveryQuoteError("ერთ ან მეტ პროდუქტს შეფუთული წონა ან რაოდენობა არასწორად აქვს მითითებული.",
                                     code="shipping_weight_missing") from None
        result.append({"product_id": item.product.pk, "quantity": quantity, "weight": weight})
    if not result:
        raise DeliveryQuoteError("კალათა ცარიელია.", code="delivery_items_empty")
    return result


def contents_fingerprint(items):
    content = [{**row, "weight": format(row["weight"], "f")} for row in sorted(items, key=lambda row: row["product_id"])]
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def delivery_order_fields(payload):
    """Decode already-verified, frozen payment data without current tariff lookups."""
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2, 3}:
        raise DeliveryQuoteError("მიწოდების მონაცემების ვერსია არასწორია.", code="delivery_quote_invalid")
    if payload["version"] == 3:
        if (payload.get("provider") != "wingo" or type(payload.get("delivery_type_id")) is not int
                or payload["delivery_type_id"] != 1 or payload.get("service_slug") != "standard"
                or type(payload.get("weight_range_id")) is not int or payload["weight_range_id"] <= 0
                or any(not isinstance(payload.get(key), str) or not payload[key] or len(payload[key]) > 200
                       for key in ("provider_region_id", "provider_city_id"))):
            raise DeliveryQuoteError("მიწოდების მონაცემები არასწორია.", code="delivery_quote_invalid")
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
    if payload["version"] in {2, 3}:
        result["delivery_service_slug"] = payload["service_slug"]
        result["delivery_tariff_revision"] = payload["tariff_revision"]
    if payload["version"] == 3:
        result["delivery_provider_data"] = {
            "region_id": payload["provider_region_id"], "locality_id": payload["provider_city_id"],
            "delivery_type_id": 1, "weight_range_id": payload["weight_range_id"],
        }
    return result
