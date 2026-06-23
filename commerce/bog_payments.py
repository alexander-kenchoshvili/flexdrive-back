import threading
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote, urlparse

import requests
from django.conf import settings


BOG_CURRENCY = "GEL"
BOG_CAPTURE_MODE = "automatic"
BOG_PAYMENT_METHOD = "card"
MONEY_QUANTUM = Decimal("0.01")
MAX_SUPPORTED_AMOUNT = Decimal("9999999999.99")
MAX_TOKEN_CACHE_SECONDS = 60 * 60

SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "auth_code",
    "buyer",
    "card_number",
    "card_expiry_date",
    "client_secret",
    "cvv",
    "email",
    "expiry",
    "expiry_date",
    "full_name",
    "masked_email",
    "masked_phone",
    "pan",
    "payer_identifier",
    "phone",
    "phone_number",
    "secret",
    "secret_key",
}


class BogPaymentError(Exception):
    default_message = "BOG payment service request failed."

    def __init__(
        self,
        message=None,
        *,
        code="bog_payment_error",
        status_code=None,
        retryable=False,
        outcome_unknown=False,
    ):
        super().__init__(message or self.default_message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


class BogConfigurationError(BogPaymentError):
    default_message = "BOG payment service is not configured."


class BogValidationError(BogPaymentError):
    default_message = "Invalid BOG payment request."


class BogAuthenticationError(BogPaymentError):
    default_message = "BOG payment service authentication failed."


class BogTransportError(BogPaymentError):
    default_message = "BOG payment service is temporarily unavailable."


class BogResponseError(BogPaymentError):
    default_message = "BOG payment service returned an invalid response."


@dataclass(frozen=True)
class BogBasketItem:
    product_id: str
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class BogCreateOrderResult:
    order_id: str
    redirect_url: str
    details_url: str
    provider_reference: dict


@dataclass(frozen=True)
class BogPaymentDetails:
    order_id: str
    industry: str
    status: str
    external_order_id: str
    capture: str
    request_amount: Decimal
    transfer_amount: Decimal
    refund_amount: Decimal
    currency: str
    payment_method: str
    payment_option: str
    transaction_id: str
    response_code: str
    reject_reason: str
    provider_reference: dict
    actions: tuple["BogPaymentAction", ...] = ()


@dataclass(frozen=True)
class BogPaymentAction:
    action_id: str
    action: str
    status: str
    code: str
    amount: Decimal


@dataclass(frozen=True)
class BogRefundResult:
    key: str
    message: str
    action_id: str
    provider_reference: dict


class BogPaymentsClient:
    def __init__(
        self,
        *,
        client_id,
        client_secret,
        oauth_url,
        api_base_url,
        connect_timeout,
        read_timeout,
        token_refresh_skew_seconds=30,
        http_client=None,
        clock=None,
    ):
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.oauth_url = str(oauth_url or "").strip()
        self.api_base_url = str(api_base_url or "").strip().rstrip("/")
        self.timeout = (
            _positive_number(connect_timeout, "connect timeout"),
            _positive_number(read_timeout, "read timeout"),
        )
        self.token_refresh_skew_seconds = max(
            int(token_refresh_skew_seconds),
            0,
        )
        self.http_client = http_client or requests
        self.clock = clock or time.monotonic
        self._access_token = ""
        self._access_token_expires_at = 0.0
        self._token_lock = threading.Lock()
        self._validate_configuration()

    @classmethod
    def from_settings(cls, **overrides):
        if not settings.BOG_PAYMENTS_ENABLED:
            raise BogConfigurationError(code="bog_payments_disabled")
        values = {
            "client_id": settings.BOG_CLIENT_ID,
            "client_secret": settings.BOG_CLIENT_SECRET,
            "oauth_url": settings.BOG_OAUTH_URL,
            "api_base_url": settings.BOG_API_BASE_URL,
            "connect_timeout": settings.BOG_HTTP_CONNECT_TIMEOUT_SECONDS,
            "read_timeout": settings.BOG_HTTP_READ_TIMEOUT_SECONDS,
            "token_refresh_skew_seconds": (
                settings.BOG_TOKEN_REFRESH_SKEW_SECONDS
            ),
        }
        values.update(overrides)
        return cls(**values)

    def create_order(
        self,
        *,
        callback_url,
        success_url,
        fail_url,
        external_order_id,
        basket,
        total_amount,
        idempotency_key,
        delivery_amount=Decimal("0.00"),
        ttl_minutes=15,
        language="ka",
    ):
        normalized_key = _uuid4_string(idempotency_key)
        payload = self._build_create_order_payload(
            callback_url=callback_url,
            success_url=success_url,
            fail_url=fail_url,
            external_order_id=external_order_id,
            basket=basket,
            total_amount=total_amount,
            delivery_amount=delivery_amount,
            ttl_minutes=ttl_minutes,
        )
        response_data = self._api_request(
            "POST",
            "/payments/v1/ecommerce/orders",
            operation="create_order",
            idempotency_key=normalized_key,
            headers={
                "Accept-Language": _payment_language(language),
            },
            json=payload,
            outcome_unknown_on_transport_error=True,
        )

        order_id = _required_string(response_data, "id")
        links = response_data.get("_links")
        if not isinstance(links, dict):
            raise BogResponseError(code="bog_invalid_create_order_response")

        details_url = _required_link(links, "details")
        redirect_url = _required_link(links, "redirect")
        return BogCreateOrderResult(
            order_id=order_id,
            redirect_url=redirect_url,
            details_url=details_url,
            provider_reference=redact_bog_provider_data(response_data),
        )

    def get_payment_details(self, order_id):
        normalized_order_id = _provider_identifier(order_id, "order ID")
        response_data = self._api_request(
            "GET",
            f"/payments/v1/receipt/{quote(normalized_order_id, safe='')}",
            operation="get_payment_details",
        )
        return parse_bog_payment_details(
            response_data,
            expected_order_id=normalized_order_id,
        )

    def refund_full(self, *, order_id, idempotency_key):
        normalized_order_id = _provider_identifier(order_id, "order ID")
        normalized_key = _uuid4_string(idempotency_key)
        response_data = self._api_request(
            "POST",
            (
                "/payments/v1/payment/refund/"
                f"{quote(normalized_order_id, safe='')}"
            ),
            operation="refund_full",
            idempotency_key=normalized_key,
            json={},
            outcome_unknown_on_transport_error=True,
        )

        key = _required_string(response_data, "key")
        action_id = _required_string(response_data, "action_id")
        return BogRefundResult(
            key=key,
            message=str(response_data.get("message") or "").strip(),
            action_id=action_id,
            provider_reference=redact_bog_provider_data(response_data),
        )

    def _build_create_order_payload(
        self,
        *,
        callback_url,
        success_url,
        fail_url,
        external_order_id,
        basket,
        total_amount,
        delivery_amount,
        ttl_minutes,
    ):
        callback_url = _https_url(callback_url, "callback URL")
        success_url = _https_url(success_url, "success URL")
        fail_url = _https_url(fail_url, "fail URL")
        external_order_id = _provider_identifier(
            external_order_id,
            "external order ID",
        )
        total_amount = _money(total_amount, "total amount", positive=True)
        delivery_amount = _money(
            delivery_amount,
            "delivery amount",
            positive=False,
        )

        try:
            ttl_minutes = int(ttl_minutes)
        except (TypeError, ValueError) as error:
            raise BogValidationError(code="bog_invalid_ttl") from error
        if not 2 <= ttl_minutes <= 1440:
            raise BogValidationError(code="bog_invalid_ttl")

        basket_payload = []
        basket_total = Decimal("0.00")
        for raw_item in basket or ():
            item = _basket_item(raw_item)
            basket_total += item.unit_price * item.quantity
            basket_payload.append(
                {
                    "product_id": item.product_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": _json_money(item.unit_price),
                }
            )

        if not basket_payload:
            raise BogValidationError(code="bog_empty_basket")
        if (basket_total + delivery_amount).quantize(MONEY_QUANTUM) != total_amount:
            raise BogValidationError(code="bog_total_amount_mismatch")

        purchase_units = {
            "basket": basket_payload,
            "total_amount": _json_money(total_amount),
            "currency": BOG_CURRENCY,
        }
        if delivery_amount:
            purchase_units["delivery"] = {
                "amount": _json_money(delivery_amount),
            }

        return {
            "callback_url": callback_url,
            "external_order_id": external_order_id,
            "capture": BOG_CAPTURE_MODE,
            "purchase_units": purchase_units,
            "redirect_urls": {
                "success": success_url,
                "fail": fail_url,
            },
            "ttl": ttl_minutes,
            "payment_method": [BOG_PAYMENT_METHOD],
        }

    def _get_access_token(self, *, force_refresh=False):
        now = self.clock()
        if (
            not force_refresh
            and self._access_token
            and now < self._access_token_expires_at
        ):
            return self._access_token

        with self._token_lock:
            now = self.clock()
            if (
                not force_refresh
                and self._access_token
                and now < self._access_token_expires_at
            ):
                return self._access_token

            try:
                response = self.http_client.post(
                    self.oauth_url,
                    auth=(self.client_id, self.client_secret),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                    timeout=self.timeout,
                )
            except requests.RequestException as error:
                raise BogTransportError(
                    code="bog_auth_transport_error",
                    retryable=True,
                ) from error

            if response.status_code >= 400:
                raise BogAuthenticationError(
                    code=_http_error_code(
                        response,
                        fallback="bog_authentication_rejected",
                    ),
                    status_code=response.status_code,
                    retryable=_is_retryable_status(response.status_code),
                )

            response_data = _response_object(response)
            access_token = _required_string(response_data, "access_token")
            if str(response_data.get("token_type") or "").strip().lower() != "bearer":
                raise BogResponseError(
                    code="bog_invalid_authentication_response"
                )
            try:
                expires_in = float(response_data.get("expires_in"))
            except (TypeError, ValueError) as error:
                raise BogResponseError(
                    code="bog_invalid_authentication_response"
                ) from error
            if expires_in <= 0:
                raise BogResponseError(code="bog_invalid_authentication_response")

            cache_seconds = min(expires_in, MAX_TOKEN_CACHE_SECONDS)
            cache_seconds = max(
                cache_seconds - self.token_refresh_skew_seconds,
                0,
            )
            self._access_token = access_token
            self._access_token_expires_at = self.clock() + cache_seconds
            return access_token

    def _api_request(
        self,
        method,
        path,
        *,
        operation,
        idempotency_key=None,
        headers=None,
        json=None,
        outcome_unknown_on_transport_error=False,
    ):
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }
        if json is not None:
            request_headers["Content-Type"] = "application/json"
        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key
        request_headers.update(headers or {})

        url = f"{self.api_base_url}{path}"
        for attempt in range(2):
            try:
                response = self.http_client.request(
                    method,
                    url,
                    headers=request_headers.copy(),
                    json=json,
                    timeout=self.timeout,
                )
            except requests.RequestException as error:
                raise BogTransportError(
                    code=f"bog_{operation}_transport_error",
                    retryable=True,
                    outcome_unknown=outcome_unknown_on_transport_error,
                ) from error

            if response.status_code == 401 and attempt == 0:
                request_headers["Authorization"] = (
                    f"Bearer {self._get_access_token(force_refresh=True)}"
                )
                continue
            if response.status_code >= 400:
                raise BogResponseError(
                    code=_http_error_code(
                        response,
                        fallback=f"bog_{operation}_rejected",
                    ),
                    status_code=response.status_code,
                    retryable=_is_retryable_status(response.status_code),
                )
            return _response_object(response)

        raise BogAuthenticationError(code="bog_authentication_rejected")

    def _validate_configuration(self):
        if not self.client_id or not self.client_secret:
            raise BogConfigurationError(code="bog_credentials_missing")
        if not _is_https_url(self.oauth_url):
            raise BogConfigurationError(code="bog_oauth_url_invalid")
        if not _is_https_url(self.api_base_url):
            raise BogConfigurationError(code="bog_api_url_invalid")


