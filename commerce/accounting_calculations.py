"""Operational line calculations; callers must supply confirmed tax treatment.

No registration date, VAT rate or deductibility is inferred here. These results
are not a VAT return, purchase invoice or net-profit calculation.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


CALCULATION_VERSION = 1
CENT = Decimal("0.01")


def _decimal(value, *, maximum):
    if isinstance(value, (bool, float)):
        raise ValueError("Use Decimal, integer or decimal text, not float/bool.")
    try:
        value = Decimal(value)
        if not value.is_finite() or not 0 <= value <= maximum:
            raise ValueError("Amount or rate is outside the supported range.")
        return value
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid decimal value.") from exc


def _money(value):
    value = _decimal(value, maximum=Decimal("9999999999.99"))
    if value != value.quantize(CENT):
        raise ValueError("Gross money must have cent precision.")
    return value.quantize(CENT)


@dataclass(frozen=True)
class VatAmounts:
    gross: Decimal
    net: Decimal | None
    vat: Decimal | None
    rate: Decimal | None


def split_vat_inclusive(gross, *, vat_rate=None):
    gross = _money(gross)
    if vat_rate is None:
        return VatAmounts(gross, None, None, None)
    rate = _decimal(vat_rate, maximum=Decimal("100"))
    with localcontext() as context:
        context.prec = 40
        net = (gross / (1 + rate / 100)).quantize(CENT, rounding=ROUND_HALF_UP)
    return VatAmounts(gross, net, gross - net, rate)


@dataclass(frozen=True)
class ProductLineAmounts:
    quantity: int
    sale: VatAmounts
    purchase: VatAmounts | None
    net_markup: Decimal | None
    markup_percent: Decimal | None
    net_rounding_adjustment: Decimal | None
    calculation_version: int = CALCULATION_VERSION


def calculate_product_line(*, unit_sale_gross, quantity, unit_purchase_gross=None,
                           sale_vat_rate=None, purchase_vat_rate=None, purchase_total_gross=None):
    if type(quantity) is not int or not 1 <= quantity <= 2147483647:
        raise ValueError("Quantity must be a positive supported integer.")
    sale = split_vat_inclusive(_money(unit_sale_gross) * quantity, vat_rate=sale_vat_rate)
    purchase = None if unit_purchase_gross is None else split_vat_inclusive(
        _money(unit_purchase_gross) * quantity, vat_rate=purchase_vat_rate,
    )
    if purchase_total_gross is not None:
        # Actual lot totals avoid rounding a mixed-cost unit average before VAT.
        purchase = split_vat_inclusive(purchase_total_gross, vat_rate=purchase_vat_rate)
    markup = percent = adjustment = None
    if purchase is not None and purchase.net is not None and sale.net is not None:
        # Match the reference workbook: subtract before rounding. Expose the
        # residual between rounded columns, never silently lose a cent.
        with localcontext() as context:
            context.prec = 40
            exact_sale_net = sale.gross / (1 + sale.rate / 100)
            exact_purchase_net = purchase.gross / (1 + purchase.rate / 100)
            markup = (exact_sale_net - exact_purchase_net).quantize(CENT, rounding=ROUND_HALF_UP)
            adjustment = sale.net - purchase.net - markup
            if purchase.gross:
                percent = ((exact_sale_net / exact_purchase_net - 1) * 100).quantize(
                    Decimal("0.0000000001"), rounding=ROUND_HALF_UP,
                )
    return ProductLineAmounts(quantity, sale, purchase, markup, percent, adjustment)
