"""First-party vehicle demand. Never store raw VIN/query/IP/account identifiers."""
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from django.core import signing
from django.db.models import Count, Min, Q
from django.utils import timezone
from django.utils.crypto import salted_hmac

from catalog.models import VehicleMake, VehicleModel
from catalog.variant_hints import parse_variant_query
from .models import VehicleInterest

TBILISI = ZoneInfo("Asia/Tbilisi")
TOKEN_SALT = "vehicle-interest-v1"


def lookup_interest_token(result):
    """Sign only decoded public vehicle attributes, NEVER the VIN or full row."""
    if result.get("status") not in ("matched", "no_coverage", "not_in_catalog"):
        return None
    vehicle = result["vehicle"]
    from catalog.variant_hints import variant_keys
    variants = variant_keys(*(vehicle.get(field, "") for field in ("trim", "trim2", "series", "series2")))
    return signing.dumps({
        "make": vehicle["make"], "model": vehicle["model"], "year": vehicle["year"],
        "variant": ",".join(variants), "outcome": result["status"],
    }, salt=TOKEN_SALT, compress=True)


def _vehicle(values):
    token = values.get("lookup_token")
    if token:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=900)
        if not isinstance(payload, dict) or payload.get("outcome") not in ("matched", "no_coverage", "not_in_catalog"):
            raise ValueError("Invalid lookup")
        vehicle = {key: payload[key] for key in ("make", "model", "year", "variant")}
        make = VehicleMake.objects.filter(is_active=True, name__iexact=vehicle["make"]).first()
        if make:
            vehicle["make"] = make.name
            model = VehicleModel.objects.filter(make=make, is_active=True, name__iexact=vehicle["model"]).first()
            if model:
                vehicle["model"] = model.name
        return vehicle, True, payload["outcome"] != "matched"
    def lookup(queryset, value):
        return queryset.get(pk=int(value)) if value.isascii() and value.isdigit() else queryset.get(slug=value)
    make = lookup(VehicleMake.objects.filter(is_active=True), values.get("make", ""))
    model = lookup(VehicleModel.objects.filter(is_active=True, make=make), values.get("model", ""))
    variants = parse_variant_query(values.get("variant", ""))
    return {
        "make": make.name, "model": model.name, "year": values.get("year"),
        "variant": ",".join(key for key in variants if key != "unspecified"),
    }, False, False


def record_interest(values):
    vehicle, via_vin, missing = _vehicle(values)
    # Case/punctuation normalization merges the VIN and matching manual selection.
    normalized = [re.sub(r"[^\w]", "", str(vehicle[key]).casefold()) for key in ("make", "model", "year")]
    normalized.append(",".join(sorted(filter(None, vehicle["variant"].split(",")))))
    key = hashlib.sha256(json.dumps(normalized).encode()).hexdigest()
    day = timezone.now().astimezone(TBILISI).date()
    digest = salted_hmac("vehicle-interest-session", str(values["session_id"]), algorithm="sha256").hexdigest()
    row, created = VehicleInterest.objects.get_or_create(
        day=day, session_digest=digest, vehicle_key=key,
        defaults={**vehicle, "via_vin": via_vin, "missing_catalog": missing,
                  "had_no_results": values.get("result_count") == 0},
    )
    if not created:
        # Monotonic flags survive concurrent/repeated events; no counter increment.
        changes = {}
        if via_vin:
            changes["via_vin"] = True
        if missing:
            changes["missing_catalog"] = True
        if values.get("result_count") == 0:
            changes["had_no_results"] = True
        if changes:
            VehicleInterest.objects.filter(pk=row.pk).update(**changes)


def build_vehicle_demand(period):
    qs = VehicleInterest.objects.filter(day__gte=period.start, day__lte=period.end)
    summary = qs.aggregate(
        visits=Count("session_digest", distinct=True), selections=Count("id"),
        no_results=Count("session_digest", distinct=True, filter=Q(had_no_results=True)),
        missing_catalog=Count("session_digest", distinct=True, filter=Q(missing_catalog=True)),
    )
    grouped = qs.values("make", "model", "year").annotate(
        visits=Count("session_digest", distinct=True),
        vin_visits=Count("session_digest", distinct=True, filter=Q(via_vin=True)),
        no_results=Count("session_digest", distinct=True, filter=Q(had_no_results=True)),
        missing_catalog=Count("session_digest", distinct=True, filter=Q(missing_catalog=True)),
    ).order_by("-visits", "make", "model", "year")
    rows = list(grouped[:100])
    insights = []
    if rows:
        top = rows[0]
        leaders = [row for row in rows if row["visits"] == top["visits"]]
        label = lambda row: f"{row['make']} {row['model']} · {row['year'] or 'წელი არჩეული არ არის'}"
        if len(leaders) == 1:
            insights.append(f"ყველაზე ხშირად ეძებდნენ: {label(top)} — {top['visits']} ვიზიტში.")
            if len(rows) > 1:
                insights.append("შემდეგ ინტერესდებიან: " + "; ".join(f"{label(row)} — {row['visits']} ვიზიტში" for row in rows[1:3]) + ".")
        else:
            insights.append("ლიდერებს შორის არიან: " + "; ".join(label(row) for row in leaders[:3]) + f" — თითოეული {top['visits']} ვიზიტში.")
        gap = next(iter(grouped.filter(Q(no_results__gt=0) | Q(missing_catalog__gt=0)).order_by("-missing_catalog", "-no_results", "-visits", "make", "model", "year")[:1]), None)
        if gap:
            insights.append(f"გადასახედია {label(gap)}: {gap['no_results']} ვიზიტში ერთ-ერთ ძიებას შედეგი არ ჰქონდა; {gap['missing_catalog']} ვიზიტში VIN-ით ამოცნობილი მანქანისთვის კატალოგის შესაბამისობა ვერ მოიძებნა.")
        if summary["visits"] < 10:
            insights.append("მონაცემი ჯერ მცირეა — ეს საწყისი სიგნალია და არა საკმარისი საფუძველი სარეკლამო ბიუჯეტის გასაზრდელად.")
    else:
        insights.append("ამ პერიოდში მანქანების ძიების მონაცემები ჯერ არ დაგროვებულა. აღრიცხვა ჩართვის შემდეგ იწყება; ძველი ძიებები არ აღდგება.")
    first = VehicleInterest.objects.aggregate(first=Min("day"))["first"]
    return {
        "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
        "generated_at": timezone.now().isoformat(),
        "collection_started_at": first.isoformat() if first else None,
        "summary": summary, "rows": rows, "row_count": grouped.count(), "insights": insights,
    }
