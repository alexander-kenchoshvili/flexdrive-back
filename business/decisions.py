"""Private decision reports. Fixed accounts, read-only APIs, no ledger writes."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re

from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

from .analytics import AnalyticsUnavailable, _batch, _credentials, _filter, _warnings
from .ga4 import GA4_PROPERTY_ID, build_ga4_report_request
from .marketing import MetaUnavailable, _ads, _cached
from .reports import previous_period

FUNNEL_URL = f"https://analyticsdata.googleapis.com/v1alpha/properties/{GA4_PROPERTY_ID}:runFunnelReport"
STEPS = (("view_item", "პროდუქტი ნახა"), ("begin_checkout", "გადახდა დაიწყო"), ("purchase", "იყიდა"))
CART_STEPS = (STEPS[0], ("add_to_cart", "კალათაში დაამატა"), *STEPS[1:])
FUNNEL_PATHS = {"all": ("ყველა გზა", STEPS, None),
                "cart": ("კალათით", CART_STEPS, r"https://flexdrive\.ge/checkout/?(\?.*)?"),
                "buy_now": ("ახლავე ყიდვით", STEPS, r"https://flexdrive\.ge/buy-now/checkout/?(\?.*)?")}
METRICS = ("sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue")
PUBLIC = {"notExpression": _filter("pagePath", r"^/(business|admin|manager-fd)(/|$)", "PARTIAL_REGEXP")}


def definitions(period):
    old = previous_period(period)
    specs = [(period, (), METRICS), (old, (), METRICS),
             (period, ("sessionSourceMedium", "sessionCampaignName"), METRICS)]
    result = []
    for index, (dates, dimensions, metrics) in enumerate(specs):
        body = build_ga4_report_request(dates, dimensions, metrics, dimension_filter=PUBLIC)
        body["limit"] = "30" if index == 2 else "1"
        if index == 2:
            body["orderBys"] = [{"metric": {"metricName": "ecommercePurchases"}, "desc": True},
                                {"metric": {"metricName": "sessions"}, "desc": True}]
        result.append(body)
    return result


def _rows(report, definition):
    dims = [item["name"] for item in definition["dimensions"]]
    metrics = [item["name"] for item in definition["metrics"]]
    # Google omits headers only for a successful empty dimensionless report.
    if (not dims and not report.get("metricHeaders") and not report.get("dimensionHeaders")
            and not report.get("rows") and report.get("rowCount", 0) == 0
            and report.get("kind") == "analyticsData#runReport" and isinstance(report.get("metadata"), dict)):
        return []
    if ([item["name"] for item in report.get("dimensionHeaders", [])] != dims
            or [item["name"] for item in report["metricHeaders"]] != metrics):
        raise ValueError("Unexpected headers")
    result = []
    for row in report.get("rows", []):
        dimensions, values = row.get("dimensionValues", []), row["metricValues"]
        if len(dimensions) != len(dims) or len(values) != len(metrics):
            raise ValueError("Invalid row")
        parsed = dict(zip(dims, (str(item["value"])[:200] for item in dimensions)))
        for key, item in zip(metrics, values):
            number = Decimal(item["value"])
            if not number.is_finite() or number < 0 or number > 2**53 - 1:
                raise ValueError("Invalid metric")
            if key == "purchaseRevenue":
                parsed[key] = format(number, "f")
            elif number == number.to_integral_value():
                parsed[key] = int(number)
            else:
                raise ValueError("Invalid count")
        result.append(parsed)
    if len(result) > int(definition["limit"]):
        raise ValueError("Too many rows")
    return result


def _google(period):
    specs = definitions(period)
    with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
        reports = _batch(session, specs)
    current, previous, sources = [_rows(report, spec) for report, spec in zip(reports, specs)]
    zero = dict.fromkeys(METRICS, 0)
    for report in reports:
        currency = report.get("metadata", {}).get("currencyCode")
        if currency and currency != "GEL":
            raise ValueError("Unexpected currency")
    if reports[0].get("metadata", {}).get("timeZone") != reports[1].get("metadata", {}).get("timeZone"):
        raise ValueError("Incompatible timezones")
    return {"current": current[0] if current else zero, "previous": previous[0] if previous else zero,
            "sources": sources, "source_row_count": int(reports[2].get("rowCount", len(sources))),
            "currency": "GEL", "timezone": reports[0].get("metadata", {}).get("timeZone"),
            "warnings": _warnings(reports)}


def funnel_request(period, path="all"):
    base = build_ga4_report_request(period, (), (), dimension_filter=PUBLIC)
    _, steps, checkout_path = FUNNEL_PATHS[path]
    filters = []
    for event, _ in steps:
        expression = {"funnelEventFilter": {"eventName": event}}
        if event == "begin_checkout" and checkout_path:
            expression = {"andGroup": {"expressions": [expression, {"funnelFieldFilter": {
                "fieldName": "pageLocation", "stringFilter": {"matchType": "FULL_REGEXP", "value": checkout_path}}}]}}
        filters.append({"name": event, "isDirectlyFollowedBy": False, "filterExpression": expression})
    return {"dateRanges": base["dateRanges"], "dimensionFilter": base["dimensionFilter"],
            "limit": str(len(steps)), "returnPropertyQuota": True,
            "funnel": {"isOpenFunnel": False, "steps": filters}}


def parse_funnel(body, path="all"):
    _, steps, _ = FUNNEL_PATHS[path]
    if body.get("kind") != "analyticsData#runFunnelReport":
        raise ValueError("Invalid funnel")
    report = body["funnelVisualization"]
    metrics = [h["name"] for h in report["metricHeaders"]]
    if ([h["name"] for h in report["dimensionHeaders"]] != ["funnelStepName"]
            or metrics not in (["activeUsers"], ["activeUsers", "activeUsers"])):
        raise ValueError("Unexpected funnel headers")
    # v1alpha duplicates the header for our single date range, sometimes with
    # only one value. Accept only this exact duplication; never truncate values.
    counts = {}
    for row in report.get("rows", []):
        if len(row["dimensionValues"]) != 1 or len(row["metricValues"]) not in (1, len(metrics)):
            raise ValueError("Invalid funnel row")
        label = row["dimensionValues"][0]["value"]
        event = re.sub(r"^\d+\.\s*", "", label)
        number = Decimal(row["metricValues"][0]["value"])
        if any(Decimal(item["value"]) != number for item in row["metricValues"]):
            raise ValueError("Ambiguous funnel metrics")
        if event not in dict(steps) or event in counts or not number.is_finite() or number < 0 or number > 2**53 - 1 or number != number.to_integral_value():
            raise ValueError("Invalid funnel count")
        counts[event] = int(number)
    # Omitted rows in a nonempty alpha report are unknown, not invented zeros.
    values = [counts.get(event) if counts else 0 for event, _ in steps]
    known = [value for value in values if value is not None]
    if any(right > left for left, right in zip(known, known[1:])):
        raise ValueError("Closed funnel cannot grow")
    warnings = _warnings([report, body.get("funnelTable", {})])
    if any(value is None for value in values):
        warnings.append("Google-მა ყველა ეტაპის სტრიქონი არ დააბრუნა. გამოტოვებული ეტაპი ნაჩვენებია ტირეთი; მას ნულად არ ვთვლით.")
    return {"steps": [{"event": event, "label": label, "users": count,
                       "lost": count - values[index + 1] if index < len(steps) - 1 and count is not None and values[index + 1] is not None else None}
                      for index, ((event, label), count) in enumerate(zip(steps, values))], "warnings": warnings}


def _funnel(period):
    with AuthorizedSession(_credentials(), refresh_timeout=5, max_refresh_attempts=0) as session:
        paths = {}
        for path, (label, _, _) in FUNNEL_PATHS.items():
            try:
                response = session.post(FUNNEL_URL, json=funnel_request(period, path), timeout=(3, 8),
                                        max_allowed_time=15, allow_redirects=False)
                if response.status_code != 200:
                    raise AnalyticsUnavailable("quota" if response.status_code == 429 else "access")
                paths[path] = {"status": "ready", "label": label, **parse_funnel(response.json(), path)}
            except (AnalyticsUnavailable, RequestException, GoogleAuthError, InvalidOperation, ValueError, KeyError, TypeError):
                paths[path] = {"status": "unavailable", "label": label,
                               "message": "ამ გზის ანგარიში ვერ მივიღეთ. ეს ნულოვან შედეგს არ ნიშნავს."}
        if not any(item["status"] == "ready" for item in paths.values()):
            raise AnalyticsUnavailable()
        return {"steps": paths["all"].get("steps"), "warnings": paths["all"].get("warnings", []), "paths": paths}


def _safe_google(reader):
    try:
        return reader()
    except (AnalyticsUnavailable, RequestException, GoogleAuthError, InvalidOperation) as error:
        raise MetaUnavailable(error.code if isinstance(error, AnalyticsUnavailable) else "unavailable") from None


def build_decision_report(period, source="all"):
    old = previous_period(period)
    result = {"period": {"start": str(period.start), "end": str(period.end)},
              "previous_period": {"start": str(old.start), "end": str(old.end)}, "refresh_seconds": 300}
    tasks = []
    if source in ("all", "google"):
        raw, path = settings.BUSINESS_GA4_CREDENTIALS_JSON, settings.BUSINESS_GA4_CREDENTIALS_FILE
        if raw or path:
            identity = sha256(f"{raw}\0{path}".encode()).hexdigest()[:16]
            root = f"business:decisions:ga4:v2:{identity}:{period.start}:{period.end}"
            tasks.extend([("google", lambda: _cached(root + ":core", lambda: _safe_google(lambda: _google(period)))),
                          ("funnel", lambda: _cached(root + ":funnel", lambda: _safe_google(lambda: _funnel(period))))])
        else:
            result.update(google={"status": "not_configured"}, funnel={"status": "not_configured"})
    if source in ("all", "meta"):
        token = settings.BUSINESS_META_ACCESS_TOKEN
        if token:
            identity = sha256(token.encode()).hexdigest()[:16]
            # Reuse the existing Ads cache; never re-read social data for comparisons.
            def ads(dates):
                return _cached(f"business:meta:v1:{identity}:ads:{dates.start}:{dates.end}", lambda: _ads(token, dates))
            tasks.extend([("ads", lambda: ads(period)), ("previous_ads", lambda: ads(old))])
        else:
            result.update(ads={"status": "not_configured"}, previous_ads={"status": "not_configured"})
    with ThreadPoolExecutor(max_workers=3) as pool:
        result.update(zip((name for name, _ in tasks), pool.map(lambda task: task[1](), tasks)))
    for name in ("google", "funnel"):
        if result.get(name, {}).get("status") == "unavailable":
            result[name]["message"] = "Google-ის ანგარიში დროებით მიუწვდომელია. წვდომა, მონაცემების დამუშავება ან მოთხოვნების ლიმიტი შესამოწმებელია; ეს ნულოვან შედეგს არ ნიშნავს."
    return result
