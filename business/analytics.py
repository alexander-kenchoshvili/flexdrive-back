"""Read-only GA4 reports, server credentials and bounded request-time refresh.

No scheduler, financial ledger writes, browser tokens or demo fallbacks.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from requests.exceptions import RequestException

from .ga4 import GA4_HOSTNAME, GA4_PROPERTY_ID, build_ga4_report_request

READER_EMAIL = "flexdrive-analytics-reader@flexdrive-494109.iam.gserviceaccount.com"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
BATCH_URL = f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY_ID}:batchRunReports"
FRESH_SECONDS = 300
STALE_SECONDS = 86400
RETRY_SECONDS = 60
SUMMARY = ("totalUsers", "sessions", "engagedSessions", "screenPageViews")
DAY = ("sessions", "totalUsers")
SOURCE = ("sessions", "engagedSessions")
SEARCH = ("eventCount", "averageCustomEvent:search_result_count")


class AnalyticsUnavailable(Exception):
    def __init__(self, code="unavailable"):
        self.code = code


def _filter(name, value, match="EXACT"):
    return {"filter": {"fieldName": name, "stringFilter": {
        "matchType": match, "value": value, "caseSensitive": False,
    }}}


def report_definitions(period, *, search=False):
    # Reject private page events even if a future tracking regression emits them.
    public = {"notExpression": {"orGroup": {"expressions": [
        _filter("pagePath", r"^/(business|admin)(/|$)", "PARTIAL_REGEXP"),
    ]}}}
    if search:
        scope = {"andGroup": {"expressions": [public, _filter("eventName", "search"),
                    _filter("customEvent:search_tracking_version", "2")]}}
        definitions = [(("customEvent:search_outcome",), SEARCH, 10, "eventCount"),
                       (("searchTerm", "customEvent:search_outcome"), SEARCH, 30, "eventCount")]
    else:
        scope = public
        definitions = [((), SUMMARY, 1, None), (("date",), DAY, 366, "date"),
                       (("sessionSourceMedium",), SOURCE, 20, "sessions")]
    requests = []
    for dimensions, metrics, limit, order in definitions:
        body = build_ga4_report_request(period, dimensions, metrics, dimension_filter=scope)
        body["limit"] = str(limit)
        if order:
            body["orderBys"] = [{"dimension": {"dimensionName": order}, "desc": False}] if order == "date" else [
                {"metric": {"metricName": order}, "desc": True}]
        requests.append(body)
    return requests


def _credentials():
    raw = settings.BUSINESS_GA4_CREDENTIALS_JSON
    path = settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not path:
        raise AnalyticsUnavailable("not_configured")
    try:
        if raw and path:
            raise ValueError("Choose a single credential source")
        if path:
            # Inspect trusted server config; never a browser-supplied file/path.
            with open(path, encoding="utf-8") as handle:
                info = json.load(handle)
        else:
            info = json.loads(raw)
        if (info.get("type") != "service_account" or info.get("client_email") != READER_EMAIL
                or info.get("token_uri") != "https://oauth2.googleapis.com/token"):
            raise ValueError("Wrong reader identity or token endpoint")
        return service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    except (OSError, ValueError, TypeError, AttributeError, GoogleAuthError):
        raise AnalyticsUnavailable("configuration_error") from None


def _batch(session, definitions):
    try:
        response = session.post(BATCH_URL, json={"requests": definitions},
                                timeout=(3, 8), max_allowed_time=15, allow_redirects=False)
        if response.status_code != 200:
            code = "quota" if response.status_code == 429 else "access" if response.status_code in (401, 403) else "unavailable"
            raise AnalyticsUnavailable(code)
        result = response.json()["reports"]
        if not isinstance(result, list) or len(result) != len(definitions):
            raise ValueError("Unexpected batch")
        return result
    except AnalyticsUnavailable:
        raise
    except (RequestException, GoogleAuthError, ValueError, KeyError, TypeError):
        raise AnalyticsUnavailable() from None


def _rows(report, definition):
    try:
        dimensions = [item["name"] for item in definition["dimensions"]]
        metrics = [item["name"] for item in definition["metrics"]]
        # Live GA4 omits even metricHeaders for an empty dimensionless report.
        # Accept that precise successful response; malformed/nonempty responses
        # still require their expected headers and must never become fake zeros.
        if (not dimensions and "metricHeaders" not in report
                and not report.get("dimensionHeaders") and not report.get("rows")
                and report.get("rowCount", 0) == 0
                and report.get("kind") == "analyticsData#runReport"
                and isinstance(report.get("metadata"), dict)):
            return []
        if ([item["name"] for item in report.get("dimensionHeaders", [])] != dimensions
                or [item["name"] for item in report["metricHeaders"]] != metrics):
            raise ValueError("Unexpected headers")
        result = []
        for row in report.get("rows", []):
            dim = row.get("dimensionValues", [])
            met = row["metricValues"]
            if len(dim) != len(dimensions) or len(met) != len(metrics):
                raise ValueError("Unexpected row")
            values = {}
            for name, item in zip(metrics, met):
                value = Decimal(item["value"])
                if not value.is_finite() or value < 0:
                    raise ValueError("Invalid metric")
                if name.startswith("averageCustomEvent:"):
                    values[name] = float(value)
                elif value == value.to_integral_value():
                    values[name] = int(value)
                else:
                    raise ValueError("Invalid count")
            result.append({**dict(zip(dimensions, (str(item["value"]) for item in dim))), **values})
        if len(result) > int(definition["limit"]):
            raise ValueError("Unexpected rows")
        return result
    except (ValueError, InvalidOperation, TypeError, KeyError, AttributeError):
        raise AnalyticsUnavailable() from None


def _warnings(reports):
    notes = []
    for report in reports:
        metadata = report.get("metadata", {})
        if metadata.get("subjectToThresholding"):
            notes.append("Google-ის კონფიდენციალურობის ზღვარი შეიძლება მცირე ჯგუფების მონაცემებს მალავდეს.")
        if metadata.get("dataLossFromOtherRow"):
            notes.append("Google-მა ზოგი კატეგორია გააერთიანა; დეტალური სია შესაძლოა არასრული იყოს.")
        if metadata.get("samplingMetadatas"):
            notes.append("Google-ის ანგარიში შერჩევით მონაცემებს იყენებს.")
    return list(dict.fromkeys(notes))


def _read(period):
    # Separate batches let traffic reports work even while custom search fields
    # are processing/unavailable in Google. Authentication is read-only.
    with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
        definitions = report_definitions(period)
        core = _batch(session, definitions)
        summary_rows, days, sources = [_rows(report, definition) for report, definition in zip(core, definitions)]
        summary = summary_rows[0] if summary_rows else dict.fromkeys(SUMMARY, 0)
        daily_by_date = {}
        try:
            for day in days:
                day_date = datetime.strptime(day["date"], "%Y%m%d").date()
                if not period.start <= day_date <= period.end or day_date.isoformat() in daily_by_date:
                    raise ValueError("Invalid day")
                daily_by_date[day_date.isoformat()] = day
        except (ValueError, KeyError):
            raise AnalyticsUnavailable() from None
        daily = []
        current = period.start
        while current <= period.end:
            values = daily_by_date.get(current.isoformat(), {})
            daily.append({"date": current.isoformat(), "sessions": values.get("sessions", 0), "users": values.get("totalUsers", 0)})
            current += timedelta(days=1)
        search = {"status": "unavailable", "total": None, "no_results": None, "terms": [], "row_count": 0}
        warnings = _warnings(core)
        try:
            definitions = report_definitions(period, search=True)
            search_reports = _batch(session, definitions)
            outcomes, terms = [_rows(report, definition) for report, definition in zip(search_reports, definitions)]
            # Never turn missing/unknown outcomes into apparent successful searches.
            if any(row["customEvent:search_outcome"] not in ("results", "no_results") for row in outcomes + terms):
                raise AnalyticsUnavailable()
            search = {"status": "ready", "total": sum(row["eventCount"] for row in outcomes),
                      "no_results": sum(row["eventCount"] for row in outcomes if row["customEvent:search_outcome"] == "no_results"),
                      "terms": [{"term": row["searchTerm"][:100], "outcome": row["customEvent:search_outcome"],
                                 "count": row["eventCount"], "average_results": row[SEARCH[1]]} for row in terms],
                      "row_count": int(search_reports[1].get("rowCount", len(terms)))}
            warnings.extend(_warnings(search_reports))
        except (AnalyticsUnavailable, ValueError, TypeError):
            search["message"] = "ძიების ანგარიში დროებით მიუწვდომელია. Google-ში ახალი ველების დამუშავებასაც შეიძლება დრო დასჭირდეს."
        status = "partial" if search["status"] != "ready" else "ready" if any(summary.values()) or search["total"] else "empty"
        return {"status": status, "fetched_at": timezone.now().isoformat(), "summary": summary,
                "daily": daily, "sources": [{"source": row["sessionSourceMedium"], "sessions": row["sessions"],
                                             "engaged_sessions": row["engagedSessions"]} for row in sources],
                "source_row_count": int(core[2].get("rowCount", len(sources))), "search": search,
                "warnings": list(dict.fromkeys(warnings)),
                "report_timezone": core[0].get("metadata", {}).get("timeZone")}


def build_analytics_report(period):
    base = {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "hostname": GA4_HOSTNAME, "property_id": GA4_PROPERTY_ID, "refresh_seconds": FRESH_SECONDS}
    raw, path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
    if not raw and not path:
        return {**base, "status": "not_configured", "fetched_at": None,
                "message": "Google Analytics-ის ნახვის უფლება მომზადებულია; სერვერის ავტორიზაცია ჯერ დასასრულებელია."}
    identity = sha256(f"{raw}\0{path}".encode()).hexdigest()[:16]
    key = f"business:ga4:v1:{GA4_PROPERTY_ID}:{GA4_HOSTNAME}:{identity}:{period.start}:{period.end}"
    fresh = cache.get(key)
    if fresh is not None:
        return {**base, **fresh}
    previous = cache.get(f"{key}:last")
    failure = cache.get(f"{key}:failure")
    if failure is None and cache.add(f"{key}:lock", True, timeout=40):
        try:
            payload = _read(period)
            cache.set(key, payload, timeout=FRESH_SECONDS)
            cache.set(f"{key}:last", payload, timeout=STALE_SECONDS)
            return {**base, **payload}
        except AnalyticsUnavailable as error:
            failure = error.code
            cache.set(f"{key}:failure", failure, timeout=RETRY_SECONDS)
        finally:
            cache.delete(f"{key}:lock")
    if previous is not None:
        payload = deepcopy(previous)
        payload.update(status="stale", message="Google-თან განახლება ვერ მოხერხდა. ნაჩვენებია ბოლო წარმატებით წამოღებული მონაცემები, ქვემოთ მითითებული დროით.")
        return {**base, **payload}
    messages = {
        "quota": "Google-ის მოთხოვნების ლიმიტი დროებით ამოიწურა. ცოტა ხანში სცადეთ ხელახლა.",
        "access": "Google-ის ანგარიშის წაკითხვა ვერ მოხერხდა. შესამოწმებელია სერვერის წვდომა და Analytics Data API.",
        "configuration_error": "Google-ის სერვერული ავტორიზაცია შესამოწმებელია.",
    }
    return {**base, "status": "unavailable", "fetched_at": None,
            "message": messages.get(failure, "Google-ის მონაცემები დროებით მიუწვდომელია ან ახლდება. სცადეთ ხელახლა.")}
