"""Read-only carrier requests; local delivery status reconciliation only."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .easyway import EasywayClient, EasywayError
from .models import EasywayShipmentState, Order, OrderPaymentStatus, OrderStatus


TERMINAL_STATUSES = {"delivered", "canceled"}
STATUS_TARGETS = {
    "new": None,
    "taking": OrderStatus.PROCESSING,
    "taken": OrderStatus.SHIPPED,
    "in_store": OrderStatus.SHIPPED,
    "taken_store": OrderStatus.SHIPPED,
    "delivered": OrderStatus.DELIVERED,
    "canceled": None,
}
ORDER_RANK = {
    OrderStatus.NEW: 0,
    OrderStatus.CONFIRMED: 1,
    OrderStatus.PROCESSING: 2,
    OrderStatus.SHIPPED: 3,
    OrderStatus.DELIVERED: 4,
}


class TrackingError(Exception):
    pass


def tracking_orders():
    return Order.objects.filter(delivery_provider="easyway", easyway_order_id__gt=0)


def due_tracking_orders(*, before):
    return (
        tracking_orders()
        .exclude(easyway_tracking_status__in=TERMINAL_STATUSES)
        .exclude(easyway_shipment_state__in=[
            EasywayShipmentState.CANCELLED, EasywayShipmentState.CANCELLING,
        ])
        .filter(Q(easyway_tracking_attempted_at__isnull=True)
                | Q(easyway_tracking_attempted_at__lte=before))
    )


def parse_tracking(payload, *, max_entries=1000):
    if not isinstance(payload, list) or not payload or len(payload) > max_entries:
        raise TrackingError("Tracking response must contain 1-1000 history entries.")
    events = set()
    for row in payload:
        if not isinstance(row, dict):
            raise TrackingError("Invalid tracking history entry.")
        status = row.get("status")
        raw_time = row.get("created_at")
        if (not isinstance(status, str) or not status or len(status) > 80
                or not isinstance(raw_time, str)):
            raise TrackingError("Invalid tracking status or timestamp.")
        try:
            timestamp = parse_datetime(raw_time)
        except (ValueError, OverflowError):
            timestamp = None
        if timestamp is None or timezone.is_naive(timestamp):
            raise TrackingError("Tracking timestamp must include a timezone.")
        if timestamp > timezone.now() + timedelta(minutes=5):
            raise TrackingError("Tracking timestamp is in the future; review required.")
        events.add((timestamp, status))
    return [
        {"status": status, "created_at": timestamp.isoformat()}
        for timestamp, status in sorted(events)
    ]


def sync_easyway_tracking(order_id, *, client=None, due_before=None):
    now = timezone.now()
    token = uuid4()
    eligible = tracking_orders() if due_before is None else due_tracking_orders(before=due_before)
    # Atomic lease works across web/cron processes without keeping a DB lock
    # open during the network request. A killed worker becomes retryable.
    claimed = eligible.filter(pk=order_id).filter(
        Q(easyway_tracking_lock_until__isnull=True)
        | Q(easyway_tracking_lock_until__lte=now)
    ).update(
        easyway_tracking_token=token,
        easyway_tracking_lock_until=now + timedelta(minutes=5),
        easyway_tracking_attempted_at=now,
    )
    if not claimed:
        return "skipped"
    order = Order.objects.get(pk=order_id)
    carrier_id = order.easyway_order_id
    try:
        try:
            events = parse_tracking((client or EasywayClient.from_settings()).get_tracking(carrier_id))
        except EasywayError as exc:
            # Provider error text can contain customer data; persist only a safe code.
            code = getattr(exc, "status_code", None)
            raise TrackingError(
                f"EasyWay tracking request failed ({type(exc).__name__}, HTTP {code})."
            ) from exc
        return _apply_tracking(order_id, carrier_id, token, events)
    except TrackingError as exc:
        Order.objects.filter(pk=order_id, easyway_tracking_token=token).update(
            easyway_tracking_error=str(exc)
        )
        raise
    finally:
        Order.objects.filter(pk=order_id, easyway_tracking_token=token).update(
            easyway_tracking_token=None, easyway_tracking_lock_until=None
        )


@transaction.atomic
def _apply_tracking(order_id, carrier_id, token, events):
    order = Order.objects.select_for_update().get(pk=order_id)
    if (order.easyway_tracking_token != token or order.easyway_order_id != carrier_id
            or order.delivery_provider != "easyway"):
        return "skipped"
    history = parse_tracking(order.easyway_tracking_history + events, max_entries=2000)[-1000:]
    latest = history[-1]
    latest_time = parse_datetime(latest["created_at"])
    same_time = {e["status"] for e in history if parse_datetime(e["created_at"]) == latest_time}
    status = latest["status"]
    issue = ""
    order.easyway_tracking_history = history
    order.easyway_tracking_checked_at = timezone.now()
    fields = ["easyway_tracking_history", "easyway_tracking_checked_at", "easyway_tracking_error"]

    if len(same_time) > 1:
        issue = "Conflicting tracking statuses at the same timestamp; review required."
    elif (order.easyway_tracking_status in TERMINAL_STATUSES
          and status != order.easyway_tracking_status):
        issue = "Tracking conflicts with an already final carrier status; review required."
    else:
        order.easyway_tracking_status = status
        order.easyway_tracking_at = latest_time
        fields += ["easyway_tracking_status", "easyway_tracking_at"]
        target = STATUS_TARGETS.get(status)
        if status not in STATUS_TARGETS:
            issue = "Unknown carrier status; order unchanged. Review tracking history."
        elif status == "canceled":
            if order.status == OrderStatus.DELIVERED:
                issue = "Carrier cancellation conflicts with a delivered order; review required."
            # Tracking never initiates local cancellation, refunds or stock writes.
        elif order.easyway_shipment_state in {
            EasywayShipmentState.CANCELLED, EasywayShipmentState.CANCELLING,
        }:
            issue = "Tracking conflicts with local shipment cancellation; review required."
        elif order.status == OrderStatus.CANCELLED:
            issue = "Tracking received for a cancelled order; order unchanged. Review required."
        elif target is not None:
            if order.payment_status != OrderPaymentStatus.PAID:
                issue = "Delivery update for an unpaid/refunding order; review required."
            elif ORDER_RANK.get(target, -1) > ORDER_RANK.get(order.status, -1):
                order.status = target
                fields += ["status", "updated_at"]
    order.easyway_tracking_error = issue
    order.save(update_fields=fields)
    return "review" if issue else "synced"
