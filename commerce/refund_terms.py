"""Frozen cash settlement, with separate paid outbound and return deductions."""

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


def build_settlement(*, total, cost, payer, agreed=False, reason="", outbound_delivery=None):
    total, cost = money(total), money(cost)
    outbound = money(outbound_delivery) if outbound_delivery is not None else ZERO
    if outbound > total:
        raise ValidationError("მიტანის თანხა გადახდილ თანხას აღემატება.")
    if payer not in {"merchant", "customer"}:
        raise ValidationError("აირჩიეთ, ვინ იხდის უკუმიტანის საფასურს.")
    reason = str(reason or "").strip()
    retained = cost if payer == "customer" else ZERO
    retained_delivery = outbound if payer == "customer" else ZERO
    deduction = retained + retained_delivery
    if payer == "customer" and (deduction <= ZERO or agreed is not True or not reason or len(reason) > 500):
        raise ValidationError("მომხმარებლისგან დასაქვითად მიუთითეთ ხარჯი, მიზეზი და დაადასტურეთ მასთან შეთანხმება.")
    if deduction >= total:
        raise ValidationError("დასაქვითი საფასური გადახდილ თანხაზე ნაკლები უნდა იყოს.")
    terms = {"version": 1, "kind": "whole_order_return", "paid_total": format(total, ".2f"),
            "return_delivery_cost": format(cost, ".2f"), "return_delivery_payer": payer,
            "retained_return_fee": format(retained, ".2f"), "refund_amount": format(total - deduction, ".2f"),
            "customer_agreed": agreed is True if payer == "customer" else False,
            "deduction_reason": reason if payer == "customer" else ""}
    if outbound_delivery is not None:
        terms.update(version=2, outbound_delivery_price=format(outbound, ".2f"),
                     retained_delivery_fee=format(retained_delivery, ".2f"))
    return terms


def validate_settlement(raw, *, total, outbound_delivery=None):
    """Read frozen v1/v2 terms; booking a v2 request also checks the paid delivery."""
    if not isinstance(raw, dict) or type(raw.get("version")) is not int or raw["version"] not in {1, 2}:
        raise ValidationError("დაბრუნების შენახული პირობები არასწორია.")
    extra = {}
    if raw["version"] == 2:
        extra["outbound_delivery"] = (raw.get("outbound_delivery_price")
                                      if outbound_delivery is None else outbound_delivery)
        # Missing v2 money must not silently select the v1 calculation.
        money(extra["outbound_delivery"])
    expected = build_settlement(total=total, cost=raw.get("return_delivery_cost"),
        payer=raw.get("return_delivery_payer"), agreed=raw.get("customer_agreed"),
        reason=raw.get("deduction_reason"), **extra)
    if raw != expected:
        raise ValidationError("დაბრუნების თანხა შენახულ პირობებს არ ემთხვევა.")
    return expected


def settlement_for_refund(refund, *, total):
    reference = refund.provider_reference if isinstance(refund.provider_reference, dict) else {}
    context = reference.get("refund_request", {})
    raw = context.get("settlement") if isinstance(context, dict) else None
    if raw is None:
        return None
    expected = validate_settlement(raw, total=total)
    if money(refund.amount) != money(expected["refund_amount"]):
        raise ValidationError("დაბრუნების თანხა შენახულ პირობებს არ ემთხვევა.")
    return expected
