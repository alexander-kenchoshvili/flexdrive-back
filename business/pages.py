"""Bounded, read-only public page reports; never expose checkout/token URLs."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from urllib.parse import unquote

from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

from .analytics import AnalyticsUnavailable, _batch, _credentials, _filter, _warnings
from .ga4 import build_ga4_report_request
from .marketing import MetaUnavailable, _cached

METRICS = ("screenPageViews", "totalUsers", "activeUsers", "userEngagementDuration", "sessions")
PAGE_SIZE = 20
SOURCE_LIMIT = 50
SEARCH_LIMIT = 500
# Unknown/private routes remain excluded, including during title searches.
PUBLIC_PATH = r"^/($|catalog(/category/[^/?#]+|/[^/?#]+)?/?$|blogs(/[0-9]+-[^/?#]+)?/?$|about/?$|contact/?$|terms/?$|privacy/?$|delivery/?$|returns/?$)"
FACEBOOK_SOURCE = r"(^|.*\.)facebook\.com$|^fb$"


def is_public_path(path):
    if not isinstance(path, str) or not path or len(path) > 1000:
        return False
    decoded = path
    for _ in range(4):
        decoded = unquote(decoded)
    return bool(re.fullmatch(PUBLIC_PATH, path) and re.fullmatch(PUBLIC_PATH, decoded)
                and decoded.count("/") == path.count("/")
                and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char in "?#\\%" for char in decoded)
                and not any(segment in (".", "..") for segment in decoded.split("/")))


def _paths_filter(paths):
    return {"filter": {"fieldName": "pagePath", "inListFilter": {"values": paths, "caseSensitive": True}}}


def _request(period, dimensions, metrics=METRICS, *, extra=None, limit=PAGE_SIZE):
    public = _filter("pagePath", PUBLIC_PATH, "FULL_REGEXP")
    scope = {"andGroup": {"expressions": [public, extra]}} if extra else public
    body = build_ga4_report_request(period, dimensions, metrics, dimension_filter=scope)
    body["limit"] = str(limit)
    return body


def page_request(period, *, page=1, paths=None):
    body = _request(period, ("pagePath",), extra=_paths_filter(paths) if paths else None)
    body.update(offset=str((page - 1) * PAGE_SIZE), orderBys=[
        {"metric": {"metricName": "screenPageViews"}, "desc": True},
        {"dimension": {"dimensionName": "pagePath"}},
    ])
    return body


def _rows(body, dimensions, metrics=METRICS, *, limit=PAGE_SIZE):
    # Successful empty dimensionless GA4 reports may omit metricHeaders entirely.
    if (not dimensions and "metricHeaders" not in body and not body.get("dimensionHeaders")
            and not body.get("rows") and body.get("rowCount", 0) == 0
            and body.get("kind") == "analyticsData#runReport" and isinstance(body.get("metadata"), dict)):
        return [], 0
    if ([item["name"] for item in body.get("dimensionHeaders", [])] != list(dimensions)
            or [item["name"] for item in body["metricHeaders"]] != list(metrics)):
        raise ValueError("Unexpected page headers")
    rows, seen = [], set()
    for row in body.get("rows", []):
        dims = row.get("dimensionValues", [])
        if len(dims) != len(dimensions) or len(row["metricValues"]) != len(metrics):
            raise ValueError("Unexpected page row")
        values = [item["value"] for item in dims]
        if any(not isinstance(value, str) or len(value) > 1000 for value in values):
            raise ValueError("Invalid dimension")
        key = tuple(values)
        if key in seen:
            raise ValueError("Duplicate row")
        seen.add(key)
        parsed = dict(zip(dimensions, values))
        for name, item in zip(metrics, row["metricValues"]):
            value = Decimal(item["value"])
            if not value.is_finite() or value < 0 or value > 2**53 - 1:
                raise ValueError("Invalid page metric")
            if name != "userEngagementDuration" and value != value.to_integral_value():
                raise ValueError("Invalid page count")
            parsed[name] = float(value) if name == "userEngagementDuration" else int(value)
        rows.append(parsed)
    count = body.get("rowCount", len(rows))
    if isinstance(count, bool) or not isinstance(count, int) or count < len(rows) or len(rows) > limit:
        raise ValueError("Invalid row count")
    return rows, count


def _metrics(row):
    active = row["activeUsers"]
    return {"views": row["screenPageViews"], "users": row["totalUsers"], "active_users": active,
            "sessions": row["sessions"],
            "average_active_seconds": row["userEngagementDuration"] / active if active else None}


def parse_pages(body):
    rows, count = _rows(body, ("pagePath",))
    if any(not is_public_path(row["pagePath"]) for row in rows):
        raise ValueError("Nonpublic page")
    return {"rows": [{"path": row["pagePath"], **_metrics(row)} for row in rows],
            "row_count": count, "warnings": _warnings([body]),
            "timezone": body.get("metadata", {}).get("timeZone")}


def detail_requests(period, path):
    if not is_public_path(path):
        raise ValueError("Nonpublic page")
    exact = _filter("pagePath", path)
    exact["filter"]["stringFilter"]["caseSensitive"] = True
    requests = [_request(period, (), extra=exact, limit=1),
                _request(period, ("date",), extra=exact, limit=366),
                _request(period, ("sessionSourceMedium",), extra=exact, limit=SOURCE_LIMIT),
                _request(period, (), extra={"andGroup": {"expressions": [
                    exact, _filter("sessionSource", FACEBOOK_SOURCE, "FULL_REGEXP")]}}, limit=1)]
    requests[1]["orderBys"] = [{"dimension": {"dimensionName": "date"}}]
    requests[2]["orderBys"] = [{"metric": {"metricName": "sessions"}, "desc": True},
                                {"dimension": {"dimensionName": "sessionSourceMedium"}}]
    return requests


def parse_detail(reports, period):
    if len(reports) != 4:
        raise ValueError("Unexpected detail reports")
    totals, total_count = _rows(reports[0], (), limit=1)
    daily, day_count = _rows(reports[1], ("date",), limit=366)
    sources, source_count = _rows(reports[2], ("sessionSourceMedium",), limit=SOURCE_LIMIT)
    facebook, facebook_count = _rows(reports[3], (), limit=1)
    if total_count > 1 or facebook_count > 1 or day_count != len(daily):
        raise ValueError("Incomplete detail report")
    if (not totals and (daily or sources or facebook)) or (source_count > len(sources) and len(sources) < SOURCE_LIMIT):
        raise ValueError("Missing detail totals or sources")
    days = {}
    for row in daily:
        current = datetime.strptime(row["date"], "%Y%m%d").date()
        if not period.start <= current <= period.end:
            raise ValueError("Unexpected report date")
        days[current] = _metrics(row)
    zero = {name: 0 for name in METRICS}
    result_days = []
    current = period.start
    while current <= period.end:
        result_days.append({"date": current.isoformat(), **days.get(current, _metrics(zero))})
        current += timedelta(days=1)
    return {"summary": _metrics(totals[0] if totals else zero),
            "facebook": _metrics(facebook[0] if facebook else zero), "daily": result_days,
            "sources": [{"source": row["sessionSourceMedium"], **_metrics(row)} for row in sources],
            "source_row_count": source_count, "warnings": _warnings(reports),
            "timezone": reports[0].get("metadata", {}).get("timeZone")}


def _titles(session, period, paths):
    # Labels never split page metrics or unique users.
    request = _request(period, ("pagePath", "pageTitle"), ("screenPageViews",),
                       extra=_paths_filter(paths), limit=200)
    request["orderBys"] = [{"metric": {"metricName": "screenPageViews"}, "desc": True},
                           {"dimension": {"dimensionName": "pagePath"}},
                           {"dimension": {"dimensionName": "pageTitle"}}]
    body = _batch(session, [request])[0]
    rows, _ = _rows(body, ("pagePath", "pageTitle"), ("screenPageViews",), limit=200)
    titles = {}
    for row in rows:
        if row["pagePath"] not in paths or not is_public_path(row["pagePath"]):
            raise ValueError("Unexpected title path")
        title = row["pageTitle"].strip()
        if title and title != "(not set)":
            titles.setdefault(row["pagePath"], title)
    return titles


def _read(period, *, query="", page=1, path=""):
    try:
        with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
            if path:
                return parse_detail(_batch(session, detail_requests(period, path)), period)
            paths, discovery_warnings = None, []
            if query:
                search = {"orGroup": {"expressions": [
                    _filter("pagePath", query, "CONTAINS"), _filter("pageTitle", query, "CONTAINS")]}}
                discovery = _batch(session, [_request(period, ("pagePath",), ("screenPageViews",),
                                                      extra=search, limit=SEARCH_LIMIT)])[0]
                matches, count = _rows(discovery, ("pagePath",), ("screenPageViews",), limit=SEARCH_LIMIT)
                if any(not is_public_path(row["pagePath"]) for row in matches):
                    raise ValueError("Nonpublic search result")
                if count > SEARCH_LIMIT:
                    return {"search_too_broad": True, "warnings": _warnings([discovery])}
                if count != len(matches):
                    raise ValueError("Incomplete search")
                paths = [row["pagePath"] for row in matches]
                discovery_warnings = _warnings([discovery])
                if not paths:
                    return {"rows": [], "row_count": 0, "warnings": discovery_warnings,
                            "timezone": discovery.get("metadata", {}).get("timeZone")}
            # Title matching only discovers paths; full metrics are then requested
            # without a title filter, so historical title changes cannot lose users.
            result = parse_pages(_batch(session, [page_request(period, page=page, paths=paths)])[0])
            if len(result["rows"]) != min(PAGE_SIZE, max(result["row_count"] - (page - 1) * PAGE_SIZE, 0)):
                raise ValueError("Incomplete page list")
            result["warnings"] = list(dict.fromkeys(discovery_warnings + result["warnings"]))
            if result["rows"]:
                try:
                    titles = _titles(session, period, [row["path"] for row in result["rows"]])
                except (AnalyticsUnavailable, RequestException, GoogleAuthError, ValueError, KeyError, TypeError, InvalidOperation):
                    titles = {}  # Optional labels cannot hide valid page counts.
                for row in result["rows"]:
                    row["title"] = titles.get(row["path"])
            return result
    except (AnalyticsUnavailable, RequestException, GoogleAuthError, InvalidOperation) as error:
        raise MetaUnavailable(error.code if isinstance(error, AnalyticsUnavailable) else "unavailable") from None


def build_page_report(period, *, query="", page=1, path=""):
    if path and not is_public_path(path):
        raise ValueError("Nonpublic page")
    if not isinstance(query, str) or len(query) > 120 or not isinstance(page, int) or not 1 <= page <= 1000000:
        raise ValueError("Invalid page filter")
    base = {"period": {"start": str(period.start), "end": str(period.end)}, "refresh_seconds": 300,
            "mode": "detail" if path else "list", "path": path or None,
            "query": query, "page": page, "page_size": PAGE_SIZE, "source_limit": SOURCE_LIMIT}
    raw, credential_path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not credential_path:
        return {**base, "status": "not_configured", "fetched_at": None}
    identity = sha256(f"{raw}\0{credential_path}".encode()).hexdigest()[:16]
    filters = sha256(json.dumps([query, page, path], ensure_ascii=True).encode()).hexdigest()[:20]
    key = f"business:pages:v2:{identity}:{period.start}:{period.end}:{filters}"
    payload = _cached(key, lambda: _read(period, query=query, page=page, path=path))
    if payload["status"] == "unavailable":
        payload = {**payload, "message": "Google-ის გვერდების ანგარიში დროებით მიუწვდომელია. ეს ნულოვან ნახვებს არ ნიშნავს."}
    return {**base, **payload}
