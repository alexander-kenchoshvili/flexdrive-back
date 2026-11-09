"""Manual outbound booking only; payment, stock and order status never change here."""

from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .delivery_quote_data import DeliveryQuoteError
from .models import Order, OrderReturn, WingoShipment
from .wingo import WingoClient, WingoConfigurationError, WingoError
from .wingo_locations import resolve_delivery_location


class WingoShipmentError(WingoError):
    pass


def _eligible(order):
    return (order.delivery_provider == "wingo" and order.payment_status == "paid"
            and order.status in {"new", "confirmed", "processing"}
            and not order.stock_restored_at and not OrderReturn.objects.filter(order=order).exists())


def can_submit(order):
    if not order or not _eligible(order):
        return False
    shipment = WingoShipment.objects.filter(order=order).first()
    return shipment is None or (not shipment.provider_order_id and not shipment.tracking_number
                               and shipment.state in {"not_sent", "failed"})


def _phone(value):
    value = "".join(char for char in str(value) if char.isascii() and char.isdigit())
    if len(value) == 12 and value.startswith("995"):
        value = value[3:]
    if len(value) != 9:
        raise WingoShipmentError("შეამოწმეთ გამგზავნისა და მიმღების ტელეფონის ნომრები.")
    return "+995" + value


def build_order_payload(order, *, parcel_count, client):
    if type(parcel_count) is not int or not 1 <= parcel_count <= 1000:
        raise WingoShipmentError("შეფუთვების რაოდენობა უნდა იყოს 1–1000.")
    merchant = settings.WINGO_MERCHANT_USER_ID
    pickup_title = settings.WINGO_PICKUP_TITLE
    pickup_address = settings.WINGO_PICKUP_ADDRESS
    if not all(isinstance(value, str) and value.strip() for value in
               (merchant, pickup_title, pickup_address, settings.WINGO_PICKUP_PHONE)):
        raise WingoConfigurationError("Wingo-ს მერჩანტის ID და აღების დასახელება, მისამართი და ტელეფონი შესავსებია.")
    WingoClient._reference(merchant)
    try:
        location = resolve_delivery_location(order.delivery_region_id, order.delivery_city_id)
    except DeliveryQuoteError:
        raise WingoShipmentError("შეკვეთაზე შენახული დასახლება Wingo-ში აღარ არის ხელმისაწვდომი.") from None
    snapshot = location.snapshot
    if snapshot.api_base_url != client.api_base_url or snapshot.account_mode != client.account_mode:
        raise WingoShipmentError("Wingo-ს ანგარიშის შეცვლის შემდეგ ჯერ განაახლეთ ტარიფები.")
    frozen = order.delivery_provider_data
    if (not isinstance(frozen, dict) or frozen.get("region_id") != location.provider_region_id
            or frozen.get("locality_id") != location.provider_city_id
            or type(frozen.get("delivery_type_id")) is not int or frozen["delivery_type_id"] != 1
            or order.delivery_service_slug != "standard"):
        raise WingoShipmentError("შეკვეთის მიწოდების მონაცემები სტანდარტულ Wingo მომსახურებას არ შეესაბამება.")
    band_id = frozen.get("weight_range_id")
    band = next((row for row in snapshot.weight_ranges if type(band_id) is int and row["id"] == band_id), None)
    weight = order.shipping_weight_kg
    if not band or weight is None or not weight.is_finite() or not (weight > 0 and
            Decimal(band["min_weight"]) <= weight <= Decimal(band["max_weight"])):
        raise WingoShipmentError("შეკვეთაზე შენახული წონა ან წონის დიაპაზონი შესამოწმებელია.")
    recipient = f"{order.first_name} {order.last_name}".strip()
    if not recipient or not order.city.strip() or not order.address_line.strip() or not order.order_number:
        raise WingoShipmentError("შეკვეთის მიმღები, ნომერი ან მისამართი დაუსრულებელია.")
    products = [{"productName": row.product_name, "quantity": row.quantity} for row in order.items.order_by("pk")]
    if not products or any(not row["productName"].strip() or row["quantity"] <= 0 for row in products):
        raise WingoShipmentError("შეკვეთის პროდუქტები შესამოწმებელია.")
    return {
        "userId": merchant, "supplierOrderId": order.order_number,
        "recipientName": recipient, "recipientPhone": _phone(order.phone),
        "regionId": frozen["region_id"], "localityId": frozen["locality_id"],
        "deliveryAddress": f"{order.city.strip()}, {order.address_line.strip()}",
        "pickupTitle": pickup_title, "pickupAddress": pickup_address,
        "pickupContactPhone": _phone(settings.WINGO_PICKUP_PHONE),
        "deliveryTypeId": 1, "weightRangeId": band_id, "recipientPaymentDue": 0,
        "packageCount": parcel_count, "products": products, "courierComment": (order.note or "")[:1000],
    }