def redact_bog_provider_data(value):
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).strip().lower() in SENSITIVE_KEYS
                else redact_bog_provider_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_bog_provider_data(item) for item in value]
    return value


def parse_bog_payment_details(response_data, *, expected_order_id=None):
    response_order_id = _required_string(response_data, "order_id")
    if expected_order_id is not None and response_order_id != str(
        expected_order_id
    ).strip():
        raise BogResponseError(code="bog_payment_details_order_mismatch")

    order_status = response_data.get("order_status")
    purchase_units = response_data.get("purchase_units")
    payment_detail = response_data.get("payment_detail") or {}
    if not isinstance(order_status, dict) or not isinstance(purchase_units, dict):
        raise BogResponseError(code="bog_invalid_payment_details_response")
    if not isinstance(payment_detail, dict):
        raise BogResponseError(code="bog_invalid_payment_details_response")

    transfer_method = payment_detail.get("transfer_method") or {}
    if not isinstance(transfer_method, dict):
        raise BogResponseError(code="bog_invalid_payment_details_response")
    actions = _parse_payment_actions(response_data.get("actions") or [])

    return BogPaymentDetails(
        order_id=response_order_id,
        industry=str(response_data.get("industry") or "").strip(),
        status=_required_string(order_status, "key").lower(),
        external_order_id=str(
            response_data.get("external_order_id") or ""
        ).strip(),
        capture=str(response_data.get("capture") or "").strip().lower(),
        request_amount=_money_from_response(
            purchase_units.get("request_amount"),
            "request amount",
        ),
        transfer_amount=_money_from_response(
            purchase_units.get("transfer_amount") or "0",
            "transfer amount",
        ),
        refund_amount=_money_from_response(
            purchase_units.get("refund_amount") or "0",
            "refund amount",
        ),
        currency=_required_string(purchase_units, "currency_code").upper(),
        payment_method=str(transfer_method.get("key") or "").strip().lower(),
        payment_option=str(
            payment_detail.get("payment_option") or ""
        ).strip().lower(),
        transaction_id=str(
            payment_detail.get("transaction_id") or ""
        ).strip(),
        response_code=str(payment_detail.get("code") or "").strip(),
        reject_reason=str(response_data.get("reject_reason") or "").strip(),
        provider_reference=redact_bog_provider_data(response_data),
        actions=actions,
    )


