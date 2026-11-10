"""Synthetic Wingo bookings for financial tests; never calls a provider."""
from django.utils import timezone

from .models import WingoShipment


def create_shipment(*, order, **values):
    state = values.get("state", "created")
    now = values.get("submitted_at") or timezone.now()
    if state == "cancelled":
        values.update(state="created", carrier_status=10, cancellation_verified_at=now, tracking_checked_at=now)
    if values.get("state", "created") == "created":
        values.setdefault("provider_order_id", f"wingo-{order.pk}")
        values.setdefault("tracking_number", f"999-{order.pk:07d}")
        values.setdefault("submitted_at", now)
    values.setdefault("state", "created")
    return WingoShipment.objects.create(order=order, **values)
