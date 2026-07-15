from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from commerce.easyway import EasywayResponseError
from commerce.models import EasywayCity, EasywayRegion


@dataclass(frozen=True)
class EasywayLocationSyncResult:
    regions_created: int
    regions_updated: int
    regions_deactivated: int
    cities_created: int
    cities_updated: int
    cities_deactivated: int


def sync_easyway_locations(client):
    region_rows = _normalized_rows(client.get_regions(), "region")
    city_rows = []
    for region_row in region_rows:
        cities = _normalized_rows(
            client.get_cities(region_row["external_id"]),
            "city",
        )
        city_rows.extend(
            {
                **city,
                "region_external_id": region_row["external_id"],
            }
            for city in cities
        )

    _ensure_unique_ids(city_rows, "city")
    now = timezone.now()

    with transaction.atomic():
        region_result = _sync_regions(region_rows, now)
        city_result = _sync_cities(city_rows, now)

    return EasywayLocationSyncResult(
        regions_created=region_result[0],
        regions_updated=region_result[1],
        regions_deactivated=region_result[2],
        cities_created=city_result[0],
        cities_updated=city_result[1],
        cities_deactivated=city_result[2],
    )


def _sync_regions(rows, now):
    existing = {
        item.external_id: item
        for item in EasywayRegion.objects.all()
    }
    to_create = []
    to_update = []

    for row in rows:
        item = existing.get(row["external_id"])
        if item is None:
            to_create.append(
                EasywayRegion(
                    external_id=row["external_id"],
                    name=row["name"],
                    is_active=True,
                    is_internal_delivery=row["name"].strip() == "თბილისი",
                    last_synced_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue

        item.name = row["name"]
        item.is_active = True
        item.last_synced_at = now
        item.updated_at = now
        to_update.append(item)

    if to_create:
        EasywayRegion.objects.bulk_create(to_create)
    if to_update:
        EasywayRegion.objects.bulk_update(
            to_update,
            ["name", "is_active", "last_synced_at", "updated_at"],
        )

    active_ids = [row["external_id"] for row in rows]
    deactivated = (
        EasywayRegion.objects.filter(is_active=True)
        .exclude(external_id__in=active_ids)
        .update(is_active=False, updated_at=now)
    )
    return len(to_create), len(to_update), deactivated


def _sync_cities(rows, now):
    regions = {
        item.external_id: item
        for item in EasywayRegion.objects.filter(
            external_id__in={row["region_external_id"] for row in rows}
        )
    }
    existing = {
        item.external_id: item
        for item in EasywayCity.objects.all()
    }
    to_create = []
    to_update = []

    for row in rows:
        region = regions[row["region_external_id"]]
        item = existing.get(row["external_id"])
        if item is None:
            to_create.append(
                EasywayCity(
                    region=region,
                    external_id=row["external_id"],
                    name=row["name"],
                    is_active=True,
                    last_synced_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue

        item.region = region
        item.name = row["name"]
        item.is_active = True
        item.last_synced_at = now
        item.updated_at = now
        to_update.append(item)

    if to_create:
        EasywayCity.objects.bulk_create(to_create, batch_size=500)
    if to_update:
        EasywayCity.objects.bulk_update(
            to_update,
            ["region", "name", "is_active", "last_synced_at", "updated_at"],
            batch_size=500,
        )

    active_ids = [row["external_id"] for row in rows]
    deactivated = (
        EasywayCity.objects.filter(is_active=True)
        .exclude(external_id__in=active_ids)
        .update(is_active=False, updated_at=now)
    )
    return len(to_create), len(to_update), deactivated


def _normalized_rows(raw_rows, label):
    normalized = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise EasywayResponseError(
                f"EasyWay API returned an invalid {label} item."
            )
        try:
            external_id = int(raw.get("id"))
        except (TypeError, ValueError) as error:
            raise EasywayResponseError(
                f"EasyWay API returned an invalid {label} ID."
            ) from error
        name = str(raw.get("name") or "").strip()
        if external_id <= 0 or not name:
            raise EasywayResponseError(
                f"EasyWay API returned invalid {label} data."
            )
        normalized.append({"external_id": external_id, "name": name})

    _ensure_unique_ids(normalized, label)
    return normalized


def _ensure_unique_ids(rows, label):
    ids = [row["external_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise EasywayResponseError(
            f"EasyWay API returned duplicate {label} IDs."
        )