def _parse_payment_actions(raw_actions):
    if not isinstance(raw_actions, list):
        raise BogResponseError(code="bog_invalid_payment_actions")

    actions = []
    for raw_action in raw_actions:
        if not isinstance(raw_action, dict):
            raise BogResponseError(code="bog_invalid_payment_actions")
        actions.append(
            BogPaymentAction(
                action_id=_required_string(raw_action, "action_id"),
                action=_required_string(raw_action, "action").lower(),
                status=_required_string(raw_action, "status").lower(),
                code=str(raw_action.get("code") or "").strip(),
                amount=_money_from_response(
                    raw_action.get("amount") or "0",
                    "action amount",
                ),
            )
        )
    return tuple(actions)


def _basket_item(value):
    if isinstance(value, BogBasketItem):
        product_id = value.product_id
        description = value.description
        quantity = value.quantity
        unit_price = value.unit_price
    elif isinstance(value, dict):
        product_id = value.get("product_id")
        description = value.get("description")
        quantity = value.get("quantity")
        unit_price = value.get("unit_price")
    else:
        raise BogValidationError(code="bog_invalid_basket_item")

    product_id = _provider_identifier(product_id, "product ID")
    description = str(description or "").strip()
    try:
        normalized_quantity = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise BogValidationError(code="bog_invalid_basket_quantity") from error
    if (
        not normalized_quantity.is_finite()
        or normalized_quantity < 1
        or normalized_quantity != normalized_quantity.to_integral_value()
    ):
        raise BogValidationError(code="bog_invalid_basket_quantity")
    quantity = int(normalized_quantity)

    return BogBasketItem(
        product_id=product_id,
        description=description,
        quantity=quantity,
        unit_price=_money(unit_price, "unit price", positive=False),
    )


