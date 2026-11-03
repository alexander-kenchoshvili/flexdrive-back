"""Leased batch reads. Observation times are not carrier event timestamps."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Order, OrderReturn, RedcapReferenceData, RedcapShipment, RedcapSyncReport
from .redcap import RedcapClient, RedcapError


class RedcapTrackingError(RedcapError):
    pass


STATUS_TARGETS = {
    "registered": None, "pending_pickup": "processing", "picked_up": "shipped",
    "in_warehouse": "shipped", "mzadaa_gasatanad": "shipped", "sawyobidan_gatanilia": "shipped",
    "gagzavnilia_regionshi": "shipped", "out_for_delivery": "shipped", "delivered": "delivered",
    "molodinis_rezhimshi": None, "postponed": None, "unreachable": None,
    "refused": None, "ukan_dabrunebuli": None, "cancelled": None,
}
ORDER_RANK = {"new": 0, "confirmed": 1, "processing": 2, "shipped": 3, "delivered": 4}
ATTENTION = {"molodinis_rezhimshi", "postponed", "unreachable", "refused", "ukan_dabrunebuli", "cancelled"}


def parse_status_batch(payload, requested):
    if (not isinstance(payload, dict) or payload.get("success") is not True
            or not isinstance(payload.get("orders"), list) or len(payload["orders"]) > 1000):
        raise RedcapTrackingError("RedCap-ის სტატუსების პასუხი არასწორია.")
    result = dict.fromkeys(requested)
    seen = set()
    for row in payload["orders"]:
        if not isinstance(row, dict):
            raise RedcapTrackingError("RedCap-ის სტატუსების ჩანაწერი არასწორია.")
        number = row.get("tracking_number")
        if not isinstance(number, str) or number not in result or number in seen or type(row.get("found")) is not bool:
            raise RedcapTrackingError("RedCap-ის თრექინგების შესაბამისობა ვერ დადასტურდა.")
        seen.add(number)
        if row["found"]:
            status = row.get("status")
            if not isinstance(status, str) or not status or len(status) > 80:
                raise RedcapTrackingError("RedCap-ის სტატუსი არასწორია.")
            result[number] = status
    return result


def due_shipments(before):
    snapshot = RedcapReferenceData.objects.filter(pk=1).first()
    finals = [row["key"] for row in snapshot.statuses if row["is_final"]] if snapshot else []
    return RedcapShipment.objects.filter(
        order__delivery_provider="redcap", state__in=["created", "cancel_unknown", "cancelling"],
        tracking_number__isnull=False,
    ).exclude(tracking_number="").exclude(carrier_status__in=finals).filter(
        Q(tracking_attempted_at__isnull=True) | Q(tracking_attempted_at__lte=before)
    )


def _apply(shipment_id, number, token, status, metadata):
    with transaction.atomic():
        order_id = RedcapShipment.objects.values_list("order_id", flat=True).get(pk=shipment_id)
        order = Order.objects.select_for_update().get(pk=order_id)
        shipment = RedcapShipment.objects.select_for_update().get(pk=shipment_id)
        if shipment.tracking_token != token or shipment.tracking_number != number or order.delivery_provider != "redcap":
            return "skipped", None
        before = shipment.carrier_status
        detail = {"order_id": order.pk, "order_number": order.order_number,
                  "carrier_before": before, "order_before": order.status}
        now = timezone.now()
        history = list(shipment.tracking_history)
        if not history or history[-1].get("status") != status:
            history.append({"status": status, "observed_at": now.isoformat()})
        shipment.tracking_history = history[-1000:]
        shipment.tracking_checked_at = now
        issue = ""
        if metadata.get(before, {}).get("is_final") and before != status:
            issue = "სტატუსი ეწინააღმდეგება უკვე საბოლოო მდგომარეობას. გადაამოწმეთ."
        else:
            shipment.carrier_status = status
            if status not in metadata or status not in STATUS_TARGETS:
                issue = "უცნობი საკურიერო სტატუსია. შეკვეთა არ შეცვლილა."
            elif shipment.state in {"created", "cancel_unknown", "cancelling"} and status == "cancelled":
                shipment.state = "cancelled"
                shipment.last_error = ""
                issue = "RedCap-ის გზავნილი გაუქმებულია. შეკვეთის გაუქმება და თანხის დაბრუნება ცალკე დასადასტურებელია."
            elif shipment.state != "created":
                issue = "გაუქმების მდგომარეობა შესამოწმებელია. შეკვეთა არ შეცვლილა."
            elif status in ATTENTION:
                issue = "საკურიერო გზავნილს ოპერატორის ყურადღება სჭირდება. თანხა და მარაგი არ შეცვლილა."
            elif order.status == "cancelled" or order.payment_status != "paid" or OrderReturn.objects.filter(order=order).exists():
                issue = "შეკვეთის გადახდა/დაბრუნება შესამოწმებელია; მიწოდების პროგრესი არ შეცვლილა."
            else:
                target = STATUS_TARGETS[status]
                if target and ORDER_RANK[target] > ORDER_RANK.get(order.status, -1):
                    order.status = target
                    order.save(update_fields=["status", "updated_at"])
        shipment.tracking_error = issue
        shipment.save(update_fields=["carrier_status", "tracking_history", "tracking_checked_at", "tracking_error", "state", "last_error"])
        detail.update(carrier_after=shipment.carrier_status, order_after=order.status, error=issue)
        changed = before != shipment.carrier_status or detail["order_before"] != order.status
        detail["changed"] = changed
        return ("review" if issue else "synced"), detail


def sync_shipments(order_ids, *, client=None, source="manual", before=None):
    if source not in {"manual", "scheduled"}:
        raise ValueError("Invalid tracking report source")
    order_ids = list(dict.fromkeys(order_ids))
    if len(order_ids) > 1000:
        raise ValueError("Tracking batch is limited to 1000 orders")
    started = timezone.now()
    counts = {"synced": 0, "review": 0, "skipped": 0, "failed": 0}
    changed = 0
    details = []
    claims = []
    run_error = ""
    try:
        for order_id in order_ids:
            token = uuid4()
            query = RedcapShipment.objects.filter(order_id=order_id, order__delivery_provider="redcap",
                state__in=["created", "cancel_unknown", "cancelling"], tracking_number__isnull=False).exclude(tracking_number="")
            if before is not None:
                query = query.filter(Q(tracking_attempted_at__isnull=True) | Q(tracking_attempted_at__lte=before))
            claimed = query.filter(Q(tracking_lock_until__isnull=True) | Q(tracking_lock_until__lte=started)).update(
                tracking_token=token, tracking_lock_until=started + timedelta(minutes=5), tracking_attempted_at=started)
            if not claimed:
                counts["skipped"] += 1
                continue
            shipment = RedcapShipment.objects.select_related("order").get(order_id=order_id)
            claims.append((shipment.pk, shipment.tracking_number, token, order_id, shipment.order.order_number))
        if claims:
            snapshot = RedcapReferenceData.objects.filter(pk=1).first()
            metadata = {row["key"]: row for row in snapshot.statuses} if snapshot else {}
            try:
                payload = (client or RedcapClient.from_settings()).get_tracking_statuses([row[1] for row in claims])
                statuses = parse_status_batch(payload, [row[1] for row in claims])
            except RedcapError:
                statuses = {}
            for shipment_id, number, token, order_id, order_number in claims:
                status = statuses.get(number)
                if status is None:
                    message = "RedCap-ის თრექინგი ვერ დადასტურდა. ბოლო სწორი მდგომარეობა შენარჩუნდა."
                    RedcapShipment.objects.filter(pk=shipment_id, tracking_token=token).update(tracking_error=message)
                    counts["failed"] += 1
                    details.append({"order_id": order_id, "order_number": order_number, "error": message})
                    continue
                result, detail = _apply(shipment_id, number, token, status, metadata)
                counts[result] += 1
                if detail:
                    changed += int(detail["changed"])
                    if detail["changed"] or detail["error"]:
                        details.append(detail)
    except Exception:
        run_error = "თრექინგის შემოწმება მოულოდნელად შეწყდა. იხილეთ სამუშაოს ჟურნალი."
        raise
    finally:
        for shipment_id, _, token, _, _ in claims:
            RedcapShipment.objects.filter(pk=shipment_id, tracking_token=token).update(tracking_token=None, tracking_lock_until=None)
        if changed or counts["review"] or counts["failed"] or run_error:
            report_counts = {"checked": counts["synced"] + counts["review"] + counts["failed"],
                             "changed": changed, **counts}
            RedcapSyncReport.objects.create(started_at=started, finished_at=timezone.now(), source=source,
                status="failed" if counts["failed"] or run_error else "review" if counts["review"] else "success",
                summary=f"შემოწმდა {report_counts['checked']}; შეიცვალა {changed}; შეცდომა {counts['failed']}.",
                details={"counts": report_counts, "items": details[:50], "run_error": run_error})
    return counts
