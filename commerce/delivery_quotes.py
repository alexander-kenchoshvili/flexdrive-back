"""Stable delivery imports; the active implementation is RedCap."""

from .redcap_quotes import (
    DeliveryLocation, DeliveryQuoteError, QUOTE_SIGNING_SALT,
    build_delivery_quote, delivery_locations, delivery_order_fields,
    resolve_checkout_delivery, resolve_delivery_location, validate_delivery_quote,
)