def _money(value, field_name, *, positive):
    try:
        raw_value = Decimal(str(value))
        normalized = raw_value.quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, TypeError, ValueError) as error:
        raise BogValidationError(
            code=f"bog_invalid_{field_name.replace(' ', '_')}"
        ) from error
    if not normalized.is_finite():
        raise BogValidationError(code=f"bog_invalid_{field_name.replace(' ', '_')}")
    if raw_value != normalized:
        raise BogValidationError(code=f"bog_invalid_{field_name.replace(' ', '_')}")
    if normalized > MAX_SUPPORTED_AMOUNT:
        raise BogValidationError(code=f"bog_invalid_{field_name.replace(' ', '_')}")
    if positive and normalized <= Decimal("0.00"):
        raise BogValidationError(code=f"bog_invalid_{field_name.replace(' ', '_')}")
    if not positive and normalized < Decimal("0.00"):
        raise BogValidationError(code=f"bog_invalid_{field_name.replace(' ', '_')}")
    return normalized


def _money_from_response(value, field_name):
    try:
        raw_value = Decimal(str(value))
        normalized = raw_value.quantize(MONEY_QUANTUM)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise BogResponseError(
            code=f"bog_invalid_{field_name.replace(' ', '_')}"
        ) from error
    if (
        not normalized.is_finite()
        or raw_value != normalized
        or normalized < Decimal("0.00")
    ):
        raise BogResponseError(code=f"bog_invalid_{field_name.replace(' ', '_')}")
    return normalized


