"""Local service availability and conservative dispatch estimates, in Tbilisi time."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .delivery_quote_data import DeliveryQuoteError


TBILISI = ZoneInfo("Asia/Tbilisi")
SERVICES = {"standard": (1, "სტანდარტული მიტანა"), "fast": (2, "სწრაფი მიტანა")}
MONTHS = ("იანვარი", "თებერვალი", "მარტი", "აპრილი", "მაისი", "ივნისი", "ივლისი",
          "აგვისტო", "სექტემბერი", "ოქტომბერი", "ნოემბერი", "დეკემბერი")
WEEKDAYS = ("ორშაბათი", "სამშაბათი", "ოთხშაბათი", "ხუთშაბათი", "პარასკევი", "შაბათი", "კვირა")


def working_days(day, count):
    step = 1 if count >= 0 else -1
    remaining = abs(count)
    while remaining:
        day += timedelta(days=step)
        if day.weekday() < 5:
            remaining -= 1
    return day


def date_label(day, *, today=None):
    prefix = "დღეს" if day == today else WEEKDAYS[day.weekday()]
    return f"{prefix}, {day.day} {MONTHS[day.month - 1]}"


def service_policy(group, service, *, now=None):
    now = (now or timezone.now()).astimezone(TBILISI)
    minutes = settings.WINGO_PREPARATION_MINUTES
    if type(minutes) is not int or not 0 <= minutes <= 240:
        raise DeliveryQuoteError("მიწოდების მომზადების დრო შესამოწმებელია.", code="delivery_configuration_invalid", status_code=503)
    if service not in SERVICES:
        raise DeliveryQuoteError("მიწოდების ტიპი არასწორია.", code="delivery_service_invalid")
    delivery_type, label = SERVICES[service]
    result = {"service_slug": service, "delivery_type_id": delivery_type, "label": label,
              "available": True, "unavailable_reason": "", "estimated_delivery_date": None,
              "estimate_label": "3–5 სამუშაო დღეში, მარშრუტის გრაფიკის მიხედვით",
              "booking_deadline_at": None, "checkout_deadline_at": None}
    if group != "tbilisi":
        if service == "fast":
            result.update(available=False, unavailable_reason="სწრაფი მიტანა მხოლოდ თბილისშია ხელმისაწვდომი.")
        return result
    cutoff = datetime.combine(now.date(), time(13), TBILISI)
    checkout_cutoff = cutoff - timedelta(minutes=minutes)
    if service == "fast":
        same_day = now.weekday() < 5 and now < checkout_cutoff
        delivery_day = now.date() if same_day else working_days(now.date(), 1)
        deadline = datetime.combine(delivery_day, time(13), TBILISI)
        estimate = (date_label(delivery_day, today=now.date()) if same_day else
                    f"მომდევნო სამუშაო დღეს — {date_label(delivery_day)}")
        result.update(estimated_delivery_date=delivery_day.isoformat(), estimate_label=estimate,
                      booking_deadline_at=deadline.isoformat(),
                      checkout_deadline_at=(deadline - timedelta(minutes=minutes)).isoformat())
        return result
    ready = now + timedelta(minutes=minutes)
    if ready.weekday() >= 5:
        ready = datetime.combine(working_days(ready.date(), 1), time.min, TBILISI)
    delivery_day = working_days(ready.date(), 1 if ready.time() < time(13) else 2)
    deadline = datetime.combine(working_days(delivery_day, -1), time(13), TBILISI)
    result.update(estimated_delivery_date=delivery_day.isoformat(), estimate_label="1–2 სამუშაო დღეში",
                  booking_deadline_at=deadline.isoformat(),
                  checkout_deadline_at=(deadline - timedelta(minutes=minutes)).isoformat())
    return result


def delivery_summary(order):
    if order.delivery_provider != "wingo" or order.delivery_service_slug not in SERVICES:
        return None
    schedule = order.delivery_provider_data.get("schedule", {})
    return {"service_slug": order.delivery_service_slug, "label": SERVICES[order.delivery_service_slug][1],
            "estimated_delivery_date": schedule.get("estimated_delivery_date"),
            "estimate_label": schedule.get("estimate_label", "")}


def booking_deadline(order):
    raw = order.delivery_provider_data.get("schedule", {}).get("booking_deadline_at")
    if not raw:
        return None
    try:
        deadline = parse_datetime(raw)
    except (ValueError, TypeError):
        deadline = None
    if deadline is None or timezone.is_naive(deadline):
        raise DeliveryQuoteError("შეკვეთის მიწოდების ვადა არასწორია.", code="delivery_schedule_invalid")
    return deadline
