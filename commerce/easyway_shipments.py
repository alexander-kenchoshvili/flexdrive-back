from datetime import time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .easyway import (
    EasywayClient,
    EasywayConfigurationError,
    EasywayResponseError,
    EasywayTransportError,
)
from .models import (
    EasywayShipmentState,
    Order,
    OrderPaymentStatus,
    OrderStatus,
)

EASYWAY_TIME_ZONE = ZoneInfo("Asia/Tbilisi")


class EasywayShipmentError(Exception):
    def __init__(self, detail, *, code="easyway_shipment_failed", outcome_unknown=False):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.outcome_unknown = outcome_unknown


def can_submit_easyway_shipment(order):
    return bool(
        order
        and order.delivery_provider == "easyway"
        and order.payment_status == OrderPaymentStatus.PAID
        and order.status != OrderStatus.CANCELLED
        and order.easyway_order_id is None
        and order.easyway_shipment_state
        in {EasywayShipmentState.NOT_SENT, EasywayShipmentState.FAILED}
    )


def submit_easyway_shipment(order, *, client=None):
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        _validate_submission(locked_order)
        try:
            payload = build_easyway_order_payload(locked_order)
        except EasywayConfigurationError as error:
            raise EasywayShipmentError(
                str(error),
                code="easyway_configuration_error",
            ) from error
        locked_order.easyway_shipment_state = EasywayShipmentState.SUBMITTING
        locked_order.easyway_last_error = ""
        locked_order.easyway_last_attempt_at = timezone.now()
        locked_order.save(
            update_fields=[
                "easyway_shipment_state",
                "easyway_last_error",
                "easyway_last_attempt_at",
                "updated_at",
            ]
        )

    try:
        easyway_order_id = (client or EasywayClient.from_settings()).create_order(payload)
    except EasywayTransportError as error:
        _record_failure(
            locked_order.pk,
            detail="EasyWay-ის პასუხი ვერ მივიღეთ. ხელახლა გაგზავნამდე გადაამოწმეთ, შეიქმნა თუ არა გზავნილი.",
            outcome_unknown=True,
        )
        raise EasywayShipmentError(
            "EasyWay-ის პასუხი ვერ მივიღეთ. გზავნილის მდგომარეობა ხელით გადაამოწმეთ.",
            code="easyway_submission_unknown",
            outcome_unknown=True,
        ) from error
    except EasywayResponseError as error:
        outcome_unknown = bool(error.outcome_unknown)
        summary = (
            "EasyWay-ის პასუხი გაურკვეველია. ხელახლა გაგზავნამდე გადაამოწმეთ გზავნილი."
            if outcome_unknown
            else "EasyWay-მ გზავნილის შექმნის მოთხოვნა უარყო."
        )
        detail = f"{summary} {error}"
        _record_failure(
            locked_order.pk,
            detail=detail,
            outcome_unknown=outcome_unknown,
        )
        raise EasywayShipmentError(
            detail,
            code=(
                "easyway_submission_unknown"
                if outcome_unknown
                else "easyway_submission_rejected"
            ),
            outcome_unknown=outcome_unknown,
        ) from error
    except EasywayConfigurationError as error:
        _record_failure(
            locked_order.pk,
            detail=str(error),
            outcome_unknown=False,
        )
        raise EasywayShipmentError(
            str(error),
            code="easyway_configuration_error",
        ) from error

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.easyway_shipment_state != EasywayShipmentState.SUBMITTING:
            raise EasywayShipmentError(
                "EasyWay გზავნილის მდგომარეობა პარალელურად შეიცვალა.",
                code="easyway_submission_state_changed",
                outcome_unknown=True,
            )
        locked_order.easyway_order_id = easyway_order_id
        locked_order.easyway_shipment_state = EasywayShipmentState.CREATED
        locked_order.easyway_last_error = ""
        locked_order.easyway_submitted_at = timezone.now()
        locked_order.save(
            update_fields=[
                "easyway_order_id",
                "easyway_shipment_state",
                "easyway_last_error",
                "easyway_submitted_at",
                "updated_at",
            ]
        )
    return locked_order


