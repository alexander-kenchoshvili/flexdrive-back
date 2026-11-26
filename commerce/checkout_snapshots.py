"""Frozen checkout evidence shared by online payment providers.

Provider request expiry is independent of the local stock-reservation expiry.
BOG keeps its existing expiry value and byte-compatible snapshot hash.
"""
import hashlib
import json
from decimal import Decimal

from .images import build_product_primary_image_snapshot
from .accounting_snapshots import build_purchase_snapshot
from .delivery_quotes import delivery_order_fields, resolve_checkout_delivery

CHECKOUT_SNAPSHOT_VERSION = 1


def is_checkout_snapshot_intact(snapshot):
    if not isinstance(snapshot, dict):
        return False
    expected_hash = str(snapshot.get("integrity_hash") or "").strip()
    if not expected_hash:
        return False
    hash_payload = {
        key: value
        for key, value in snapshot.items()
        if key != "integrity_hash"
    }
    return snapshot_hash(hash_payload) == expected_hash


def build_checkout_snapshot(
    *,
    reservation,
    source,
    source_reference,
    user,
    validated_data,
    terms_acceptance,
    owner_fingerprint,
    request_fingerprint,
    provider_expires_at,
    marketing_consent,
    marketing_context,
):
    reservation_items = list(
        reservation.items.select_related("product", "product__category")
        .prefetch_related("product__images")
        .order_by("id")
    )
    items = []
    subtotal = Decimal("0.00")
    cart_item_ids = source_reference.get("cart_item_ids", {})
    persisted_source_reference = {
        key: value
        for key, value in source_reference.items()
        if key != "cart_item_ids"
    }

    for reservation_item in reservation_items:
        product = reservation_item.product
        line_total = (
            reservation_item.unit_price_snapshot * reservation_item.quantity
        )
        subtotal += line_total
        items.append(
            {
                "product_id": product.pk,
                "provider_product_id": product.display_sku,
                "source_item_id": cart_item_ids.get(product.pk),
                "product_name": product.name,
                "sku": product.sku,
                "internal_sku": product.internal_sku or "",
                "accounting": build_purchase_snapshot(product),
                "unit_price": decimal_string(
                    reservation_item.unit_price_snapshot
                ),
                "quantity": reservation_item.quantity,
                "line_total": decimal_string(line_total),
                "primary_image_snapshot": build_product_primary_image_snapshot(
                    product
                ),
            }
        )

    delivery_quote = resolve_checkout_delivery(
        validated_data=validated_data,
        source=source,
        items=reservation_items,
    )
    delivery_fields = delivery_order_fields(delivery_quote)
    delivery_price = delivery_fields["delivery_price"]
    terms_fields = terms_acceptance.to_order_fields()
    snapshot = {
        "version": CHECKOUT_SNAPSHOT_VERSION,
        "source": source,
        "source_reference": persisted_source_reference,
        "owner_fingerprint": owner_fingerprint,
        "request_fingerprint": request_fingerprint,
        "user_id": (
            user.pk
            if user is not None and getattr(user, "is_authenticated", True)
            else None
        ),
        "buyer": {
            "buyer_type": validated_data.get("buyer_type", "individual"),
            "personal_number": validated_data.get("personal_number", ""),
            "company_name": validated_data.get("company_name", ""),
            "company_is_vat_registered": validated_data.get("company_is_vat_registered"),
            "company_identification_code": validated_data.get(
                "company_identification_code",
                "",
            ),
            "first_name": validated_data["first_name"],
            "last_name": validated_data["last_name"],
            "email": validated_data.get("email", ""),
            "phone": validated_data["phone"],
            "city": validated_data["city"],
            "address_line": validated_data["address_line"],
            "note": validated_data.get("note", ""),
        },
        "items": items,
        "delivery": delivery_quote,
        "totals": {
            "subtotal": decimal_string(subtotal),
            "delivery": decimal_string(delivery_price),
            "total": decimal_string(subtotal + delivery_price),
            "currency": "GEL",
        },
        "terms": {
            "accepted_at": terms_fields["terms_accepted_at"].isoformat(),
            "version": terms_fields["terms_version"],
            "content_hash": terms_fields["terms_content_hash"],
            "content_snapshot": terms_fields["terms_content_snapshot"],
            "url": terms_fields["terms_url"],
            "ip_address": terms_fields["terms_ip_address"],
            "user_agent": terms_fields["terms_user_agent"],
        },
        "marketing": {
            "consent": bool(marketing_consent),
            "context": marketing_context or {},
        },
        "provider_order_expires_at": provider_expires_at.isoformat() if provider_expires_at is not None else None,
        "reservation_expires_at": reservation.expires_at.isoformat(),
    }
    snapshot["integrity_hash"] = snapshot_hash(snapshot)
    return snapshot


def snapshot_hash(snapshot):
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decimal_string(value):
    return f"{Decimal(value):.2f}"

