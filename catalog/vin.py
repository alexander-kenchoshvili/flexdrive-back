"""Conservative vPIC identification; saved product fitments remain authoritative.

VINs are never logged/persisted; cache keys are hashes. Cache only normalized
vehicle identity, and resolve against the current internal taxonomy every time.
"""
import hashlib
import json
import re
import unicodedata

import requests
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from .models import ProductFitment, ProductStatus, VehicleMake, VehicleModel


VIN_PATTERN = re.compile(r"[A-HJ-NPR-Z0-9]{17}", re.ASCII)
PROVIDER_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"


def normalize_vin(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.isascii():
        return None
    value = value.upper()
    return value if VIN_PATTERN.fullmatch(value) else None


def _key(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


def _read_provider(vin):
    # Fixed host, strict path, bounded time/body, no redirects/retries or secrets.
    with requests.get(
        PROVIDER_BASE + vin, params={"format": "json"},
        timeout=(3.05, 6), allow_redirects=False, stream=True,
        headers={"Accept": "application/json"},
    ) as response:
        if response.status_code != 200:
            raise ValueError("provider unavailable")
        body = bytearray()
        for chunk in response.iter_content(16384):
            body.extend(chunk)
            if len(body) > 262144:
                raise ValueError("provider response too large")
    payload = json.loads(body)
    results = payload.get("Results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise ValueError("invalid provider response")
    row = results[0]
    if row.get("VIN") != vin:
        raise ValueError("unexpected provider result")
    # HTTP 200 can carry partial/incorrect decodes, including wrong check digits.
    # Never silently substitute SuggestedVIN or auto-select from warning data.
    if str(row.get("ErrorCode", "")).strip() != "0":
        return {"status": "unrecognized"}
    make, model, year = row.get("Make"), row.get("Model"), row.get("ModelYear")
    if not all(isinstance(v, str) and v.strip() and len(v) <= 120 and not any(ord(c) < 32 for c in v) for v in (make, model)):
        raise ValueError("missing vehicle identity")
    if not isinstance(year, str) or not re.fullmatch(r"[0-9]{4}", year) or not 1981 <= int(year) <= timezone.now().year + 2:
        raise ValueError("missing model year")
    return {"status": "decoded", "vehicle": {"make": make.strip(), "model": model.strip(), "year": int(year)}}


def decode_vehicle(vin):
    key = "catalog:vin:v1:" + hashlib.sha256(vin.encode("ascii")).hexdigest()
    try:
        cached = cache.get(key)
    except Exception:
        cached = None
    if cached is not None:
        return cached
    try:
        result = _read_provider(vin)
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        result = {"status": "unavailable"}
    ttl = 604800 if result["status"] == "decoded" else (300 if result["status"] == "unrecognized" else 20)
    try:
        cache.set(key, result, timeout=ttl)
    except Exception:
        pass
    return result


def resolve_vehicle(vehicle):
    make_key = _key(vehicle["make"])
    make_keys = {make_key}
    if make_key == "mercedesbenz":
        make_keys.add("mercedes")  # Manufacturer spelling, not model equivalence.
    makes = [m for m in VehicleMake.objects.filter(is_active=True) if {_key(m.name), _key(m.slug)} & make_keys]
    if len(makes) != 1:
        return {"status": "not_in_catalog", "vehicle": vehicle}
    make = makes[0]
    model_key = _key(vehicle["model"])
    models = [m for m in VehicleModel.objects.filter(make=make, is_active=True) if model_key in {_key(m.name), _key(m.slug)}]
    if len(models) != 1:
        return {"status": "not_in_catalog", "vehicle": vehicle}
    model = models[0]
    coverage = ProductFitment.objects.filter(
        vehicle_model=model, year_from__lte=vehicle["year"], year_to__gte=vehicle["year"],
        product__status=ProductStatus.PUBLISHED, product__category__is_active=True,
    ).filter(Q(engine__isnull=True) | Q(engine__is_active=True)).exists()
    if not coverage:
        return {"status": "no_coverage", "vehicle": vehicle}
    return {
        "status": "matched", "vehicle": {"make": make.name, "model": model.name, "year": vehicle["year"]},
        "filters": {"make": make.slug, "model": model.slug, "year": str(vehicle["year"])},
    }
