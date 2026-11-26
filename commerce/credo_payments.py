"""Narrow client for Credo's documented widget order and status API.

No live credentials/default endpoints, checkout hooks, automatic POST retries,
financial mutations, or bank-response PII. Callers own submission reconciliation.
"""

import hashlib
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests

from .credo_status import CredoStatus, parse_credo_status


MAX_AMOUNT = Decimal("9999999999.99")
DELIVERY_PRODUCT_ID = "FLEXDRIVE_DELIVERY"
_ORDER_CODE = re.compile(r"\A[A-Za-z0-9_]{1,50}\Z")


class CredoPaymentError(Exception):
    """Only safe codes and flags; never attach a response, URL, or raw error."""

    def __init__(self, *, code, status_code=None, outcome_unknown=False, retryable=False):
        super().__init__("Credo service operation could not be completed.")
        self.code = code
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown
        self.retryable = retryable


class CredoConfigurationError(CredoPaymentError):
    pass


class CredoValidationError(CredoPaymentError):
    pass


class CredoTransportError(CredoPaymentError):
    pass


class CredoResponseError(CredoPaymentError):
    pass


@dataclass(frozen=True)
class CredoProduct:
    product_id: str
    title: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class CredoCreateOrderResult:
    redirect_url: str = field(repr=False)


@dataclass(frozen=True)
class CredoStatusResult:
    application_status: CredoStatus


class CredoPaymentsClient:
    def __init__(
        self, *, merchant_id, secret_key, order_url, status_url,
        redirect_origin, connect_timeout=5, read_timeout=15, http_client=None,
    ):
        if not isinstance(merchant_id, str) or not re.fullmatch(r"[0-9]{1,64}", merchant_id):
            raise CredoConfigurationError(code="credo_invalid_merchant_id")
        if int(merchant_id) < 1:
            raise CredoConfigurationError(code="credo_invalid_merchant_id")
        if not isinstance(secret_key, str) or not secret_key.strip():
            raise CredoConfigurationError(code="credo_missing_secret_key")
        self._merchant_id = merchant_id
        self._secret_key = secret_key  # Significant spaces must not be trimmed.
        self._order_url = _https_url(order_url)
        self._status_url = _https_url(status_url)
        origin_url = _https_url(redirect_origin)
        origin = urlsplit(origin_url)
        if origin.path not in ("", "/"):
            raise CredoConfigurationError(code="credo_invalid_redirect_origin")
        self._redirect_origin = (origin.hostname, origin.port or 443)
        self.timeout = (_timeout(connect_timeout), _timeout(read_timeout))
        self.http_client = http_client if http_client is not None else requests

    @property
    def merchant_id(self):
        return self._merchant_id

    def create_order(
        self, *, order_code, products, total_amount,
        delivery_amount=Decimal("0.00"), currency="GEL",
    ):
        order_code = _order_code(order_code)
        if currency != "GEL":
            raise CredoValidationError(code="credo_invalid_currency")
        amount = _tetri(total_amount)
        if not isinstance(products, (list, tuple)) or not products:
            raise CredoValidationError(code="credo_empty_products")
        basket = [_product_payload(product) for product in products]
        if any(item["id"] == DELIVERY_PRODUCT_ID for item in basket):
            raise CredoValidationError(code="credo_reserved_product_id")
        delivery_tetri = _tetri(delivery_amount, allow_zero=True)
        if delivery_tetri:
            # One financed total. Delivery is an explicit basket line so product
            # unit prices/quantities remain intact. Bank acceptance of this line
            # will be checked in the agreed live test; no extra API field is used.
            basket.append({
                "id": DELIVERY_PRODUCT_ID, "title": "მიწოდება", "amount": 1,
                "price": delivery_tetri, "type": "0",
            })
        if sum(item["price"] * item["amount"] for item in basket) != amount:
            raise CredoValidationError(code="credo_total_mismatch")
        # The exact ordered strings used for the checksum are sent unchanged.
        signature = "".join(
            str(item[key]) for item in basket for key in ("id", "title", "amount", "price", "type")
        ) + self._secret_key
        payload = {
            "merchantId": self._merchant_id, "orderCode": order_code,
            "check": _md5(signature), "products": basket,
        }
        body = self._request("POST", self._order_url, json=payload)
        # No undocumented error response is treated as proof that no application
        # exists. A timeout/invalid reply must not trigger a new financing request.
        if type(body.get("status")) is not int or body["status"] != 200:
            raise CredoResponseError(code="credo_create_result_unknown", outcome_unknown=True)
        data = body.get("data")
        redirect_url = data.get("URL") if isinstance(data, dict) else None
        if not self._valid_redirect(redirect_url):
            raise CredoResponseError(code="credo_invalid_redirect", outcome_unknown=True)
        return CredoCreateOrderResult(redirect_url=redirect_url)

    def get_status(self, *, order_code):
        order_code = _order_code(order_code)
        query = {
            "merchantId": self._merchant_id, "orderCode": order_code,
            "hash": _md5(self._merchant_id + order_code + self._secret_key),
        }
        body = self._request("GET", self._status_url, params=query)
        code = body.get("status")
        if type(code) is not int or code != 200:
            issue = {
                300: "credo_duplicate_application", 400: "credo_status_request_rejected",
                404: "credo_application_not_found",
            }.get(code) if type(code) is int else None
            raise CredoResponseError(code=issue or "credo_invalid_status_envelope")
        try:
            application_status = parse_credo_status(body.get("data"))
        except ValueError:
            raise CredoResponseError(code="credo_unknown_application_status") from None
        # Discard info (name, personal number and mobile), messages, and any
        # undocumented fields. None enters the return value or error message.
        return CredoStatusResult(application_status=application_status)

    def _request(self, method, url, **kwargs):
        is_create = method == "POST"
        try:
            response = self.http_client.request(
                method, url, headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=self.timeout, allow_redirects=False, **kwargs,
            )
        except requests.RequestException:
            raise CredoTransportError(
                code="credo_transport_error", outcome_unknown=is_create, retryable=not is_create,
            ) from None
        http_code = response.status_code
        if type(http_code) is not int or http_code != 200:
            known_code = http_code if type(http_code) is int else None
            raise CredoResponseError(
                code="credo_http_error", status_code=known_code, outcome_unknown=is_create,
                retryable=not is_create and known_code is not None and (known_code == 429 or known_code >= 500),
            )
        try:
            body = response.json()
        except (ValueError, TypeError):
            raise CredoResponseError(code="credo_invalid_json", outcome_unknown=is_create) from None
        if not isinstance(body, dict):
            raise CredoResponseError(code="credo_invalid_response", outcome_unknown=is_create)
        return body

    def _valid_redirect(self, value):
        return _redirect_matches_origin(value, self._redirect_origin)


