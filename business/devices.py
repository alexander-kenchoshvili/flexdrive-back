"""Aggregate GA4 device categories only; no order/browser identity tracking."""
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

from .analytics import AnalyticsUnavailable, _batch, _credentials, _filter, _warnings
from .ga4 import build_ga4_report_request
from .marketing import MetaUnavailable, _cached

METRICS = ("sessions", "ecommercePurchases")
DEVICES = (("mobile", "მობილური"), ("desktop", "კომპიუტერი / ლეპტოპი"),
           ("tablet", "პლანშეტი"), ("other", "სხვა / უცნობი"))


def device_request(period):
    public = {"notExpression": _filter("pagePath", r"^/(business|admin|manager-fd)(/|$)", "PARTIAL_REGEXP")}
    body = build_ga4_report_request(period, ("deviceCategory",), METRICS, dimension_filter=public)
    body.update(limit="10", orderBys=[{"metric": {"metricName": "sessions"}, "desc": True}])
    return body


def parse_devices(body):
    if ([item["name"] for item in body.get("dimensionHeaders", [])] != ["deviceCategory"]
            or [item["name"] for item in body["metricHeaders"]] != list(METRICS)):
        raise ValueError("Unexpected device report headers")
    counts = {key: {"sessions": 0, "purchases": 0} for key, _ in DEVICES}
    raw_rows = body.get("rows", [])
    if not isinstance(raw_rows, list) or len(raw_rows) > 10:
        raise ValueError("Invalid device rows")
    count = body.get("rowCount", len(raw_rows))
    if type(count) is not int or count != len(raw_rows):
        raise ValueError("Incomplete device rows")
    seen = set()
    for row in raw_rows:
        if len(row["dimensionValues"]) != 1 or len(row["metricValues"]) != len(METRICS):
            raise ValueError("Invalid device row")
        raw = row["dimensionValues"][0]["value"]
        if not isinstance(raw, str) or len(raw) > 100 or raw in seen:
            raise ValueError("Invalid or duplicate category")
        seen.add(raw)
        category = raw.lower() if raw.lower() in {"mobile", "desktop", "tablet"} else "other"
        values = [Decimal(item["value"]) for item in row["metricValues"]]
        if any(not value.is_finite() or value < 0 or value > 2**53 - 1
               or value != value.to_integral_value() for value in values):
            raise ValueError("Invalid device count")
        counts[category]["sessions"] += int(values[0])
        counts[category]["purchases"] += int(values[1])
    totals = {metric: sum(row[metric] for row in counts.values()) for metric in ("sessions", "purchases")}
    rows = [{"category": key, "label": label, **counts[key],
             "session_share": round(counts[key]["sessions"] * 100 / totals["sessions"], 1) if totals["sessions"] else None,
             "purchase_share": round(counts[key]["purchases"] * 100 / totals["purchases"], 1) if totals["purchases"] else None}
            for key, label in DEVICES]
    return {"rows": rows, "totals": totals, "warnings": _warnings([body]),
            "timezone": body.get("metadata", {}).get("timeZone"), "source": "ga4"}


def _read(period):
    try:
        with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
            return parse_devices(_batch(session, [device_request(period)])[0])
    except (AnalyticsUnavailable, RequestException, GoogleAuthError, InvalidOperation) as error:
        raise MetaUnavailable(error.code if isinstance(error, AnalyticsUnavailable) else "unavailable") from None


def build_device_report(period):
    base = {"period": {"start": str(period.start), "end": str(period.end)}, "refresh_seconds": 300}
    raw, path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not path:
        return {**base, "status": "not_configured", "fetched_at": None,
                "message": "Google-ის მოწყობილობების ანგარიში ამ გარემოში დაკავშირებული არ არის."}
    identity = sha256(f"{raw}\0{path}".encode()).hexdigest()[:16]
    payload = _cached(f"business:devices:v1:{identity}:{period.start}:{period.end}", lambda: _read(period))
    if payload["status"] == "unavailable":
        payload = {**payload, "message": "მოწყობილობების ანგარიში დროებით მიუწვდომელია. ეს ნულოვან ვიზიტებს ან შესყიდვებს არ ნიშნავს."}
    return {**base, **payload}
