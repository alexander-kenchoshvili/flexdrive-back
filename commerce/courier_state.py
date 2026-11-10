"""Local-only guard shared by refund/stock flows; no provider requests."""

from .models import WingoShipment


def cancellation_required_message(order):
    name = {"wingo": "Wingo-ს"}.get(order.delivery_provider, "საკურიერო")
    return f"ჯერ დაადასტურეთ {name} გზავნილის გაუქმება."


def wingo_cancellation_verified(shipment):
    """Only an accepted authenticated status read releases the outbound guard."""
    return bool(
        shipment and shipment.state == "created" and shipment.carrier_status == 10
        and shipment.cancellation_verified_at and shipment.tracking_checked_at
        and not shipment.tracking_error and not shipment.tracking_token
        and (not shipment.webhook_received_at or (shipment.webhook_checked_at
             and shipment.webhook_checked_at >= shipment.webhook_received_at))
    )


def has_unsettled_courier_shipment(order):
    if not order:
        return False
    if order.delivery_provider == "wingo":
        shipment = WingoShipment.objects.filter(order_id=order.pk).first()
        if wingo_cancellation_verified(shipment):
            return False
        return bool(shipment and (shipment.provider_order_id or shipment.tracking_number
                                 or shipment.state not in {"not_sent", "failed"}))
    return False