def _account_matches(shipment, client):
    if (shipment.account_mode != client.account_mode or shipment.api_base_url != client.api_base_url
            or shipment.request_payload.get("userId") != settings.WINGO_MERCHANT_USER_ID):
        raise WingoShipmentError("გზავნილი სხვა Wingo ანგარიშით შეიქმნა. შეამოწმეთ ანგარიშის პარამეტრები.")


def _validate_identity(result, payload):
    if not isinstance(result, dict):
        raise WingoShipmentError("გზავნილის პასუხი შესამოწმებელია.")
    for key in ("id", "orderNumber"):
        WingoClient._reference(result.get(key))
    # Recovery never trusts list filters (the provider currently ignores them).
    for key in ("userId", "supplierOrderId", "recipientName", "regionId", "localityId",
                "deliveryAddress", "pickupAddress", "deliveryTypeId", "packageCount"):
        if type(result.get(key)) is not type(payload[key]) or result[key] != payload[key]:
            raise WingoShipmentError("Wingo-ს გზავნილის მონაცემები გაგზავნილ მოთხოვნას არ ემთხვევა.")
    # Actual detail responses serialize this foreign key as a numeric string.
    weight_range = result.get("weightRangeId")
    if (type(weight_range) not in {str, int} or str(weight_range) != str(payload["weightRangeId"])):
        raise WingoShipmentError("Wingo-ს გზავნილის წონის დიაპაზონი მოთხოვნას არ ემთხვევა.")
    if _phone(result.get("recipientPhone", "")) != payload["recipientPhone"]:
        raise WingoShipmentError("Wingo-ს გზავნილის მიმღები მოთხოვნას არ ემთხვევა.")
    try:
        if isinstance(result.get("recipientPaymentDue"), bool) or Decimal(str(result["recipientPaymentDue"])) != 0:
            raise ValueError
    except (KeyError, ValueError, InvalidOperation):
        raise WingoShipmentError("Wingo-ს გზავნილის გადასახდელი თანხა მოთხოვნას არ ემთხვევა.") from None


def _price(value):
    try:
        amount = Decimal(str(value))
        if amount.is_finite() and 0 <= amount <= Decimal("9999999999.99"):
            rounded = amount.quantize(Decimal("0.01"))
            return rounded if rounded == amount else None
    except (InvalidOperation, ValueError, TypeError):
        pass
    return None


def _accept_created(order, shipment, result):
    _validate_identity(result, shipment.request_payload)
    shipment.provider_order_id = result["id"]
    shipment.tracking_number = result["orderNumber"]
    shipment.booked_price = _price(result.get("serviceFee"))
    status = result.get("orderStatusId")
    shipment.carrier_status = status if type(status) is int and 1 <= status <= 32767 else None
    shipment.state = WingoShipment.State.CREATED
    shipment.submitted_at = shipment.submitted_at or timezone.now()
    shipment.operation_token = None
    shipment.last_error = ""
    if shipment.booked_price is None:
        shipment.last_error = "გზავნილი შეიქმნა; Wingo-ს ფასი პასუხში ვერ დადასტურდა. გადაამოწმეთ პანელში."
    elif shipment.booked_price != order.carrier_delivery_cost:
        shipment.last_error = "Wingo-ს ფასი შეკვეთაზე შენახული ტარიფისგან განსხვავდება. მომხმარებლის გადასახდელი არ შეცვლილა."
    if not _eligible(order):
        shipment.last_error = "გზავნილი შეიქმნა, მაგრამ შეკვეთის მდგომარეობა შეიცვალა. დაუკავშირდით Wingo-ს."
    shipment.save()
    return shipment


def submit_shipment(order_id, *, parcel_count, prepared, client=None):
    if prepared is not True:
        raise WingoShipmentError("დაადასტურეთ, რომ ნივთები შემოწმებულია, შეფუთულია და მზადაა კურიერისთვის.")
    token = uuid4()
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if not can_submit(order):
            raise WingoShipmentError("გაგზავნა შეუძლებელია. გადაამოწმეთ გადახდა და უკვე გაგზავნილი მოთხოვნის შედეგი.")
        carrier = client or WingoClient.from_settings()
        payload = build_order_payload(order, parcel_count=parcel_count, client=carrier)
        shipment, _ = WingoShipment.objects.get_or_create(order=order)
        shipment.state = WingoShipment.State.SUBMITTING
        shipment.operation_token = token
        shipment.parcel_count = parcel_count
        shipment.request_payload = payload
        shipment.account_mode = carrier.account_mode
        shipment.api_base_url = carrier.api_base_url
        shipment.attempted_at = timezone.now()
        shipment.last_error = ""
        shipment.save()
    try:
        result = carrier.create_order(payload)
    except Exception as exc:
        # Once POST starts, any unclassified failure may have created a shipment.
        unknown = not isinstance(exc, WingoError) or exc.outcome_unknown
        message = ("გაგზავნის შედეგი გაურკვეველია. ახალი გზავნილის ნაცვლად გამოიყენეთ შედეგის გადამოწმება."
                   if unknown else "Wingo-მ მოთხოვნა უარყო. შეამოწმეთ API წვდომა და შეკვეთის მონაცემები.")
        WingoShipment.objects.filter(pk=shipment.pk, state="submitting", operation_token=token).update(
            state="unknown" if unknown else "failed", operation_token=None, last_error=message)
        raise WingoShipmentError(message) from None
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            shipment = WingoShipment.objects.select_for_update().get(pk=shipment.pk)
            if shipment.operation_token != token or shipment.state != "submitting":
                raise WingoShipmentError("გზავნილის მდგომარეობა შეიცვალა. შედეგი გადაამოწმეთ.")
            return _accept_created(order, shipment, result)
    except (WingoError, IntegrityError):
        WingoShipment.objects.filter(pk=shipment.pk, operation_token=token, state="submitting").update(
            state="unknown", operation_token=None,
            last_error="Wingo-ს პასუხი ვერ დადასტურდა. ხელახლა გაგზავნის ნაცვლად გადაამოწმეთ არსებული გზავნილი.")
        raise WingoShipmentError("Wingo-ს პასუხი შესამოწმებელია. ახალი მოთხოვნა არ გაიგზავნოს.") from None