def build_easyway_order_payload(order):
    _validate_submission(order)
    sender = _sender_settings()
    receiver_phone = _normalize_georgian_mobile(order.phone, "receiver phone")
    receiver_tax_code = settings.EASYWAY_RECEIVER_TAX_CODE_PLACEHOLDER
    if not receiver_tax_code.isdigit() or len(receiver_tax_code) != 11:
        raise EasywayConfigurationError(
            "EASYWAY_RECEIVER_TAX_CODE_PLACEHOLDER must contain exactly 11 digits."
        )
    if not order.shipping_weight_kg or not order.delivery_package_id:
        raise EasywayConfigurationError(
            "Order shipping weight and package ID are required for EasyWay."
        )

    items = []
    quantity = 0
    for order_item in order.items.order_by("id"):
        for unit_index in range(1, order_item.quantity + 1):
            items.append({"code": f"{order.order_number}-{order_item.pk}-{unit_index}"})
            quantity += 1
    if not items:
        raise EasywayConfigurationError("EasyWay order must contain at least one item.")

    return {
        "tracking_code": order.order_number,
        **sender,
        "receiver_name": f"{order.first_name} {order.last_name}".strip(),
        "receiver_region_id": order.delivery_region_id,
        "receiver_city_id": order.delivery_city_id,
        "receiver_address": order.address_line,
        "receiver_legal_form_id": 1,
        "receiver_tax_code": receiver_tax_code,
        "receiver_phone": receiver_phone,
        "third_name": "",
        "third_phone": "",
        "third_tax_code": "",
        "package_id": order.delivery_package_id,
        "payer": "sender",
        "pay_method": "cashless",
        "cgd": 0,
        "comment": (order.note or "")[:250],
        "order_date": _easyway_order_date(),
        "weight": float(order.shipping_weight_kg),
        "quantity": quantity,
        "items": items,
    }


def _sender_settings():
    values = {
        "sender_name": settings.EASYWAY_SENDER_NAME,
        "sender_region_id": settings.EASYWAY_SENDER_REGION_ID,
        "sender_city_id": settings.EASYWAY_SENDER_CITY_ID,
        "sender_address": settings.EASYWAY_SENDER_ADDRESS,
        "sender_legal_form_id": settings.EASYWAY_SENDER_LEGAL_FORM_ID,
        "sender_tax_code": settings.EASYWAY_SENDER_TAX_CODE,
        "sender_phone": _normalize_georgian_mobile(
            settings.EASYWAY_SENDER_PHONE,
            "sender phone",
        ),
    }
    missing = [key for key, value in values.items() if value in {"", 0, None}]
    if missing:
        raise EasywayConfigurationError(
            f"Missing EasyWay sender configuration: {', '.join(missing)}"
        )
    return values


def _normalize_georgian_mobile(value, label):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) == 12 and digits.startswith("995"):
        digits = digits[3:]
    if len(digits) != 9 or not digits.startswith("5"):
        raise EasywayConfigurationError(
            f"EasyWay {label} must be a Georgian mobile number."
        )
    return digits


def _easyway_order_date(now=None):
    local_now = timezone.localtime(
        now or timezone.now(),
        timezone=EASYWAY_TIME_ZONE,
    )
    if local_now.time() >= time(hour=16):
        local_now += timedelta(days=1)
    return local_now.strftime("%Y-%m-%d %H:%M:%S")


def _validate_submission(order):
    if order.delivery_provider != "easyway":
        raise ValidationError("Only EasyWay regional orders can be submitted.")
    if order.payment_status != OrderPaymentStatus.PAID:
        raise ValidationError("Only paid orders can be submitted to EasyWay.")
    if order.status == OrderStatus.CANCELLED:
        raise ValidationError("Cancelled orders cannot be submitted to EasyWay.")
    if order.easyway_order_id is not None:
        raise ValidationError("This order already has an EasyWay order ID.")
    if order.easyway_shipment_state not in {
        EasywayShipmentState.NOT_SENT,
        EasywayShipmentState.FAILED,
    }:
        raise ValidationError(
            "This EasyWay submission cannot be retried without a manual check."
        )


def _record_failure(order_id, *, detail, outcome_unknown):
    state = (
        EasywayShipmentState.UNKNOWN
        if outcome_unknown
        else EasywayShipmentState.FAILED
    )
    Order.objects.filter(
        pk=order_id,
        easyway_shipment_state=EasywayShipmentState.SUBMITTING,
    ).update(
        easyway_shipment_state=state,
        easyway_last_error=detail[:1000],
        updated_at=timezone.now(),
    )
