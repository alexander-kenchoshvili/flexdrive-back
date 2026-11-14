"""Read-only, fixed-property Google Search Console performance reports."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

from .analytics import AnalyticsUnavailable, _credentials
from .marketing import MetaUnavailable, _cached
from .reports import ReportPeriod, previous_period

PROPERTY = "sc-domain:flexdrive.ge"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
URL = f"https://www.googleapis.com/webmasters/v3/sites/{quote(PROPERTY, safe='')}/searchAnalytics/query"
PT = ZoneInfo("America/Los_Angeles")
ROW_LIMIT = 50


def available_period(period):
    today = timezone.now().astimezone(PT).date()
    # Deliberately omit the three most recent PT days. Still request only final data.
    last = today - timedelta(days=3)
    month = today.year * 12 + today.month - 1 - 16
    year, month_zero = divmod(month, 12)
    first = date(year, month_zero + 1, min(today.day, monthrange(year, month_zero + 1)[1]))
    start, end = max(period.start, first), min(period.end, last)
    return (ReportPeriod(start, end) if start <= end else None), first, last


def query_body(period, dimensions=()):
    return {"startDate": str(period.start), "endDate": str(period.end), "type": "web",
            "dataState": "final", "dimensions": list(dimensions),
            "aggregationType": "byPage" if "page" in dimensions else "byProperty",
            "rowLimit": 366 if dimensions == ("date",) else ROW_LIMIT if dimensions else 1,
            "startRow": 0}


def _credentials_for_search():
    # Reuse the validated reporting identity and key; never broaden the GA4 scope.
    return _credentials().with_scopes([SCOPE])


def _query(session, body):
    try:
        response = session.post(URL, json=body, timeout=(3, 8), max_allowed_time=15, allow_redirects=False)
        if response.status_code != 200:
            code = "quota" if response.status_code == 429 else "unavailable"
            if response.status_code in (401, 403):
                code = "access"
                # Read only the machine error reason; never return provider text.
                error = response.json().get("error", {})
                if any(item.get("reason") == "accessNotConfigured" for item in error.get("errors", [])):
                    code = "api_disabled"
            raise MetaUnavailable(code)
        result = response.json()
        expected = body["aggregationType"]
        if not isinstance(result, dict) or result.get("responseAggregationType") != expected:
            raise ValueError("Unexpected aggregation")
        return parse_rows(result, body)
    except MetaUnavailable:
        raise
    except (RequestException, GoogleAuthError, InvalidOperation, ValueError, KeyError, TypeError, AttributeError):
        raise MetaUnavailable("unavailable") from None


def parse_rows(result, body):
    rows = result.get("rows", [])
    if not isinstance(rows, list) or len(rows) > body["rowLimit"]:
        raise ValueError("Invalid rows")
    output, seen = [], set()
    dimensions = body["dimensions"]
    for row in rows:
        keys = row.get("keys", [])
        if not isinstance(keys, list) or len(keys) != len(dimensions) or any(not isinstance(key, str) for key in keys):
            raise ValueError("Invalid dimensions")
        identity = tuple(keys)
        if identity in seen:
            raise ValueError("Duplicate row")
        seen.add(identity)
        if dimensions == ["date"]:
            day = date.fromisoformat(keys[0])
            if not date.fromisoformat(body["startDate"]) <= day <= date.fromisoformat(body["endDate"]):
                raise ValueError("Invalid day")
        if dimensions == ["page"]:
            page = urlsplit(keys[0])
            host = (page.hostname or "").lower()
            if (page.scheme not in ("http", "https") or page.username or page.password
                    or not (host == "flexdrive.ge" or host.endswith(".flexdrive.ge"))):
                raise ValueError("Foreign page")
        parsed = {}
        for key in ("clicks", "impressions", "ctr", "position"):
            if isinstance(row[key], bool):
                raise ValueError("Invalid metric")
            value = Decimal(str(row[key]))
            if not value.is_finite() or value < 0 or value > 2**53 - 1:
                raise ValueError("Invalid metric")
            if key in ("clicks", "impressions"):
                if value != value.to_integral_value():
                    raise ValueError("Invalid count")
                parsed[key] = int(value)
            elif key == "ctr":
                if value > 1:
                    raise ValueError("Invalid CTR")
                parsed[key] = float(value)
            else:
                parsed[key] = float(value)
        if parsed["impressions"] and parsed["position"] < 1:
            raise ValueError("Invalid position")
        if not parsed["impressions"]:
            parsed["position"] = None
        output.append({**dict(zip(dimensions, keys)), **parsed})
    return output


def _empty():
    return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": None}


def _read(period, first_available):
    old = previous_period(period)
    blocks = {}
    try:
        with AuthorizedSession(_credentials_for_search(), refresh_timeout=5, max_refresh_attempts=0) as session:
            totals = _query(session, query_body(period))
            current = totals[0] if totals else _empty()
            tasks = [("previous", old, ()), ("daily", period, ("date",)),
                     ("queries", period, ("query",)), ("pages", period, ("page",))]
            for name, dates, dimensions in tasks:
                if dates.start < first_available:
                    blocks[name] = {"status": "range_limit"}
                    continue
                try:
                    rows = _query(session, query_body(dates, dimensions))
                    blocks[name] = {"status": "ready", **({"summary": rows[0] if rows else _empty()} if not dimensions else {"rows": rows})}
                except MetaUnavailable:
                    blocks[name] = {"status": "unavailable"}
    except AnalyticsUnavailable as error:
        raise MetaUnavailable(error.code) from None
    except (RequestException, GoogleAuthError):
        raise MetaUnavailable("unavailable") from None
    partial = any(block["status"] != "ready" for block in blocks.values())
    return {"status": "partial" if partial else "ready" if current["impressions"] or current["clicks"] else "empty",
            "summary": current, **blocks}


def build_search_console_report(requested):
    effective, first, last = available_period(requested)
    base = {"property": PROPERTY, "requested_period": {"start": str(requested.start), "end": str(requested.end)},
            "period": {"start": str(effective.start), "end": str(effective.end)} if effective else None,
            "timezone": "America/Los_Angeles", "data_state": "final", "available_from": str(first),
            "available_through": str(last), "refresh_seconds": 300, "row_limit": ROW_LIMIT}
    if not effective:
        return {**base, "status": "range_limit", "fetched_at": None,
                "message": "არჩეულ პერიოდში დამუშავებისთვის გამოყოფილი თარიღები არ არის. ბოლო 3 დღე გამოტოვებულია; ისტორია მაქსიმუმ 16 თვეა."}
    old = previous_period(effective)
    base["previous_period"] = {"start": str(old.start), "end": str(old.end)}
    raw, path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not path:
        return {**base, "status": "not_configured", "fetched_at": None,
                "message": "Search Console-ის წასაკითხი ანგარიშის სერვერული გასაღები ჯერ არ არის მითითებული."}
    identity = sha256(f"{raw}\0{path}".encode()).hexdigest()[:16]
    key = f"business:gsc:v1:{PROPERTY}:{identity}:{effective.start}:{effective.end}"
    payload = _cached(key, lambda: _read(effective, first))
    if payload["status"] == "unavailable":
        payload["message"] = "Search Console-ის წაკითხვა ვერ მოხერხდა. შესამოწმებელია წაკითხვის უფლება, API-ის ჩართვა ან დროებითი შეზღუდვა. ეს ნულოვან აქტივობას არ ნიშნავს."
    return {**base, **payload}
