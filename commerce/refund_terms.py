"""Frozen settlement for a full goods return with an agreed return-delivery deduction."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


ZERO = Decimal("0.00")
QUANTUM = Decimal("0.01")


def money(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < ZERO or amount > Decimal("9999999999.99") or amount != amount.quantize(QUANTUM):
            raise ValueError
        return amount.quantize(QUANTUM)
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValidationError("თანხა მიუთითეთ სწორად, მაქსიმუმ ორი ათწილადით.") from exc


def build_settlement(*, total, cost, payer, agreed=False, reason=""):
    total, cost = money(total), money(cost)
    if payer not in {"merchant", "customer"}:
        raise ValidationError("აირჩიეთ, ვინ იხდის უკუმიტანის საფასურს.")
    reason = str(reason or "").strip()
    retained = cost if payer == "customer" else ZERO
    if payer == "customer" and (cost <= ZERO or agreed is not True or not reason or len(reason) > 500):
        raise ValidationError("მომხმარებლისგან დასაქვითად მიუთითეთ ხარჯი, მიზეზი და დაადასტურეთ მასთან შეთანხმება.")
    if retained >= total:
        raise ValidationError("დასაქვითი საფასური გადახდილ თანხაზე ნაკლები უნდა იყოს.")
    return {"version": 1, "kind": "whole_order_return", "paid_total": format(total, ".2f"),
            "return_delivery_cost": format(cost, ".2f"), "return_delivery_payer": payer,
            "retained_return_fee": format(retained, ".2f"), "refund_amount": format(total - retained, ".2f"),
            "customer_agreed": agreed is True if payer == "customer" else False,
            "deduction_reason": reason if payer == "customer" else ""}


def settlement_for_refund(refund, *, total):
    reference = refund.provider_reference if isinstance(refund.provider_reference, dict) else {}
    context = reference.get("refund_request", {})
    raw = context.get("settlement") if isinstance(context, dict) else None
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValidationError("დაბრუნების შენახული პირობები არასწორია.")
    expected = build_settlement(total=total, cost=raw.get("return_delivery_cost"),
        payer=raw.get("return_delivery_payer"), agreed=raw.get("customer_agreed"), reason=raw.get("deduction_reason"))
    if raw != expected or money(refund.amount) != money(expected["refund_amount"]):
        raise ValidationError("დაბრუნების თანხა შენახულ პირობებს არ ემთხვევა.")
    return expected
