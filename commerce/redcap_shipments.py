"""Operator-only outbound booking. Courier state never changes payment/stock."""

from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Order, OrderReturn, RedcapReferenceData, RedcapShipment
from .redcap import RedcapClient, RedcapConfigurationError, RedcapError, positive_decimal
from .redcap_references import ZONE_SERVICES


class RedcapShipmentError(RedcapError):
    pass


def _eligible(order):
    return (order.delivery_provider == "redcap" and order.payment_status == "paid"
            and order.status in {"new", "confirmed", "processing"}
            and not OrderReturn.objects.filter(order=order).exists())


def can_submit(order):
    if not order or not _eligible(order):
        return False
    shipment = RedcapShipment.objects.filter(order=order).first()
    return shipment is None or (not shipment.tracking_number and shipment.state in {"not_sent", "failed"})


def _snapshot_location(order):
    snapshot = RedcapReferenceData.objects.filter(pk=1).first()
    if snapshot is None:
        raise RedcapShipmentError("RedCap-ის ტარიფები ჯერ არ არის ჩამოტვირთული.")
    location = next((row for row in snapshot.locations if row["id"] == order.delivery_city_id), None)
    if location is None:
        raise RedcapShipmentError("შეკვეთის საკურიერო ზონა აღარ არის ხელმისაწვდომი.")
    if order.delivery_service_slug not in ZONE_SERVICES[location["zone_slug"]]:
        raise RedcapShipmentError("შეკვეთის მიწოდების ტიპი ზონას არ შეესაბამება.")
    return snapshot, location


def _phone(value):
    value = "".join(c for c in str(value) if c.isascii() and c.isdigit())
    if len(value) == 12 and value.startswith("995"):
        value = value[3:]
    if len(value) != 9:
        raise RedcapShipmentError("შეამოწმეთ გამგზავნისა და მიმღების ტელეფონის ნომრები.")
    return value


def build_order_payload(order, *, parcel_count):
    if type(parcel_count) is not int or not 1 <= parcel_count <= 1000:
        raise RedcapShipmentError("ამანათების რაოდენობა უნდა იყოს 1–1000.")
    snapshot, location = _snapshot_location(order)
    sender = {"sender_name": settings.REDCAP_SENDER_NAME, "sender_city": settings.REDCAP_SENDER_CITY,
              "sender_address": settings.REDCAP_SENDER_ADDRESS, "sender_phone": settings.REDCAP_SENDER_PHONE}
    if any(not str(value).strip() for value in sender.values()):
        raise RedcapShipmentError("RedCap-ის აღების მისამართი და გამგზავნის მონაცემები შესავსებია.")
    if sender["sender_city"] not in {row["name"] for row in snapshot.locations}:
        raise RedcapShipmentError("გამგზავნის ზონა RedCap-ის ცნობარს არ ემთხვევა.")
    sender["sender_phone"] = _phone(sender["sender_phone"])
    if not order.city.strip() or not order.address_line.strip() or not order.order_number:
        raise RedcapShipmentError("შეკვეთის მისამართი ან ნომერი დაუსრულებელია.")
    products = [{"name": item.product_name, "qty": item.quantity} for item in order.items.order_by("pk")]
    if not products or any(row["qty"] <= 0 or not row["name"].strip() for row in products):
        raise RedcapShipmentError("შეკვეთის პროდუქტები შესამოწმებელია.")
    address = order.address_line
    if order.city.strip() != location["name"]:
        address = f"{order.city.strip()}, {address}"
    return {
        **sender, "receiver_name": f"{order.first_name} {order.last_name}".strip(),
        "receiver_phone": _phone(order.phone), "receiver_city": location["name"],
        "receiver_address": address, "weight": float(positive_decimal(order.shipping_weight_kg)),
        "quantity": parcel_count, "delivery_type": order.delivery_service_slug,
        "payment_type": "transfer", "delivery_payer": "sender", "item_price": 0,
        "products": products, "order_number": order.order_number, "notes": (order.note or "")[:500],
    }


