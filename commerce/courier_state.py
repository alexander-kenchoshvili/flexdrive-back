"""Local-only guard shared by refund/stock flows; no provider requests."""

from .models import RedcapShipment, WingoShipment


def cancellation_required_message(order):
    name = {"redcap": "RedCap-ის", "wingo": "Wingo-ს"}.get(order.delivery_provider, "საკურიერო")
    return f"ჯერ დაადასტურეთ {name} გზავნილის გაუქმება."


def has_unsettled_courier_shipment(order):
    if not order:
        return False
    if order.delivery_provider == "redcap":
        shipment = RedcapShipment.objects.filter(order_id=order.pk).first()
        if shipment is None or shipment.state == "cancelled":
            return False
        return bool(shipment.tracking_number or shipment.state not in {"not_sent", "failed"})
    if order.delivery_provider == "wingo":
        shipment = WingoShipment.objects.filter(order_id=order.pk).first()
        return bool(shipment and (shipment.provider_order_id or shipment.tracking_number
                                 or shipment.state not in {"not_sent", "failed"}))
    return False