def _find_existing(shipment, client):
    matches, seen = [], set()
    # Bounded full-page search: provider-side supplierOrderId/search filters are ignored.
    for page in range(1, 11):
        body = client.get_orders(page=page, limit=100)
        rows = body.get("orders") if isinstance(body, dict) else None
        pagination = body.get("pagination") if isinstance(body, dict) else None
        if (not isinstance(rows, list) or len(rows) > 100 or not isinstance(pagination, dict)
                or type(pagination.get("page")) is not int or pagination["page"] != page
                or type(pagination.get("hasNext")) is not bool):
            raise WingoShipmentError("Wingo-ს ძიების პასუხი არასწორია. ახალი მოთხოვნა არ გაიგზავნოს.")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in seen:
                raise WingoShipmentError("Wingo-ს ძიების გვერდები ვერ გადამოწმდა. ახალი მოთხოვნა არ გაიგზავნოს.")
            seen.add(row["id"])
            if row.get("supplierOrderId") == shipment.request_payload["supplierOrderId"]:
                matches.append(row)
        if len(matches) > 1:
            raise WingoShipmentError("ამ ნომრით Wingo-ში რამდენიმე გზავნილია. გადაამოწმეთ მათ პანელში; ახალი არ შექმნათ.")
        if not pagination["hasNext"]:
            if len(matches) != 1:
                raise WingoShipmentError("გზავნილი ჯერ ვერ მოიძებნა. შედეგი გაურკვეველი რჩება; ახალი არ შექმნათ.")
            result = client.get_order(matches[0]["id"])
            _validate_identity(result, shipment.request_payload)
            if result["id"] != matches[0]["id"] or result["orderNumber"] != matches[0].get("orderNumber"):
                raise WingoShipmentError("Wingo-ს გზავნილის ნომერი ვერ დადასტურდა.")
            return result
        if not rows:
            break
    raise WingoShipmentError("ძიების ზღვარი ამოიწურა. გადაამოწმეთ Wingo-ს პანელში; ახალი მოთხოვნა არ გაიგზავნოს.")


def recover_submission(order_id, *, client=None):
    shipment = WingoShipment.objects.filter(order_id=order_id, state__in=["unknown", "submitting"]).first()
    if shipment is None or not shipment.request_payload or not shipment.attempted_at:
        raise WingoShipmentError("შესამოწმებელი გაგზავნის მოთხოვნა არ არის.")
    carrier = client or WingoClient.from_settings()
    _account_matches(shipment, carrier)
    result = _find_existing(shipment, carrier)
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            locked = WingoShipment.objects.select_for_update().get(pk=shipment.pk)
            if (locked.state not in {"unknown", "submitting"} or locked.provider_order_id
                    or locked.request_payload != shipment.request_payload or locked.attempted_at != shipment.attempted_at):
                raise WingoShipmentError("გზავნილის მდგომარეობა უკვე შეიცვალა. განაახლეთ შეკვეთის გვერდი.")
            return _accept_created(order, locked, result)
    except IntegrityError:
        raise WingoShipmentError("Wingo-ს გზავნილი უკვე სხვა შეკვეთასთანაა დაკავშირებული. გადაამოწმეთ.") from None


def get_shipment_label(order_id, *, size="a4", client=None):
    shipment = WingoShipment.objects.filter(order_id=order_id, state="created").first()
    if shipment is None or not shipment.provider_order_id:
        raise WingoShipmentError("სტიკერი მხოლოდ დადასტურებული გზავნილისთვისაა ხელმისაწვდომი.")
    carrier = client or WingoClient.from_settings()
    _account_matches(shipment, carrier)
    # Verify ownership again before forwarding a private document.
    result = carrier.get_order(shipment.provider_order_id)
    _validate_identity(result, shipment.request_payload)
    if result["id"] != shipment.provider_order_id or result["orderNumber"] != shipment.tracking_number:
        raise WingoShipmentError("სტიკერის გზავნილთან შესაბამისობა ვერ დადასტურდა.")
    return carrier.get_label(shipment.provider_order_id, size=size)
