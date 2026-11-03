"""RedCap transport. No automatic retries or checkout-time price requests.

Credentials stay in backend settings. Reference responses were verified with
read-only requests against the account's documented API on 2026-11-03.
"""

import math
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings


STANDARD_SERVICES = frozenset({
    "same_day", "next_day", "Dgesshemog", "KHVshemog",
    "RegionCity", "sofeli", "Magalmtiani",
})
LABEL_SIZES = frozenset({"a4", "a5", "zebra"})
MAX_LABEL_BYTES = 20 * 1024 * 1024


class RedcapError(Exception):
    """Safe to display to staff; never contains raw provider error text."""


class RedcapConfigurationError(RedcapError):
    pass


class RedcapTransportError(RedcapError):
    def __init__(self, *, outcome_unknown=False):
        self.outcome_unknown = outcome_unknown
        super().__init__("RedCap-თან კავშირი ვერ დამყარდა.")


class RedcapResponseError(RedcapError):
    def __init__(self, *, status_code=None, outcome_unknown=False):
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown
        super().__init__(f"RedCap-ის პასუხი ვერ დამუშავდა (HTTP {status_code}).")


class RedcapClient:
    def __init__(self, *, api_key, api_base_url, connect_timeout=5,
                 read_timeout=15, http_client=None):
        self.api_key = str(api_key or "").strip()
        self.api_base_url = str(api_base_url or "").strip().rstrip("/")
        parsed = urlsplit(self.api_base_url)
        if (not self.api_key or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise RedcapConfigurationError("RedCap-ის API პარამეტრები დაუსრულებელია.")
        try:
            self.timeout = (float(connect_timeout), float(read_timeout))
        except (ValueError, TypeError) as exc:
            raise RedcapConfigurationError("RedCap-ის ლოდინის დრო არასწორია.") from exc
        if any(not math.isfinite(v) or v <= 0 for v in self.timeout):
            raise RedcapConfigurationError("RedCap-ის ლოდინის დრო არასწორია.")
        self.http_client = http_client or requests

    @classmethod
    def from_settings(cls):
        return cls(
            api_key=settings.REDCAP_API_KEY,
            api_base_url=settings.REDCAP_API_BASE_URL,
            connect_timeout=settings.REDCAP_HTTP_CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.REDCAP_HTTP_READ_TIMEOUT_SECONDS,
        )

    def get_weight_options(self):
        return self._request("GET", "/weight-options")

    def get_locations(self):
        return self._request("GET", "/locations")

    def get_payment_options(self):
        return self._request("GET", "/payment-options")

    def get_statuses(self):
        return self._request("GET", "/statuses")

    def get_delivery_options(self, *, receiver_city, weight):
        """For verification/dispatch checks, never called by local tariff lookup."""
        city = str(receiver_city or "").strip()
        if not city:
            raise RedcapConfigurationError("RedCap-ის მიმღების ზონა აუცილებელია.")
        return self._request("GET", "/delivery-options", params={
            "receiver_city": city, "weight": str(positive_decimal(weight)),
        })

    def get_order(self, reference):
        return self._request("GET", f"/orders/{self._reference(reference)}")

    def get_orders_by_number(self, order_number):
        self._reference(order_number)
        return self._request("GET", "/orders", params={
            "order_number": str(order_number), "per_page": 200,
        })

    def get_tracking_statuses(self, tracking_numbers):
        numbers = list(tracking_numbers)
        if not 1 <= len(numbers) <= 1000:
            raise RedcapConfigurationError("საჭიროა 1–1000 განსხვავებული თრექინგი.")
        for number in numbers:
            self._reference(number)
        if len(set(numbers)) != len(numbers):
            raise RedcapConfigurationError("საჭიროა 1–1000 განსხვავებული თრექინგი.")
        # This documented POST only reads statuses; it never creates a shipment.
        return self._request("POST", "/orders/statuses", json={"tracking_numbers": numbers})

    def create_order(self, payload):
        if not isinstance(payload, dict):
            raise RedcapConfigurationError("გზავნილის მონაცემები არასწორია.")
        if (payload.get("delivery_type") not in STANDARD_SERVICES
                or payload.get("payment_type") != "transfer"
                or payload.get("delivery_payer") != "sender"
                or payload.get("additional_services") not in (None, [])
                or payload.get("item_price", 0) != 0):
            raise RedcapConfigurationError("გზავნილის დამატებითი სერვისები გამორთულია.")
        result = self._request("POST", "/orders", json=payload, mutation=True)
        order = result.get("order")
        if not isinstance(order, dict):
            raise RedcapResponseError(status_code=200, outcome_unknown=True)
        try:
            self._reference(order.get("tracking_number"))
        except RedcapConfigurationError as exc:
            raise RedcapResponseError(status_code=200, outcome_unknown=True) from exc
        return order

    def cancel_order(self, tracking_number, *, reason):
        reason = str(reason or "").strip()
        if not reason or len(reason) > 500:
            raise RedcapConfigurationError("მიუთითეთ გაუქმების მიზეზი (მაქს. 500 სიმბოლო).")
        return self._request("POST", f"/orders/{self._reference(tracking_number)}/cancel",
                             json={"reason": reason}, mutation=True)

    def get_label(self, tracking_number, *, size="a4"):
        if size not in LABEL_SIZES:
            raise RedcapConfigurationError("სტიკერის ფორმატი არასწორია.")
        return self._request("GET", f"/orders/{self._reference(tracking_number)}/label",
                             params={"size": size}, pdf=True)

    @staticmethod
    def _reference(value):
        # Text is intentional: leading zeroes are significant in RedCap tracking.
        if (not isinstance(value, str) or not value.strip() or len(value) > 150
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise RedcapConfigurationError("თრექინგი/შეკვეთის ნომერი არასწორია.")
        return quote(value.strip(), safe="")

    def _request(self, method, path, *, params=None, json=None, mutation=False, pdf=False):
        kwargs = {
            "headers": {"X-API-Key": self.api_key,
                        "Accept": "application/pdf" if pdf else "application/json"},
            "params": params, "timeout": self.timeout, "allow_redirects": False,
        }
        if json is not None:
            kwargs["json"] = json
        if pdf:
            kwargs["stream"] = True
        try:
            response = self.http_client.request(method, self.api_base_url + path, **kwargs)
        except requests.RequestException as exc:
            raise RedcapTransportError(outcome_unknown=mutation) from exc
        status = response.status_code
        if not 200 <= status < 300:
            response.close()
            raise RedcapResponseError(status_code=status, outcome_unknown=(
                mutation and (status >= 500 or status in {408, 429} or 300 <= status < 400)
            ))
        if pdf:
            try:
                if response.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/pdf":
                    raise RedcapResponseError(status_code=status)
                data = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > MAX_LABEL_BYTES:
                        raise RedcapResponseError(status_code=status)
                if not data.startswith(b"%PDF-"):
                    raise RedcapResponseError(status_code=status)
                return bytes(data)
            except requests.RequestException as exc:
                raise RedcapTransportError() from exc
            finally:
                response.close()
        try:
            body = response.json()
        except ValueError as exc:
            raise RedcapResponseError(status_code=status, outcome_unknown=mutation) from exc
        finally:
            response.close()
        if not isinstance(body, dict) or body.get("success") is not True:
            # A success-shaped HTTP response with an unclear body cannot prove
            # that a create/cancel failed. Never automatically retry it.
            raise RedcapResponseError(status_code=status, outcome_unknown=mutation)
        return body


def positive_decimal(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise RedcapConfigurationError("წონა უნდა იყოს დადებითი რიცხვი.") from exc
    if not result.is_finite() or result <= 0:
        raise RedcapConfigurationError("წონა უნდა იყოს დადებითი რიცხვი.")
    return result
