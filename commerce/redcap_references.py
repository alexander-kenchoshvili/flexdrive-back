"""Manual reference synchronization and pure local, weight-based tariff selection."""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import RedcapReferenceData
from .redcap import RedcapClient, RedcapConfigurationError, RedcapError, RedcapResponseError, STANDARD_SERVICES, positive_decimal


ZONE_SERVICES = {
    "city": ("same_day", "next_day"),
    "suburban": ("Dgesshemog", "KHVshemog"),
    "region_city": ("RegionCity",),
    "region_village": ("sofeli",),
    "region_mountain": ("Magalmtiani",),
}
SERVICE_LABELS = {
    "same_day": "თბილისი — იმავე დღის ტიპი",
    "next_day": "თბილისი — მომდევნო დღის ტიპი",
    "Dgesshemog": "შემოგარენი — იმავე დღის ტიპი",
    "KHVshemog": "შემოგარენი — მომდევნო დღის ტიპი",
    "RegionCity": "რეგიონი — ქალაქები",
    "sofeli": "რეგიონი — სოფლები",
    "Magalmtiani": "რეგიონი — მაღალმთიანი",
}


def _invalid():
    raise RedcapResponseError(status_code=200)


def _text(value, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _invalid()
    return value.strip()


def _rows(payload, name, maximum=1000):
    if not isinstance(payload, dict) or payload.get("success") is not True:
        _invalid()
    rows = payload.get(name)
    if not isinstance(rows, list) or not 1 <= len(rows) <= maximum:
        _invalid()
    if any(not isinstance(row, dict) for row in rows):
        _invalid()
    return rows


def _number(value, *, money=False):
    try:
        if isinstance(value, bool):
            _invalid()
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal("9999999999.99"):
            _invalid()
        if money and number != number.quantize(Decimal("0.01")):
            _invalid()
        return number
    except (InvalidOperation, ValueError, TypeError):
        _invalid()


def normalize_weights(payload):
    rows = _rows(payload, "weights")
    result = []
    previous_end = Decimal(0)
    for row in rows:
        lower, upper = _number(row.get("from")), _number(row.get("to"))
        if lower != previous_end or upper <= lower or not isinstance(row.get("prices"), dict):
            _invalid()
        prices = {}
        for service in sorted(STANDARD_SERVICES):
            price = _number(row["prices"].get(service), money=True)
            # Out-of-scope zero-priced entries such as 3hour are discarded. A
            # zero/missing standard tariff is not treated as free delivery.
            if price <= 0:
                _invalid()
            prices[service] = format(price, ".2f")
        result.append({"from": str(lower), "to": str(upper), "prices": prices})
        previous_end = upper
    return result


def normalize_locations(payload):
    rows = _rows(payload, "locations", maximum=100)
    result, ids, zones, names = [], set(), set(), set()
    for row in rows:
        external_id, zone = row.get("id"), row.get("zone_slug")
        name = _text(row.get("name"), 160)
        if (type(external_id) is not int or external_id <= 0 or external_id in ids
                or zone not in ZONE_SERVICES or zone in zones or name in names
                or row.get("type") not in {"city", "region", "village"}):
            _invalid()
        result.append({"id": external_id, "name": name, "type": row["type"],
                       "zone": _text(row.get("zone"), 160), "zone_slug": zone})
        ids.add(external_id)
        zones.add(zone)
        names.add(name)
    if zones != set(ZONE_SERVICES):
        _invalid()
    return sorted(result, key=lambda row: row["id"])


def normalize_statuses(payload):
    result, keys = [], set()
    for row in _rows(payload, "statuses", maximum=100):
        key = _text(row.get("key"), 80)
        if (key in keys or type(row.get("is_final")) is not bool
                or type(row.get("can_cancel")) is not bool):
            _invalid()
        keys.add(key)
        result.append({"key": key, "name": _text(row.get("name"), 160),
                       "is_final": row["is_final"], "can_cancel": row["can_cancel"]})
    return sorted(result, key=lambda row: row["key"])


def normalize_payment_options(payload):
    result = {}
    for field, needed in (("payment_types", "transfer"), ("delivery_payers", "sender")):
        values = []
        keys = set()
        for row in _rows(payload, field, maximum=20):
            key = _text(row.get("key"), 40)
            if key in keys:
                _invalid()
            keys.add(key)
            values.append({"key": key, "name": _text(row.get("name"), 160)})
        if needed not in keys:
            _invalid()
        result[field] = sorted(values, key=lambda row: row["key"])
    # Carrier COD availability does not enable COD in FlexDrive.
    return result


def refresh_redcap_references(*, client=None):
    client = client or RedcapClient.from_settings()
    revision_before = RedcapReferenceData.objects.filter(pk=1).values_list("revision", flat=True).first()
    # Fetch and validate everything before touching the database. Network calls
    # are outside transactions and row locks.
    weight_payload = client.get_weight_options()
    data = {
        "category": _text(weight_payload.get("category")) if isinstance(weight_payload, dict) else _invalid(),
        "weights": normalize_weights(weight_payload),
        "locations": normalize_locations(client.get_locations()),
        "statuses": normalize_statuses(client.get_statuses()),
        "payment_options": normalize_payment_options(client.get_payment_options()),
    }
    revision = hashlib.sha256(json.dumps(data, ensure_ascii=True, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    with transaction.atomic():
        snapshot, created = RedcapReferenceData.objects.get_or_create(
            pk=1, defaults={**data, "revision": revision, "synced_at": timezone.now()},
        )
        snapshot = RedcapReferenceData.objects.select_for_update().get(pk=snapshot.pk)
        if not created and snapshot.revision not in {revision_before, revision}:
            raise RedcapError("სხვა განახლება უკვე დასრულდა. მიმდინარე ცხრილი შენარჩუნდა; გადაამოწმეთ შედეგი.")
        for key, value in data.items():
            setattr(snapshot, key, value)
        snapshot.revision = revision
        snapshot.synced_at = timezone.now()
        snapshot.save()
    return snapshot


def tariff_price(*, snapshot, location_id, service, weight):
    """Select a stored tariff; does not choose a date, package count or service.

    Verified boundary examples: 5 kg stays in 0–5; 5.01 moves to 5–10;
    10 stays in 5–10; 10.01 moves to 10–15. Amounts include carrier VAT.
    """
    if type(location_id) is not int:
        raise RedcapConfigurationError("RedCap-ის ზონა არასწორია.")
    location = next((row for row in snapshot.locations if row["id"] == location_id), None)
    if location is None or service not in ZONE_SERVICES.get(location["zone_slug"], ()):
        raise RedcapConfigurationError("მიწოდების ტიპი არჩეულ ზონას არ შეესაბამება.")
    weight = positive_decimal(weight)
    rows = normalize_weights({"success": True, "weights": snapshot.weights})
    for row in rows:
        if Decimal(row["from"]) < weight <= Decimal(row["to"]):
            return Decimal(row["prices"][service])
    raise RedcapConfigurationError("ამ წონისთვის RedCap-ის ტარიფი არ არის შენახული.")
