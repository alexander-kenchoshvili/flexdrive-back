"""Stable numeric checkout IDs backed by the current Wingo reference snapshot."""

from dataclasses import dataclass

from .models import WingoLocality, WingoReferenceData, WingoRegion
from .delivery_quote_data import DeliveryQuoteError


@dataclass(frozen=True)
class DeliveryRegion:
    external_id: int
    name: str


@dataclass(frozen=True)
class DeliveryLocation:
    external_id: int
    name: str
    region_id: int
    region_name: str
    provider_region_id: str
    provider_city_id: str
    group_type: str
    snapshot: WingoReferenceData


def synchronize_location_ids(snapshot):
    """Called inside the reference transaction; never deletes/reuses old IDs."""
    WingoRegion.objects.bulk_create(
        [WingoRegion(external_id=row["id"]) for row in snapshot.regions], ignore_conflicts=True)
    regions = dict(WingoRegion.objects.values_list("external_id", "pk"))
    WingoLocality.objects.bulk_create([
        WingoLocality(external_id=row["id"], region_id=regions[row["region_id"]])
        for row in snapshot.localities
    ], update_conflicts=True, update_fields=["region"], unique_fields=["external_id"])


def _available(row):
    # A delivery weekday is NOT an order-acceptance cutoff.
    return row["active"] and row["operational"]


def delivery_locations():
    snapshot = WingoReferenceData.objects.filter(pk=1).first()
    if snapshot is None:
        return []
    available = {row["region_id"] for row in snapshot.localities if _available(row)}
    ids = dict(WingoRegion.objects.filter(external_id__in=available).values_list("external_id", "pk"))
    return [DeliveryRegion(ids[row["id"]], row["name"]) for row in snapshot.regions if row["id"] in ids]


def delivery_cities(region_id):
    snapshot = WingoReferenceData.objects.filter(pk=1).first()
    if snapshot is None:
        return None, []
    mapping = WingoRegion.objects.filter(pk=region_id).first()
    if mapping is None:
        return None, []
    region = next((row for row in snapshot.regions if row["id"] == mapping.external_id), None)
    if region is None:
        return None, []
    rows = [row for row in snapshot.localities if row["region_id"] == mapping.external_id and _available(row)]
    ids = dict(WingoLocality.objects.filter(region=mapping, external_id__in=[row["id"] for row in rows])
               .values_list("external_id", "pk"))
    return DeliveryRegion(mapping.pk, region["name"]), sorted(
        [{"id": ids[row["id"]], "name": row["locality_name"]} for row in rows if row["id"] in ids],
        key=lambda row: (row["name"], row["id"]))


def resolve_delivery_location(region_id, city_id):
    if type(region_id) is not int or type(city_id) is not int:
        raise DeliveryQuoteError("აირჩიეთ რეგიონი და დასახლება.", code="delivery_city_region_mismatch")
    snapshot = WingoReferenceData.objects.filter(pk=1).first()
    if snapshot is None:
        raise DeliveryQuoteError("მიწოდების მონაცემები ჯერ ხელმისაწვდომი არ არის.",
                                 code="delivery_location_unavailable", status_code=503)
    mapping = WingoLocality.objects.select_related("region").filter(pk=city_id, region_id=region_id).first()
    if mapping is None:
        raise DeliveryQuoteError("არჩეული რეგიონი ან დასახლება ხელმისაწვდომი არ არის.", code="delivery_location_unavailable")
    region = next((row for row in snapshot.regions if row["id"] == mapping.region.external_id), None)
    locality = next((row for row in snapshot.localities if row["id"] == mapping.external_id), None)
    if (region is None or locality is None or locality["region_id"] != region["id"]
            or not _available(locality) or len(locality["locality_name"]) > 120):
        raise DeliveryQuoteError("არჩეული დასახლების მიწოდება ხელმისაწვდომი არ არის.", code="delivery_location_unavailable")
    return DeliveryLocation(mapping.pk, locality["locality_name"], mapping.region_id, region["name"],
                            region["id"], locality["id"], locality["group_type"], snapshot)
