"""Validate a complete Wingo reference set before replacing the private snapshot."""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import WingoReferenceData
from .wingo import WingoClient, WingoError, WingoResponseError


TARIFF_LABELS = {
    "fastTbilisi": "თბილისი — სწრაფი",
    "standardTbilisi": "თბილისი — სტანდარტული",
    "tbilisiSurroundings": "თბილისის შემოგარენი",
    "standardRegion": "რეგიონი",
    "highlandRegion": "მაღალმთიანი რეგიონი",
}
LOCALITY_GROUPS = frozenset({"tbilisi", "tbilisiSuburbs", "standardRegion", "mountainRegion"})
WEEKDAYS = {
    "monday": "ორშაბათი", "tuesday": "სამშაბათი", "wednesday": "ოთხშაბათი",
    "thursday": "ხუთშაბათი", "friday": "პარასკევი", "saturday": "შაბათი", "sunday": "კვირა",
}


def _invalid():
    raise WingoResponseError()


def _text(value, maximum=200):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        _invalid()
    return value.strip()


def _rows(value, maximum=20000, *, empty=False):
    if (not isinstance(value, list) or len(value) > maximum or (not empty and not value)
            or any(not isinstance(row, dict) for row in value)):
        _invalid()
    return value


def _positive_id(value):
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 10:
        value = int(value)
    if type(value) is not int or not 0 < value <= 2147483647:
        _invalid()
    return value


def _boolean(value):
    if type(value) is not bool:
        _invalid()
    return value


def _decimal(value, *, positive=False):
    try:
        if isinstance(value, bool):
            _invalid()
        number = Decimal(str(value))
        if (not number.is_finite() or number < 0 or number > Decimal("9999999999.99")
                or number != number.quantize(Decimal("0.01")) or (positive and number <= 0)):
            _invalid()
    except (InvalidOperation, TypeError, ValueError):
        _invalid()
    return number


def normalize_regions(payload):
    if not isinstance(payload, dict):
        _invalid()
    result, ids, names = [], set(), set()
    for row in _rows(payload.get("regions"), maximum=100):
        identifier, name = _text(row.get("id")), _text(row.get("nameGe"))
        if identifier in ids or name in names:
            _invalid()
        result.append({"id": identifier, "name": name})
        ids.add(identifier)
        names.add(name)
    return sorted(result, key=lambda row: row["id"])


def normalize_localities(payload, regions, client):
    by_name = {region["name"]: region["id"] for region in regions}
    expected = {}
    for row in _rows(payload.get("localities")):
        identifier, region_name = _text(row.get("id")), _text(row.get("regionGe"))
        if identifier in expected or region_name not in by_name:
            _invalid()
        expected[identifier] = (by_name[region_name], _text(row.get("nameGe"), 500))
    result, seen = [], set()
    for region in regions:
        for row in _rows(client.get_localities(region["name"]), empty=True):
            identifier = _text(row.get("id"))
            name = _text(row.get("nameGe"), 500)
            group = row.get("groupType")
            if (identifier in seen or row.get("regionGe") != region["name"]
                    or expected.get(identifier) != (region["id"], name)
                    or not isinstance(group, str) or group not in LOCALITY_GROUPS):
                _invalid()
            address_required = row.get("addressRequired")
            if address_required is not None:
                _boolean(address_required)
            result.append({
                "id": identifier, "region_id": region["id"], "name": name,
                "locality_name": _text(row.get("localityGe"), 500),
                "group_type": group, "active": _boolean(row.get("active")),
                "operational": _boolean(row.get("operational")),
                "delivery_days": [day for day in WEEKDAYS if _boolean(row.get(day))],
                "address_required": address_required,
            })
            seen.add(identifier)
    if seen != set(expected):
        _invalid()
    return sorted(result, key=lambda row: row["id"])


