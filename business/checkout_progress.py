"""Checkout diagnostics use the existing basket and signed quote as sources of truth."""

import json

from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.utils.crypto import salted_hmac

from commerce.delivery_quote_data import contents_fingerprint, normalize_quote_items
from commerce.models import BuyNowSession, CartItem
from commerce.services import (
    BUY_NOW_TOKEN_COOKIE_NAME, CART_TOKEN_COOKIE_NAME, _is_buy_now_session_expired,
    build_checkout_owner_fingerprint, parse_guest_token,
)
from commerce.wingo_quotes import QUOTE_SIGNING_SALT

from .models import CheckoutProgress
from .payment_attempts import DELIVERY_LABELS, _amount


STAGE_LABELS = {
    "opened": "გაფორმების გვერდი გაიხსნა",
    "quoted": "მიტანის ფასი გამოჩნდა",
    "quote_error": "მიტანის ფასი ვერ გამოითვალა",
    "submitted": "გადახდას დააჭირა",
    "form_invalid": "ფორმა შევსებას ან შესწორებას ითხოვდა",
    "price_changed": "პროდუქტის განახლებული ფასი დასადასტურებელი იყო",
    "stock_changed": "პროდუქტის ხელმისაწვდომობა შეიცვალა",
    "submit_unconfirmed": "გადახდის მოთხოვნის დაწყება ვერ დადასტურდა",
}
SOURCES = {"cart": "კალათით", "buy_now": "ახლავე ყიდვით"}


def _digest(salt, value):
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    return salted_hmac(salt, encoded, algorithm="sha256").hexdigest()


def basket_key(identity):
    return _digest("business.checkout.basket.v1", identity)


def _basket(request, source):
    user = request.user if request.user.is_authenticated else None
    cookie = CART_TOKEN_COOKIE_NAME if source == "cart" else BUY_NOW_TOKEN_COOKIE_NAME
    token = None if user else parse_guest_token(request.COOKIES.get(cookie))
    if user is None and token is None:
        return None
    owner = {"user_id": user.pk} if user else {"guest_token": token, "user_id__isnull": True}
    if source == "cart":
        rows = list(CartItem.objects.filter(cart__is_active=True, **{
            f"cart__{key}": value for key, value in owner.items()
        }).select_related("product").only(
            "cart_id", "product_id", "quantity", "unit_price_snapshot", "product__shipping_weight_kg",
        ).order_by("product_id"))
        if not rows:
            return None
        reference = rows[0].cart_id
        if any(row.cart_id != reference for row in rows):
            return None
    else:
        session = BuyNowSession.objects.filter(**owner).select_related("product").first()
        if not session or _is_buy_now_session_expired(session):
            return None
        rows, reference = [session], session.pk
    items = tuple((row.product_id, row.quantity, _amount(row.unit_price_snapshot)) for row in rows)
    if any(price is None for _, _, price in items):
        return None
    identity = (build_checkout_owner_fingerprint(user=user, guest_token=token), source, reference, items, "GEL")
    return basket_key(identity), items, rows


def _quote(token, source, rows):
    payload = signing.loads(token, salt=QUOTE_SIGNING_SALT, max_age=settings.DELIVERY_QUOTE_MAX_AGE_SECONDS)
    service = payload.get("service_slug")
    amount = _amount(payload.get("customer_delivery_price"))
    if (payload.get("source") != source or service not in DELIVERY_LABELS or amount is None
            or payload.get("contents_fingerprint") != contents_fingerprint(normalize_quote_items(rows))):
        raise ValueError("Quote does not match checkout")
    return amount, service


def record_checkout_progress(request, values):
    source, stage = values["source"], values["stage"]
    current = _basket(request, source)
    if current is None:
        return
    key, items, rows = current
    amount, service = None, ""
    if stage == "quoted":
        amount, service = _quote(values["quote_token"], source, rows)
    # Exact repeat observations shortly after a refresh are stored once.
    slot = int(timezone.now().timestamp()) // 600
    event_key = _digest("business.checkout.event.v1", (key, stage, amount, service, slot))
    CheckoutProgress.objects.get_or_create(event_key=event_key, defaults={
        "basket_key": key, "items": items, "source": source, "stage": stage,
        "delivery_amount": amount, "delivery_service": service,
    })
