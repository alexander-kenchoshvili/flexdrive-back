"""Optional server-confirmed cart observations; storage cannot block shopping."""
import logging

from django.db import DatabaseError, transaction
from django.utils.crypto import salted_hmac

from .models import CartAddition


def record_cart_addition(request, item, quantity, event_id):
    if (not event_id or request.data.get("analytics_consent") is not True
            or request.headers.get("Origin", "").rstrip("/") != "https://flexdrive.ge"
            or (request.user.is_authenticated and request.user.is_staff)):
        return
    cart_key = salted_hmac("business.cart.v1", str(item.cart_id)).hexdigest()
    event_key = salted_hmac("business.cart.addition.v1", f"{item.cart_id}:{event_id}").hexdigest()
    values = {"cart_key": cart_key, "cart_id": item.cart_id, "product_id": item.product_id,
              "source_item_id": item.pk, "name": item.product.name[:500],
              "sku": (item.product.internal_sku or "")[:100], "quantity": quantity,
              "unit_price": item.unit_price_snapshot}

    def save():
        try:
            CartAddition.objects.get_or_create(event_key=event_key, defaults=values)
        except DatabaseError:
            logging.getLogger(__name__).warning("cart_addition_storage_unavailable")

    transaction.on_commit(save)
