"""FlexDrive-only, read-only Meta reporting. Tokens never enter report payloads."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone as utc
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import requests

PAGE_ID = "1044408968766868"
IG_ID = "17841432881478668"
AD_ID = "1462913205812039"
GRAPH = "https://graph.facebook.com/v26.0/"
FRESH_SECONDS = 300
RETRY_SECONDS = 60
STALE_SECONDS = 86400
PURCHASE = "offsite_conversion.fb_pixel_purchase"
FB_METRICS = {"page_media_view": "views", "page_post_engagements": "interactions"}
IG_METRICS = ("reach", "views", "total_interactions")


class MetaUnavailable(Exception):
    def __init__(self, code="unavailable"):
        self.code = code


def _count(value):
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number != number.to_integral_value() or number > 2**53 - 1:
            raise ValueError()
        return int(number)
    except (ValueError, TypeError, InvalidOperation):
        raise MetaUnavailable("invalid_response") from None


def _money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError()
        return format(number.quantize(Decimal("0.01")), ".2f")
    except (ValueError, TypeError, InvalidOperation):
        raise MetaUnavailable("invalid_response") from None


def _get(session, node, params=None, *, token=None):
    try:
        response = session.get(GRAPH + node, params=params or {},
                               headers={"Authorization": "Bearer " + token} if token else None,
                               timeout=(3, 8), allow_redirects=False)
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError()
        if response.status_code != 200 or "error" in body:
            error = body.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
            raise MetaUnavailable("access" if code in (10, 102, 190, 200) or response.status_code in (401, 403)
                                  else "quota" if code in (4, 17, 32, 613, 80001, 80002, 80004) or response.status_code == 429
                                  else "unavailable")
        return body
    except MetaUnavailable:
        raise
    except (requests.RequestException, ValueError, TypeError):
        # Provider errors/URLs can contain tokens; never forward or log them.
        raise MetaUnavailable() from None


def _data(body):
    value = body.get("data")
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise MetaUnavailable("invalid_response")
    return value


def _session(token):
    session = requests.Session()
    session.headers.update({"Authorization": "Bearer " + token})
    return session


def _facebook_profile(token):
    with _session(token) as session:
        body = _get(session, PAGE_ID, {"fields": "id,name,followers_count,instagram_business_account"})
    if body.get("id") != PAGE_ID or body.get("instagram_business_account", {}).get("id") != IG_ID:
        raise MetaUnavailable("configuration_error")
    return {"name": str(body.get("name", "FlexDrive"))[:150], "followers": _count(body.get("followers_count"))}


def _instagram_profile(token):
    with _session(token) as session:
        body = _get(session, IG_ID, {"fields": "id,username,followers_count,media_count"})
    if body.get("id") != IG_ID or body.get("username") != "flexdrive.ge":
        raise MetaUnavailable("configuration_error")
    return {"username": "flexdrive.ge", "followers": _count(body.get("followers_count")),
            "posts": _count(body.get("media_count"))}


def _facebook_activity(token, period):
    with _session(token) as session:
        # A derived Page token is transient and never cached/saved/returned.
        page = _get(session, PAGE_ID, {"fields": "id,access_token"})
        page_token = page.get("access_token")
        if page.get("id") != PAGE_ID or not isinstance(page_token, str) or not page_token:
            raise MetaUnavailable("access")
        body = _get(session, PAGE_ID + "/insights", {
            "metric": ",".join(FB_METRICS), "period": "day", "since": period.start.isoformat(),
            "until": (period.end + timedelta(days=1)).isoformat(),
        }, token=page_token)
    metrics = _data(body)
    if {row.get("name") for row in metrics} != set(FB_METRICS) or len(metrics) != len(FB_METRICS):
        raise MetaUnavailable("missing_metrics")
    result = {}
    coverage = []
    for metric in metrics:
        values = metric.get("values")
        if metric.get("period") != "day" or not isinstance(values, list) or not values:
            raise MetaUnavailable("missing_metrics")
        days = {}
        for row in values:
            try:
                end = datetime.fromisoformat(row["end_time"])
                if end.tzinfo is None:
                    raise ValueError()
                # Label Meta's reporting day; do not reassign it to Tbilisi.
                day = end.date() - timedelta(days=1)
                if period.start <= day <= period.end:
                    if day in days:
                        raise ValueError()
                    days[day] = _count(row["value"])
            except (KeyError, TypeError, ValueError):
                raise MetaUnavailable("invalid_response") from None
        if not days:
            raise MetaUnavailable("missing_metrics")
        result[FB_METRICS[metric["name"]]] = sum(days.values())
        coverage.append(len(days))
    expected = (period.end - period.start).days + 1
    return {**result, "reported_days": min(coverage), "complete": all(count == expected for count in coverage)}


def _instagram_activity(token, period):
    with _session(token) as session:
        body = _get(session, IG_ID + "/insights", {
            "metric": ",".join(IG_METRICS), "period": "day", "metric_type": "total_value",
            "since": int(datetime.combine(period.start, time.min, utc.utc).timestamp()),
            "until": int(datetime.combine(period.end + timedelta(days=1), time.min, utc.utc).timestamp()),
        })
    rows = _data(body)
    if {row.get("name") for row in rows} != set(IG_METRICS) or len(rows) != len(IG_METRICS):
        raise MetaUnavailable("missing_metrics")
    try:
        return {row["name"]: _count(row["total_value"]["value"]) for row in rows}
    except (KeyError, TypeError):
        raise MetaUnavailable("invalid_response") from None


def _action(row, key, *, money=False):
    values = row.get(key, [])
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise MetaUnavailable("invalid_response")
    found = [value for value in values if value.get("action_type") == PURCHASE]
    if len(found) > 1:
        raise MetaUnavailable("invalid_response")
    value = found[0].get("value") if found else 0
    # Attribution can return fractional modeled conversions: preserve them.
    return _money(value) if money else _attributed_count(value)


def _attributed_count(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError()
        return format(number, "f")
    except (ValueError, TypeError, InvalidOperation):
        raise MetaUnavailable("invalid_response") from None


def _ad_values(row):
    return {"spend": _money(row.get("spend")), "impressions": _count(row.get("impressions")),
            "clicks": _count(row.get("clicks")), "reach": _count(row.get("reach")),
            "website_purchases": _action(row, "actions"), "website_purchase_value": _action(row, "action_values", money=True)}


def _ads(token, period):
    fields = "spend,impressions,clicks,reach,actions,action_values"
    params = {"fields": fields, "time_range": json.dumps({"since": period.start.isoformat(), "until": period.end.isoformat()}),
              "action_attribution_windows": json.dumps(["7d_click", "1d_view"]), "action_report_time": "conversion", "limit": 1000}
    node = "act_" + AD_ID
    with _session(token) as session:
        account = _get(session, node, {"fields": "id,name,currency,timezone_name"})
        if account.get("id") != node or not re.fullmatch(r"[A-Z]{3}", str(account.get("currency", ""))):
            raise MetaUnavailable("configuration_error")
        try:
            ZoneInfo(account["timezone_name"])
        except (KeyError, ValueError, TypeError):
            raise MetaUnavailable("configuration_error") from None
        summary_body = _get(session, node + "/insights", params)
        summaries = _data(summary_body)
        if len(summaries) > 1 or summary_body.get("paging", {}).get("next"):
            raise MetaUnavailable("invalid_response")
        summary = _ad_values(summaries[0]) if summaries else _ad_values({"spend": 0, "impressions": 0, "clicks": 0, "reach": 0})
        if summaries and (summaries[0].get("date_start") != period.start.isoformat() or summaries[0].get("date_stop") != period.end.isoformat()):
            raise MetaUnavailable("invalid_response")
        daily_body = _get(session, node + "/insights", {**params, "time_increment": 1})
        if daily_body.get("paging", {}).get("next"):
            raise MetaUnavailable("invalid_response")
        daily_by_date = {}
        for row in _data(daily_body):
            day = row.get("date_start")
            try:
                parsed_day = date.fromisoformat(day)
            except (ValueError, TypeError):
                raise MetaUnavailable("invalid_response") from None
            if (not period.start <= parsed_day <= period.end
                    or row.get("date_stop") != day or day in daily_by_date):
                raise MetaUnavailable("invalid_response")
            daily_by_date[day] = {"date": day, **_ad_values(row)}
        if not summaries and daily_by_date:
            raise MetaUnavailable("invalid_response")
        # Successful empty ad days really have no reported activity; counts are
        # filled only after a valid provider response, never after a failed call.
        daily = []
        day = period.start
        while day <= period.end:
            daily.append(daily_by_date.get(day.isoformat(), {"date": day.isoformat(), "spend": "0.00", "impressions": 0, "clicks": 0,
                         "reach": 0, "website_purchases": "0", "website_purchase_value": "0.00"}))
            day += timedelta(days=1)
        campaigns, seen, cursors, limited = [], set(), set(), False
        campaign_params = {**params, "fields": "campaign_id,campaign_name," + fields, "level": "campaign", "limit": 100}
        for page in range(3):
            body = _get(session, node + "/insights", campaign_params)
            rows = _data(body)
            if len(rows) > 100:
                raise MetaUnavailable("invalid_response")
            for row in rows:
                identifier = str(row.get("campaign_id", ""))
                if (not identifier.isdigit() or identifier in seen or row.get("date_start") != period.start.isoformat()
                        or row.get("date_stop") != period.end.isoformat()):
                    raise MetaUnavailable("invalid_response")
                seen.add(identifier)
                campaigns.append({"id": identifier, "name": str(row.get("campaign_name", ""))[:200], **_ad_values(row)})
            paging = body.get("paging", {})
            if not paging.get("next"):
                break
            if page == 2:
                limited = True
                break
            cursor = paging.get("cursors", {}).get("after")
            if not isinstance(cursor, str) or not cursor or len(cursor) > 2048 or cursor in cursors:
                raise MetaUnavailable("invalid_response")
            cursors.add(cursor)
            # Never follow provider next URLs: they can embed tokens/other hosts.
            campaign_params = {**campaign_params, "after": cursor}
        if not summaries and campaigns:
            raise MetaUnavailable("invalid_response")
    campaigns.sort(key=lambda row: Decimal(row["spend"]), reverse=True)
    return {"status": "ready" if summaries else "empty", "currency": account["currency"],
            "timezone": account["timezone_name"], "summary": summary, "daily": daily,
            "campaigns": campaigns, "campaigns_limited": limited}


MESSAGES = {
    "access": "Meta-ს წვდომა შესამოწმებელია: გასაღები ან სტატისტიკის ნახვის უფლება.",
    "quota": "Meta-ს მოთხოვნების ლიმიტი დროებით ამოიწურა. ცოტა ხანში სცადეთ ხელახლა.",
    "configuration_error": "FlexDrive-ის ანგარიშების კავშირი შესამოწმებელია.",
    "missing_metrics": "Meta-მ ამ მაჩვენებლებისთვის რიცხვები არ დააბრუნა. ეს ნულს არ ნიშნავს.",
}


def _cached(key, reader):
    fresh = cache.get(key)
    if fresh is not None:
        return fresh
    last, failure = cache.get(key + ":last"), cache.get(key + ":failure")
    if failure is None and cache.add(key + ":lock", True, timeout=90):
        try:
            result = reader()
            payload = {"status": "ready", "fetched_at": timezone.now().isoformat(), **result}
            cache.set(key, payload, FRESH_SECONDS)
            cache.set(key + ":last", payload, STALE_SECONDS)
            return payload
        except (MetaUnavailable, KeyError, TypeError, ValueError, AttributeError) as error:
            failure = error.code if isinstance(error, MetaUnavailable) else "invalid_response"
            cache.set(key + ":failure", failure, RETRY_SECONDS)
        finally:
            cache.delete(key + ":lock")
    if last is not None:
        payload = deepcopy(last)
        return {**payload, "status": "stale", "message": "განახლება ვერ მოხერხდა. ნაჩვენებია ბოლო მიღებული მონაცემები მითითებული დროით."}
    return {"status": "unavailable", "fetched_at": None, "message": MESSAGES.get(failure, "Meta-ს მონაცემები დროებით მიუწვდომელია ან ახლდება.")}


def build_marketing_report(period):
    base = {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()}, "refresh_seconds": FRESH_SECONDS,
            "accounts": {"facebook": PAGE_ID, "instagram": IG_ID, "ads": AD_ID}, "generated_at": timezone.now().isoformat()}
    token = settings.BUSINESS_META_ACCESS_TOKEN
    if not token:
        return {**base, "status": "not_configured", "message": "Meta-ს სერვერული გასაღები ამ გარემოში ჯერ არ არის მითითებული."}
    identity = sha256(token.encode()).hexdigest()[:16]
    root = f"business:meta:v1:{identity}"
    days = (period.end - period.start).days + 1
    def read(name, fn, *, maximum=None, profile=False):
        if maximum and days > maximum:
            return {"status": "range_limit", "fetched_at": None,
                    "message": f"ამ სტატისტიკისთვის აირჩიეთ მაქსიმუმ {maximum} დღე. გამომწერების მიმდინარე რაოდენობა პერიოდზე არ არის დამოკიდებული."}
        key = f"{root}:{name}" + ("" if profile else f":{period.start}:{period.end}")
        return _cached(key, fn)
    # Independent providers/sections: one failure cannot hide the others.
    tasks = [
        ("facebook_profile", lambda: read("facebook_profile", lambda: _facebook_profile(token), profile=True)),
        ("facebook_activity", lambda: read("facebook_activity", lambda: _facebook_activity(token, period), maximum=90)),
        ("instagram_profile", lambda: read("instagram_profile", lambda: _instagram_profile(token), profile=True)),
        ("instagram_activity", lambda: read("instagram_activity", lambda: _instagram_activity(token, period), maximum=30)),
        ("ads", lambda: read("ads", lambda: _ads(token, period))),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        values = dict(zip((name for name, _ in tasks), pool.map(lambda task: task[1](), tasks)))
    blocks = list(values.values())
    successful = [block for block in blocks if block["status"] in ("ready", "empty", "stale")]
    status = "ready" if all(block["status"] in ("ready", "empty") for block in blocks) else "partial" if successful else "unavailable"
    return {**base, "status": status,
            "facebook": {"profile": values["facebook_profile"], "activity": values["facebook_activity"]},
            "instagram": {"profile": values["instagram_profile"], "activity": values["instagram_activity"]}, "ads": values["ads"]}