def _json_money(value):
    return float(value)


def _uuid4_string(value):
    try:
        parsed = uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise BogValidationError(code="bog_invalid_idempotency_key") from error
    if parsed.version != 4:
        raise BogValidationError(code="bog_invalid_idempotency_key")
    return str(parsed)


def _provider_identifier(value, field_name):
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255:
        raise BogValidationError(
            code=f"bog_invalid_{field_name.replace(' ', '_')}"
        )
    return normalized


def _payment_language(value):
    normalized = str(value or "").strip().lower()
    if normalized not in {"ka", "en"}:
        raise BogValidationError(code="bog_invalid_payment_language")
    return normalized


def _https_url(value, field_name):
    normalized = str(value or "").strip()
    if not _is_https_url(normalized):
        raise BogValidationError(
            code=f"bog_invalid_{field_name.replace(' ', '_')}"
        )
    return normalized


def _is_https_url(value):
    parsed = urlparse(str(value or "").strip())
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _positive_number(value, field_name):
    try:
        normalized = float(value)
    except (TypeError, ValueError) as error:
        raise BogConfigurationError(
            code=f"bog_invalid_{field_name.replace(' ', '_')}"
        ) from error
    if normalized <= 0:
        raise BogConfigurationError(
            code=f"bog_invalid_{field_name.replace(' ', '_')}"
        )
    return normalized


def _required_string(data, key):
    if not isinstance(data, dict):
        raise BogResponseError(code="bog_invalid_response")
    value = str(data.get(key) or "").strip()
    if not value:
        raise BogResponseError(code="bog_invalid_response")
    return value


def _required_link(links, name):
    link = links.get(name)
    if not isinstance(link, dict):
        raise BogResponseError(code="bog_invalid_create_order_response")
    href = str(link.get("href") or "").strip()
    if not _is_https_url(href):
        raise BogResponseError(code="bog_invalid_create_order_response")
    return href


def _response_object(response):
    try:
        data = response.json()
    except (TypeError, ValueError) as error:
        raise BogResponseError(
            code="bog_invalid_json_response",
            status_code=getattr(response, "status_code", None),
        ) from error
    if not isinstance(data, dict):
        raise BogResponseError(
            code="bog_invalid_json_response",
            status_code=getattr(response, "status_code", None),
        )
    return data


def _http_error_code(response, *, fallback):
    try:
        data = response.json()
    except (TypeError, ValueError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    provider_code = str(data.get("key") or data.get("code") or "").strip()
    if not provider_code:
        return fallback
    safe_code = "".join(
        character
        for character in provider_code.lower()
        if character.isalnum() or character in {"_", "-"}
    )
    return f"bog_{safe_code[:60]}" if safe_code else fallback


def _is_retryable_status(status_code):
    return status_code in {408, 429} or status_code >= 500
