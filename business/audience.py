"""GA4 audience aggregates, using direct new/returning counts rather than subtraction."""
from datetime import datetime, timedelta
from hashlib import sha256

from django.conf import settings
from google.auth.transport.requests import AuthorizedSession

from .analytics import AnalyticsUnavailable, _batch, _credentials, _filter, _rows, _warnings
from .decisions import _safe_google
from .ga4 import build_ga4_report_request
from .marketing import _cached


def audience_requests(period):
    public = {"notExpression": _filter("pagePath", r"^/(business|admin|manager-fd)(/|$)", "PARTIAL_REGEXP")}
    returning = {"andGroup": {"expressions": [public, _filter("newVsReturning", "returning")]}}
    specs = [
        ((), ("newUsers",), public, 1),
        (("date",), ("newUsers",), public, 366),
        ((), ("totalUsers",), returning, 1),
        (("date",), ("totalUsers",), returning, 366),
        (("firstUserSourceMedium",), ("newUsers",), public, 20),
    ]
    result = []
    for dimensions, metrics, scope, limit in specs:
        body = build_ga4_report_request(period, dimensions, metrics, dimension_filter=scope)
        body["limit"] = str(limit)
        if dimensions:
            body["orderBys"] = ([{"dimension": {"dimensionName": "date"}}] if dimensions == ("date",)
                                else [{"metric": {"metricName": "newUsers"}, "desc": True}])
        result.append(body)
    return result


def _read(period):
    definitions = audience_requests(period)
    with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
        reports = _batch(session, definitions)
    rows = [_rows(report, definition) for report, definition in zip(reports, definitions)]
    daily = {}
    for values, metric, key in ((rows[1], "newUsers", "new_users"), (rows[3], "totalUsers", "returning_users")):
        seen = set()
        for row in values:
            try:
                day = datetime.strptime(row["date"], "%Y%m%d").date()
            except ValueError:
                raise AnalyticsUnavailable() from None
            if not period.start <= day <= period.end or day in seen:
                raise AnalyticsUnavailable()
            seen.add(day)
            daily.setdefault(day, {})[key] = row[metric]
    days, day = [], period.start
    while day <= period.end:
        days.append({"date": str(day), "new_users": daily.get(day, {}).get("new_users", 0),
                     "returning_users": daily.get(day, {}).get("returning_users", 0)})
        day += timedelta(days=1)
    return {"new_users": rows[0][0]["newUsers"] if rows[0] else 0,
            "returning_users": rows[2][0]["totalUsers"] if rows[2] else 0,
            "daily": days,
            "first_sources": [{"source": row["firstUserSourceMedium"][:200], "new_users": row["newUsers"]} for row in rows[4]],
            "source_row_count": reports[4].get("rowCount", len(rows[4])),
            "timezone": reports[0].get("metadata", {}).get("timeZone"), "warnings": _warnings(reports)}


def build_audience_report(period):
    base = {"period": {"start": str(period.start), "end": str(period.end)}, "source": "ga4", "refresh_seconds": 300}
    raw, path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not path:
        return {**base, "status": "not_configured", "fetched_at": None,
                "message": "Google-ის მომხმარებლების ანგარიში ამ გარემოში დაკავშირებული არ არის."}
    identity = sha256(f"{raw}\0{path}".encode()).hexdigest()[:16]
    payload = _cached(f"business:audience:v1:{identity}:{period.start}:{period.end}",
                      lambda: _safe_google(lambda: _read(period)))
    if payload["status"] == "unavailable":
        payload = {**payload, "message": "მომხმარებლების ანგარიში დროებით მიუწვდომელია. ეს ნულოვან მომხმარებლებს არ ნიშნავს."}
    return {**base, **payload}
