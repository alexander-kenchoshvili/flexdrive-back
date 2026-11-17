"""Bounded, read-only public page performance; never expose checkout/token URLs."""
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re
from urllib.parse import unquote

from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

from .analytics import AnalyticsUnavailable, _batch, _credentials, _filter, _warnings
from .ga4 import build_ga4_report_request
from .marketing import MetaUnavailable, _cached

METRICS = ("screenPageViews", "totalUsers", "activeUsers", "userEngagementDuration")
# Include only storefront routes: new unknown/private routes are excluded by default.
PUBLIC_PATH = r"^/($|catalog(/[^/?#]+)?/?$|about/?$|contact/?$|terms/?$|privacy/?$|delivery/?$|returns/?$)"


def page_request(period):
    body = build_ga4_report_request(period, ("pagePath",), METRICS,
                                   dimension_filter=_filter("pagePath", PUBLIC_PATH, "FULL_REGEXP"))
    body.update(limit="20", orderBys=[{"metric": {"metricName": "screenPageViews"}, "desc": True},
                                     {"dimension": {"dimensionName": "pagePath"}}])
    return body


def parse_pages(body):
    if ([item["name"] for item in body.get("dimensionHeaders", [])] != ["pagePath"]
            or [item["name"] for item in body["metricHeaders"]] != list(METRICS)):
        raise ValueError("Unexpected page headers")
    rows, seen = [], set()
    for row in body.get("rows", []):
        if len(row["dimensionValues"]) != 1 or len(row["metricValues"]) != len(METRICS):
            raise ValueError("Unexpected page row")
        path = row["dimensionValues"][0]["value"]
        if (not isinstance(path, str) or len(path) > 1000 or not re.fullmatch(PUBLIC_PATH, path)
                or any(char in unquote(path) for char in ("?", "#", "\\", "\n", "\r")) or path in seen):
            raise ValueError("Nonpublic or duplicate page")
        seen.add(path)
        numbers = [Decimal(item["value"]) for item in row["metricValues"]]
        if any(not value.is_finite() or value < 0 or value > 2**53 - 1 for value in numbers):
            raise ValueError("Invalid page metric")
        if any(value != value.to_integral_value() for value in numbers[:3]):
            raise ValueError("Invalid page count")
        views, users, active, seconds = numbers
        rows.append({"path": path, "views": int(views), "users": int(users),
                     "active_users": int(active),
                     "average_active_seconds": float(seconds / active) if active else None})
    count = body.get("rowCount", len(rows))
    if isinstance(count, bool) or not isinstance(count, int) or count < len(rows) or len(rows) > 20:
        raise ValueError("Invalid page count")
    return {"rows": rows, "row_count": count, "warnings": _warnings([body]),
            "timezone": body.get("metadata", {}).get("timeZone")}


def _read(period):
    try:
        with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
            return parse_pages(_batch(session, [page_request(period)])[0])
    except (AnalyticsUnavailable, RequestException, GoogleAuthError, InvalidOperation) as error:
        raise MetaUnavailable(error.code if isinstance(error, AnalyticsUnavailable) else "unavailable") from None


def build_page_report(period):
    base = {"period": {"start": str(period.start), "end": str(period.end)}, "refresh_seconds": 300}
    raw, path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not path:
        return {**base, "status": "not_configured", "fetched_at": None}
    identity = sha256(f"{raw}\0{path}".encode()).hexdigest()[:16]
    payload = _cached(f"business:pages:v1:{identity}:{period.start}:{period.end}", lambda: _read(period))
    if payload["status"] == "unavailable":
        payload = {**payload, "message": "Google-ის გვერდების ანგარიში დროებით მიუწვდომელია. ეს ნულოვან ნახვებს არ ნიშნავს."}
    return {**base, **payload}
