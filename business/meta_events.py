"""Read-only, allowlisted dataset event counts. Browser and server are never added."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from hashlib import sha256

from django.conf import settings
from django.utils import timezone

from .marketing import PIXEL_ID, EVENTS_MANAGER_URL, MetaUnavailable, _cached, _count, _data, _get, _session
from .reports import TBILISI

EVENTS = {
    "ViewContent": "პროდუქტის ნახვა", "AddToCart": "კალათაში დამატება",
    "InitiateCheckout": "გაფორმების დაწყება", "Purchase": "შეძენის მოვლენა",
    "PageView": "გვერდის ნახვა", "Search": "ძებნა", "AddToWishlist": "სურვილების სიაში დამატება",
    "AddPaymentInfo": "გადახდის ინფორმაციის დამატება", "Contact": "დაკავშირება",
}
SOURCES = {"browser": "WEB_ONLY", "server": "SERVER_ONLY"}


def _read_source(token, period, source):
    lower, upper = period.bounds
    upper = min(upper, timezone.now())
    counts = dict.fromkeys(EVENTS, 0)
    daily, day = {}, period.start
    while day <= period.end:
        daily[str(day)] = dict.fromkeys(EVENTS, 0)
        day += timedelta(days=1)
    params = {"aggregation": "event", "event_source": SOURCES[source],
              "start_time": int(lower.timestamp()), "end_time": int(upper.timestamp()), "limit": 200}
    cursors, hours = set(), set()
    with _session(token) as session:
        for page in range(3):
            body = _get(session, PIXEL_ID + "/stats", params)
            rows = _data(body)
            if len(rows) > 200:
                raise MetaUnavailable("invalid_response")
            for row in rows:
                if row.get("aggregation") != "event":
                    raise MetaUnavailable("invalid_response")
                try:
                    at = datetime.fromisoformat(row["start_time"].replace("Z", "+00:00"))
                except (KeyError, ValueError, TypeError, AttributeError):
                    raise MetaUnavailable("invalid_response") from None
                if at.tzinfo is None or not lower <= at < upper or at in hours:
                    raise MetaUnavailable("invalid_response")
                hours.add(at)
                entries = _data(row)
                if len(entries) > 100:
                    raise MetaUnavailable("invalid_response")
                seen = set()
                for entry in entries:
                    event = entry.get("event") or entry.get("value")
                    if not isinstance(event, str) or event not in EVENTS:
                        continue  # Never expose custom event labels or fields.
                    if event in seen:
                        raise MetaUnavailable("invalid_response")
                    seen.add(event)
                    count = _count(entry.get("count"))
                    counts[event] = _count(counts[event] + count)
                    daily[str(at.astimezone(TBILISI).date())][event] += count
            paging = body.get("paging", {})
            if not isinstance(paging, dict):
                raise MetaUnavailable("invalid_response")
            if not paging.get("next"):
                break
            cursor = paging.get("cursors", {}).get("after")
            if page == 2 or not isinstance(cursor, str) or not cursor or len(cursor) > 2048 or cursor in cursors:
                raise MetaUnavailable("invalid_response")
            cursors.add(cursor)
            params = {**params, "after": cursor}  # Do not follow provider next URLs.
    for values in daily.values():
        _count(sum(values.values()))
    return {"status": "ready" if any(counts.values()) else "empty", "counts": counts, "daily": daily}


def build_meta_events_report(period):
    today = timezone.now().astimezone(TBILISI).date()
    base = {"source": "meta", "pixel_id": PIXEL_ID, "events_manager_url": EVENTS_MANAGER_URL,
            "period": {"start": str(period.start), "end": str(period.end)}, "timezone": "Asia/Tbilisi",
            "scope": "entire_dataset", "refresh_seconds": 300, "generated_at": timezone.now().isoformat()}
    if period.start < today - timedelta(days=6) or period.end > today:
        return {**base, "status": "range_limit", "message": "ეს ანგარიში ბოლო 7 დღის მოვლენებს კითხულობს. აირჩიეთ ამ მონაკვეთში მოქცეული დღეები."}
    token = settings.BUSINESS_META_ACCESS_TOKEN
    if not token:
        return {**base, "status": "not_configured", "message": "Meta-ს ანგარიშის წაკითხვის გასაღები მითითებული არ არის."}
    identity = sha256(token.encode()).hexdigest()[:16]
    def read(source):
        return _cached(f"business:meta-events:v1:{identity}:{source}:{period.start}:{period.end}",
                       lambda: _read_source(token, period, source))
    with ThreadPoolExecutor(max_workers=2) as pool:
        sources = dict(zip(SOURCES, pool.map(read, SOURCES)))
    available = {key: value for key, value in sources.items() if value["status"] in ("ready", "empty", "stale")}
    ready = all(value["status"] in ("ready", "empty") for value in sources.values())
    rows = [{"event": event, "label": label,
             **{source: available[source]["counts"][event] if source in available else None for source in SOURCES}}
            for event, label in EVENTS.items()]
    daily, day = [], period.start
    while day <= period.end:
        daily.append({"date": str(day), **{source: sum(available[source]["daily"][str(day)].values())
                      if source in available else None for source in SOURCES}})
        day += timedelta(days=1)
    return {**base, "status": "ready" if ready else "partial" if available else "unavailable",
            "sources": sources, "rows": rows, "daily": daily}
