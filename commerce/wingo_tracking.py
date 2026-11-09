"""Authenticated current-state reads shared by webhook and operator checks."""

from datetime import timedelta
from uuid import uuid4

from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Order, OrderReturn, WingoShipment
from .wingo import WingoClient, WingoError
from .wingo_shipments import _accept_created, _account_matches, _validate_identity


STATUS_LABELS = {
    1: "დასამუშავებელი", 2: "მუშავდება", 3: "აღებულია", 4: "აღების გაუქმება",
    5: "საწყობშია", 6: "გატანილია ჩასაბარებლად", 7: "მძღოლი გზაშია",
    8: "დაყოვნებულია", 9: "ჩაბარებულია", 10: "გაუქმებულია", 11: "დაბრუნებულია",
}
STATUS_TARGETS = {2: "processing", 3: "shipped", 5: "shipped", 6: "shipped", 7: "shipped", 9: "delivered"}
ORDER_RANK = {"new": 0, "confirmed": 1, "processing": 2, "shipped": 3, "delivered": 4}
ATTENTION = {4, 8, 10, 11}
FINAL = {9, 10, 11}
SAFE_FAILURE = "Wingo-ს სტატუსი ვერ გადამოწმდა. ბოლო დადასტურებული მდგომარეობა შენარჩუნდა; სცადეთ ხელახლა."


class WingoTrackingError(WingoError):
    pass


class WingoTrackingBusy(WingoTrackingError):
    pass


def provider_datetime(value):
    try:
        parsed = parse_datetime(value) if isinstance(value, str) else None
    except (ValueError, TypeError, OverflowError):
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        raise WingoTrackingError("Wingo-ს სტატუსის განახლების დრო არასწორია. შენახული მდგომარეობა უცვლელია.")
    return parsed


def _claim(order_id, *, notification):
    token, now = uuid4(), timezone.now()
    busy = False
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update(nowait=True).get(pk=order_id)
            shipment = WingoShipment.objects.select_for_update(nowait=True).filter(order=order).first()
            if (order.delivery_provider != "wingo" or shipment is None
                    or shipment.state not in {"created", "submitting", "unknown"} or not shipment.request_payload):
                raise WingoTrackingError("შესამოწმებელი Wingo გზავნილი ჯერ არ არის.")
            if notification:
                if (notification["supplierOrderId"] != shipment.request_payload.get("supplierOrderId")
                        or (shipment.provider_order_id and shipment.provider_order_id != notification["id"])
                        or (shipment.tracking_number and shipment.tracking_number != notification["orderNumber"])):
                    raise WingoTrackingError("შეტყობინება ამ გზავნილს არ ეკუთვნის.")
                shipment.webhook_received_at = now
            elif shipment.state != "created" or not shipment.provider_order_id:
                raise WingoTrackingError("ჯერ გადაამოწმეთ გაგზავნის გაურკვეველი შედეგი.")
            if shipment.tracking_token and shipment.tracking_lock_until and shipment.tracking_lock_until > now:
                busy = True
                if notification:
                    shipment.save(update_fields=["webhook_received_at"])
            else:
                shipment.tracking_token = token
                shipment.tracking_lock_until = now + timedelta(seconds=60)
                shipment.tracking_attempted_at = now
                shipment.save(update_fields=["tracking_token", "tracking_lock_until", "tracking_attempted_at", "webhook_received_at"])
    except DatabaseError:
        raise WingoTrackingBusy("შეკვეთაზე სხვა მოქმედება მიმდინარეობს. სცადეთ ხელახლა.") from None
    if busy:
        raise WingoTrackingBusy("Wingo-ს სტატუსი უკვე მოწმდება. სცადეთ ხელახლა რამდენიმე წამში.")
    return shipment, token