def _price(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or value > Decimal("9999999999.99"):
            return None
        return value.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _accept_created(order, shipment, provider_order):
    tracking = provider_order.get("tracking_number")
    RedcapClient._reference(tracking)
    shipment.tracking_number = tracking.strip()
    shipment.state = RedcapShipment.State.CREATED
    shipment.booked_price = _price(provider_order.get("delivery_price"))
    shipment.submitted_at = shipment.submitted_at or timezone.now()
    shipment.operation_token = None
    shipment.last_error = ""
    if shipment.booked_price is None:
        shipment.last_error = "გზავნილი შეიქმნა; კურიერის ფასი პასუხში ვერ დადასტურდა. გადაამოწმეთ."
    elif shipment.booked_price != order.carrier_delivery_cost:
        shipment.last_error = "კურიერის ფასი შეკვეთაზე შენახულ ფასს განსხვავდება. მომხმარებლის თანხა არ შეცვლილა."
    if not _eligible(order):
        shipment.last_error = "გზავნილი შეიქმნა, მაგრამ შეკვეთის მდგომარეობა შეიცვალა. გადაამოწმეთ კურიერთან."
    shipment.save()
    return shipment


def submit_shipment(order_id, *, parcel_count, prepared, client=None):
    if prepared is not True:
        raise RedcapShipmentError("დაადასტურეთ, რომ ნივთები შემოწმებული და შეფუთულია.")
    token = uuid4()
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if not _eligible(order):
            raise RedcapShipmentError("გაგზავნა მხოლოდ გადახდილი, გასაგზავნად მზად შეკვეთისთვისაა შესაძლებელი.")
        payload = build_order_payload(order, parcel_count=parcel_count)
        shipment, _ = RedcapShipment.objects.get_or_create(order=order, defaults={"service_slug": order.delivery_service_slug})
        shipment = RedcapShipment.objects.select_for_update().get(pk=shipment.pk)
        if shipment.tracking_number or shipment.state not in {"not_sent", "failed"}:
            raise RedcapShipmentError("განმეორებით გაგზავნამდე არსებული გზავნილის შედეგი გადაამოწმეთ.")
        carrier = client or RedcapClient.from_settings()
        shipment.state = RedcapShipment.State.SUBMITTING
        shipment.operation_token = token
        shipment.parcel_count = parcel_count
        shipment.service_slug = order.delivery_service_slug
        shipment.attempted_at = timezone.now()
        shipment.last_error = ""
        shipment.save()
    try:
        result = carrier.create_order(payload)
    except Exception as exc:
        unknown = not isinstance(exc, RedcapError) or getattr(exc, "outcome_unknown", True)
        RedcapShipment.objects.filter(pk=shipment.pk, operation_token=token).update(
            state="unknown" if unknown else "failed", operation_token=None,
            last_error="გაგზავნის შედეგი გაურკვეველია. გადაამოწმეთ, შეიქმნა თუ არა გზავნილი." if unknown
            else "RedCap-მა მოთხოვნა უარყო. მონაცემების შესწორების შემდეგ შესაძლებელია ხელახლა ცდა.",
        )
        raise RedcapShipmentError("RedCap-ში გაგზავნა ვერ დადასტურდა. იხილეთ გზავნილის მდგომარეობა.") from exc
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            shipment = RedcapShipment.objects.select_for_update().get(pk=shipment.pk)
            if shipment.operation_token != token or shipment.state != "submitting":
                raise RedcapShipmentError("გაგზავნის მდგომარეობა შეიცვალა; შედეგი ხელით გადაამოწმეთ.")
            return _accept_created(order, shipment, result)
    except (RedcapError, IntegrityError) as exc:
        # A provider success must never turn into a retryable failure merely
        # because its tracking reference is malformed or already attached.
        RedcapShipment.objects.filter(pk=shipment.pk, operation_token=token, state="submitting").update(
            state="unknown", operation_token=None,
            last_error="RedCap-ის პასუხის შენახვა ვერ დადასტურდა. ახალი მოთხოვნის ნაცვლად გადაამოწმეთ არსებული გზავნილი.",
        )
        raise RedcapShipmentError("გზავნილის პასუხი შესამოწმებელია. ახალი მოთხოვნა არ გაიგზავნოს.") from exc


def recover_submission(order_id, *, client=None):
    order = Order.objects.get(pk=order_id)
    shipment = RedcapShipment.objects.filter(order=order, state__in=["unknown", "submitting"]).first()
    if shipment is None:
        raise RedcapShipmentError("შესამოწმებელი გაგზავნის მოთხოვნა არ არის.")
    result = (client or RedcapClient.from_settings()).get_order(order.order_number).get("order")
    if not isinstance(result, dict) or result.get("order_number") != order.order_number:
        raise RedcapShipmentError("ზუსტი შესაბამისობა ვერ დადასტურდა. გადაამოწმეთ RedCap-ის პანელში.")
    RedcapClient._reference(result.get("tracking_number"))
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        shipment = RedcapShipment.objects.select_for_update().get(pk=shipment.pk)
        if shipment.state not in {"unknown", "submitting"} or shipment.tracking_number:
            raise RedcapShipmentError("გზავნილის მდგომარეობა უკვე შეცვლილია.")
        return _accept_created(order, shipment, result)


def cancel_shipment(order_id, *, reason, client=None):
    carrier = client or RedcapClient.from_settings()
    # Read eligibility from the documented batch response before mutation. The
    # carrier still enforces its own cancellation cutoff after this check.
    shipment = RedcapShipment.objects.get(order_id=order_id)
    if shipment.state != "created" or not shipment.tracking_number:
        raise RedcapShipmentError("გზავნილი გასაუქმებლად ხელმისაწვდომი არ არის.")
    from .redcap_tracking import parse_status_batch
    result = parse_status_batch(carrier.get_tracking_statuses([shipment.tracking_number]), [shipment.tracking_number])
    status = result[shipment.tracking_number]
    snapshot = RedcapReferenceData.objects.get(pk=1)
    metadata = next((row for row in snapshot.statuses if row["key"] == status), None)
    if not metadata or metadata["can_cancel"] is not True:
        raise RedcapShipmentError("კურიერის მიმდინარე სტატუსზე გზავნილის გაუქმება აღარ არის შესაძლებელი.")
    token = uuid4()
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order_id)
        locked = RedcapShipment.objects.select_for_update().get(pk=shipment.pk)
        if locked.state != "created" or locked.tracking_number != shipment.tracking_number:
            raise RedcapShipmentError("გზავნილის მდგომარეობა შეიცვალა. გადაამოწმეთ ხელახლა.")
        locked.state = "cancelling"
        locked.operation_token = token
        locked.attempted_at = timezone.now()
        locked.save()
    try:
        carrier.cancel_order(shipment.tracking_number, reason=reason)
    except Exception as exc:
        unknown = not isinstance(exc, RedcapError) or getattr(exc, "outcome_unknown", True)
        RedcapShipment.objects.filter(pk=shipment.pk, operation_token=token).update(
            state="cancel_unknown" if unknown else "created", operation_token=None,
            last_error="გაუქმების შედეგი გაურკვეველია; გადაამოწმეთ." if unknown else "RedCap-მა გაუქმება უარყო.",
        )
        raise RedcapShipmentError("გზავნილის გაუქმება ვერ დადასტურდა.") from exc
    RedcapShipment.objects.filter(pk=shipment.pk, operation_token=token, state="cancelling").update(
        state="cancelled", operation_token=None, last_error="", carrier_status="cancelled",
    )
    shipment.refresh_from_db()
    return shipment