def is_allowed_credo_redirect(value, *, origin):
    """Validate a saved continuation URL without needing credentials or HTTP."""
    try:
        parsed = urlsplit(_https_url(origin))
    except CredoConfigurationError:
        return False
    if parsed.path not in ("", "/"):
        return False
    return _redirect_matches_origin(value, (parsed.hostname, parsed.port or 443))


def _redirect_matches_origin(value, origin):
    try:
        parsed = urlsplit(_https_url(value))
    except CredoConfigurationError:
        return False
    return (
        (parsed.hostname, parsed.port or 443) == origin
        and parsed.path.startswith("/installment/")
        and len(parsed.path) > len("/installment/")
        and not any(part in (".", "..") for part in parsed.path.split("/"))
        and "%" not in parsed.path
    )


def _https_url(value):
    try:
        if not isinstance(value, str) or not value or any(character.isspace() for character in value):
            raise ValueError
        if any(ord(character) < 32 or ord(character) == 127 for character in value) or "\\" in value:
            raise ValueError
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment):
            raise ValueError
        _ = parsed.port  # Validate malformed/out-of-range ports now.
    except (ValueError, TypeError):
        raise CredoConfigurationError(code="credo_invalid_https_url") from None
    return value


def _timeout(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError
        return value
    except (ValueError, TypeError, OverflowError):
        raise CredoConfigurationError(code="credo_invalid_timeout") from None


def _order_code(value):
    if not isinstance(value, str) or _ORDER_CODE.fullmatch(value) is None:
        raise CredoValidationError(code="credo_invalid_order_code")
    return value


def _tetri(value, *, allow_zero=False):
    try:
        if isinstance(value, (bool, float)) or not isinstance(value, (Decimal, str, int)):
            raise ValueError
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount > MAX_AMOUNT or (not allow_zero and amount == 0):
            raise ValueError
        tetri = amount * 100
        if tetri != tetri.to_integral_value():
            raise ValueError
        return int(tetri)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise CredoValidationError(code="credo_invalid_amount") from None


def _product_payload(product):
    if not isinstance(product, CredoProduct):
        raise CredoValidationError(code="credo_invalid_product")
    if type(product.quantity) is not int or product.quantity < 1:
        raise CredoValidationError(code="credo_invalid_quantity")
    for value in (product.product_id, product.title):
        if (not isinstance(value, str) or not value.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in value)):
            raise CredoValidationError(code="credo_invalid_product_text")
    return {
        "id": product.product_id, "title": product.title, "amount": product.quantity,
        "price": _tetri(product.unit_price), "type": "0",
    }


def _md5(value):
    # Mandated by the bank protocol; do not substitute a different algorithm.
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