def _apply(shipment, token, result, *, client):
    status = result.get("orderStatusId")
    if type(status) is not int or status not in STATUS_LABELS:
        raise WingoTrackingError("Wingo-სგან უცნობი სტატუსი მოვიდა. შეკვეთის მდგომარეობა უცვლელია.")
    updated_at = provider_datetime(result.get("updatedAt"))
    with transaction.atomic():
        order = Order.objects.select_for_update(nowait=True).get(pk=shipment.order_id)
        locked = WingoShipment.objects.select_for_update(nowait=True).get(pk=shipment.pk)
        if locked.tracking_token != token:
            return "skipped"
        if (order.delivery_provider != "wingo" or locked.request_payload != shipment.request_payload
                or (locked.provider_order_id and locked.provider_order_id != result["id"])
                or (locked.tracking_number and locked.tracking_number != result["orderNumber"])):
            raise WingoTrackingError("გზავნილის მონაცემები შეიცვალა. სტატუსი არ განახლებულა.")
        _validate_identity(result, locked.request_payload)
        _account_matches(locked, client)
        previous = locked.carrier_status
        outcome, issue = "synced", ""
        if locked.carrier_updated_at and updated_at < locked.carrier_updated_at:
            outcome, issue = "stale", locked.tracking_error
        elif locked.carrier_updated_at and updated_at == locked.carrier_updated_at and previous != status:
            outcome, issue = "review", "Wingo-მ ერთსა და იმავე დროზე განსხვავებული სტატუსები დააბრუნა. გადაამოწმეთ."
        elif previous in FINAL and previous != status and not (previous in {9, 10} and status == 11):
            outcome, issue = "review", "Wingo-ს სტატუსი უკვე საბოლოო მდგომარეობას ეწინააღმდეგება. გადაამოწმეთ."
        else:
            if locked.state in {"submitting", "unknown"}:
                _accept_created(order, locked, result)
            locked.carrier_status = status
            locked.carrier_updated_at = updated_at
            if status in ATTENTION:
                outcome, issue = "review", "გზავნილს ყურადღება სჭირდება. გადაამოწმეთ Wingo-სთან; თანხა და მარაგი არ შეცვლილა."
            elif (order.status not in ORDER_RANK or order.payment_status != "paid"
                  or OrderReturn.objects.filter(order=order).exists()):
                outcome, issue = "review", "შეკვეთის გადახდა/დაბრუნება შესამოწმებელია. შეკვეთის სტატუსი არ შეცვლილა."
            else:
                target = STATUS_TARGETS.get(status)
                if target and ORDER_RANK[target] > ORDER_RANK[order.status]:
                    order.status = target
                    order.save(update_fields=["status", "updated_at"])
                elif target and ORDER_RANK[target] < ORDER_RANK[order.status]:
                    outcome, issue = "review", "კურიერის ეტაპი შეკვეთაზე შენახულზე ადრეულია. შეკვეთის სტატუსი უკან არ შეცვლილა."
        history = list(locked.tracking_history)
        observation = {"status": status, "provider_updated_at": updated_at.isoformat(), "result": outcome}
        if not history or any(history[-1].get(key) != value for key, value in observation.items()):
            history.append({**observation, "observed_at": timezone.now().isoformat()})
        locked.tracking_history = history[-1000:]
        locked.tracking_checked_at = timezone.now()
        locked.tracking_error = issue
        # A notification arriving during this GET stays pending, even if retries overlap.
        locked.webhook_checked_at = shipment.webhook_received_at
        locked.save(update_fields=["carrier_status", "carrier_updated_at", "tracking_history",
                                   "tracking_checked_at", "tracking_error", "webhook_checked_at"])
        return outcome


def sync_shipment(order_id, *, client=None, notification=None):
    shipment, token = _claim(order_id, notification=notification)
    try:
        # Provider callbacks time out at ~10s. Use shorter reads here than for booking.
        carrier = client or WingoClient.from_settings(connect_timeout=2, read_timeout=4)
        _account_matches(shipment, carrier)
        reference = notification["id"] if notification else shipment.provider_order_id
        result = carrier.get_order(reference)
        _validate_identity(result, shipment.request_payload)
        number = notification["orderNumber"] if notification else shipment.tracking_number
        if result["id"] != reference or result["orderNumber"] != number:
            raise WingoTrackingError("Wingo-ს გზავნილის ნომერი ვერ დადასტურდა.")
        return _apply(shipment, token, result, client=carrier)
    except Exception as exc:
        message = str(exc) if isinstance(exc, WingoTrackingError) else SAFE_FAILURE
        WingoShipment.objects.filter(pk=shipment.pk, tracking_token=token).update(tracking_error=message)
        raise WingoTrackingError(message) from None
    finally:
        WingoShipment.objects.filter(pk=shipment.pk, tracking_token=token).update(
            tracking_token=None, tracking_lock_until=None)
