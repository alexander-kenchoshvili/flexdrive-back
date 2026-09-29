"""Private purchase-price facts, not invoices or confirmed VAT deductions."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone


COST_FIELDS = ("purchase_unit_gross", "purchase_cost_source", "purchase_cost_recorded_at")


def build_purchase_snapshot(product):
    amount = product.supplier_price
    return {
        "version": 1,
        "purchase_unit_gross": None if amount is None else format(amount, ".2f"),
        "source": "catalog_supplier_price" if amount is not None else "unavailable",
        "recorded_at": timezone.now().isoformat(),
    }


def purchase_snapshot_fields(snapshot):
    """Normalize an optional version-1 block; absent legacy facts stay unknown."""
    if snapshot is None:
        return {"purchase_unit_gross": None,
            "purchase_cost_source": "", "purchase_cost_recorded_at": None,
        }
    try:
        if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int or snapshot["version"] != 1:
            raise ValueError
        source = snapshot["source"]
        raw_amount = snapshot["purchase_unit_gross"]
        if raw_amount is None:
            if source != "unavailable":
                raise ValueError
            amount = None
        else:
            if source != "catalog_supplier_price" or not isinstance(raw_amount, str):
                raise ValueError
            amount = Decimal(raw_amount)
            if not amount.is_finite() or not Decimal("0") <= amount <= Decimal("99999999.99"):
                raise ValueError
            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError
        recorded_at = datetime.fromisoformat(snapshot["recorded_at"])
        if timezone.is_naive(recorded_at):
            raise ValueError
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Invalid purchase accounting snapshot.") from exc
    return {
        "purchase_unit_gross": amount,
        "purchase_cost_source": source,
        "purchase_cost_recorded_at": recorded_at,
    }