def normalize_weight_ranges(payload):
    result, ids = [], set()
    for row in _rows(payload, maximum=1000):
        identifier = _positive_id(row.get("id"))
        if "weightRangeId" in row and _positive_id(row["weightRangeId"]) != identifier:
            _invalid()
        lower, upper = _decimal(row.get("minWeight")), _decimal(row.get("maxWeight"), positive=True)
        if identifier in ids or upper <= lower:
            _invalid()
        ids.add(identifier)
        result.append({"id": identifier, "min_weight": format(lower, ".2f"), "max_weight": format(upper, ".2f")})
    result.sort(key=lambda row: Decimal(row["min_weight"]))
    previous = None
    for row in result:
        lower = Decimal(row["min_weight"])
        if (previous is None and lower != 0) or (previous is not None and lower != previous + Decimal("0.01")):
            _invalid()
        previous = Decimal(row["max_weight"])
    return result


def normalize_delivery_types(payload):
    result, ids = [], set()
    for row in _rows(payload, maximum=100):
        identifier = _positive_id(row.get("id"))
        if identifier in ids:
            _invalid()
        result.append({"id": identifier, "name": _text(row.get("nameGe"))})
        ids.add(identifier)
    if not {1, 2}.issubset(ids):
        _invalid()
    return sorted(result, key=lambda row: row["id"])


def normalize_tariffs(payload, weights):
    expected = {row["id"]: row for row in weights}
    result, seen = [], set()
    for row in _rows(payload, maximum=1000):
        identifier = _positive_id(row.get("weightRangeId"))
        if identifier in seen or identifier not in expected:
            _invalid()
        weight = expected[identifier]
        if (_decimal(row.get("minWeight")) != Decimal(weight["min_weight"])
                or _decimal(row.get("maxWeight")) != Decimal(weight["max_weight"])):
            _invalid()
        result.append({
            "weight_range_id": identifier,
            "prices": {key: format(_decimal(row.get(key), positive=True), ".2f") for key in TARIFF_LABELS},
            "is_custom": _boolean(row.get("isCustom")), "hidden": _boolean(row.get("hidden")),
        })
        seen.add(identifier)
    if seen != set(expected):
        _invalid()
    by_id = {row["weight_range_id"]: row for row in result}
    return [by_id[weight["id"]] for weight in weights]


def refresh_wingo_references(*, client=None):
    client = client or WingoClient.from_settings()
    before = WingoReferenceData.objects.filter(pk=1).values_list("revision", "synced_at").first()
    # No database lock or transaction is held while Wingo is being contacted.
    payload = client.get_regions()
    regions = normalize_regions(payload)
    weights = normalize_weight_ranges(client.get_weight_ranges())
    data = {
        "account_mode": client.account_mode, "api_base_url": client.api_base_url,
        "regions": regions, "weight_ranges": weights,
        "delivery_types": normalize_delivery_types(client.get_delivery_types()),
        "tariffs": normalize_tariffs(client.get_merchant_tariffs(), weights),
        "localities": normalize_localities(payload, regions, client),
    }
    revision = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True,
                                        separators=(",", ":")).encode()).hexdigest()
    with transaction.atomic():
        snapshot, created = WingoReferenceData.objects.get_or_create(
            pk=1, defaults={**data, "revision": revision, "synced_at": timezone.now()},
        )
        snapshot = WingoReferenceData.objects.select_for_update().get(pk=1)
        if not created and (snapshot.revision, snapshot.synced_at) != before:
            raise WingoError("სხვა განახლება უკვე დასრულდა. მიმდინარე Wingo-ს ცხრილი შენარჩუნდა; გადაამოწმეთ შედეგი.")
        for field, value in data.items():
            setattr(snapshot, field, value)
        snapshot.revision = revision
        snapshot.synced_at = timezone.now()
        snapshot.save()
        from .wingo_locations import synchronize_location_ids
        synchronize_location_ids(snapshot)
    return snapshot
