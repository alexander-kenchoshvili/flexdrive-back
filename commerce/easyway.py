import requests
from decimal import Decimal, InvalidOperation
from django.conf import settings


class EasywayError(Exception):
    pass


class EasywayConfigurationError(EasywayError):
    pass


class EasywayTransportError(EasywayError):
    pass


class EasywayResponseError(EasywayError):
    def __init__(self, message, *, status_code=None, outcome_unknown=False):
        super().__init__(message)
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown


class EasywayClient:
    def __init__(
        self,
        *,
        api_user,
        api_key,
        api_base_url,
        connect_timeout,
        read_timeout,
        http_client=None,
    ):
        self.api_user = str(api_user or "").strip()
        self.api_key = str(api_key or "").strip()
        self.api_base_url = str(api_base_url or "").strip().rstrip("/")
        self.timeout = (
            self._positive_timeout(connect_timeout, "connect timeout"),
            self._positive_timeout(read_timeout, "read timeout"),
        )
        self.http_client = http_client or requests
        self._validate_configuration()

    @classmethod
    def from_settings(cls, **overrides):
        values = {
            "api_user": settings.EASYWAY_API_USER,
            "api_key": settings.EASYWAY_API_KEY,
            "api_base_url": settings.EASYWAY_API_BASE_URL,
            "connect_timeout": settings.EASYWAY_HTTP_CONNECT_TIMEOUT_SECONDS,
            "read_timeout": settings.EASYWAY_HTTP_READ_TIMEOUT_SECONDS,
        }
        values.update(overrides)
        return cls(**values)

    def get_server_time(self):
        payload = self._get("/time")
        if not isinstance(payload, dict) or not isinstance(payload.get("time"), str):
            raise EasywayResponseError(
                "EasyWay API returned an invalid time response."
            )
        return payload["time"]

    def get_regions(self, *, language="ka"):
        return self._list_response(
            self._get("/region", params={"lang": language}),
            "region",
        )

    def get_cities(self, region_id, *, language="ka"):
        try:
            normalized_region_id = int(region_id)
        except (TypeError, ValueError) as error:
            raise EasywayConfigurationError(
                "EasyWay region ID must be a positive integer."
            ) from error
        if normalized_region_id <= 0:
            raise EasywayConfigurationError(
                "EasyWay region ID must be a positive integer."
            )
        return self._list_response(
            self._get(
                f"/city/{normalized_region_id}",
                params={"lang": language},
            ),
            "city",
        )

    def get_packages(self, *, language="ka"):
        return self._list_response(
            self._get("/package", params={"lang": language}),
            "package",
        )

    def get_legal_forms(self, *, language="ka"):
        return self._list_response(
            self._get("/legal-form", params={"lang": language}),
            "legalForm",
        )

    def get_shipping_price(
        self,
        *,
        length,
        width,
        height,
        weight,
        from_city_id,
        to_city_id,
        package_id,
    ):
        payload = {
            "length": self._positive_number(length, "length"),
            "width": self._positive_number(width, "width"),
            "height": self._positive_number(height, "height"),
            "weight": self._positive_number(weight, "weight"),
            "from_city_id": self._positive_integer(from_city_id, "from city ID"),
            "to_city_id": self._positive_integer(to_city_id, "to city ID"),
            "package_id": self._positive_integer(package_id, "package ID"),
        }
        response = self._post("/price", json=payload)
        if not isinstance(response, dict):
            raise EasywayResponseError(
                "EasyWay API returned an invalid price response."
            )
        try:
            price = Decimal(str(response.get("price")))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise EasywayResponseError(
                "EasyWay API returned an invalid price response."
            ) from error
        if not price.is_finite() or price < Decimal("0.00"):
            raise EasywayResponseError(
                "EasyWay API returned an invalid price response."
            )
        return price.quantize(Decimal("0.01"))

    def create_order(self, payload):
        if not isinstance(payload, dict) or not payload:
            raise EasywayConfigurationError(
                "EasyWay order payload must be a non-empty object."
            )
        response = self._post("/order/insert", json=payload)
        order_id = response.get("order_id") if isinstance(response, dict) else response
        try:
            normalized_order_id = int(order_id)
        except (TypeError, ValueError) as error:
            raise EasywayResponseError(
                "EasyWay API did not return a valid order_id.",
                outcome_unknown=True,
            ) from error
        if normalized_order_id <= 0:
            raise EasywayResponseError(
                "EasyWay API did not return a valid order_id.",
                outcome_unknown=True,
            )
        return normalized_order_id

    def _get(self, path, *, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, *, json=None):
        return self._request("POST", path, json=json)

    def _request(self, method, path, *, params=None, json=None):
        url = f"{self.api_base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_user}:{self.api_key}",
        }

        try:
            request_kwargs = {
                "headers": headers,
                "params": params,
                "timeout": self.timeout,
            }
            if json is not None:
                request_kwargs["json"] = json
            response = self.http_client.request(method, url, **request_kwargs)
        except requests.RequestException as error:
            raise EasywayTransportError(
                "EasyWay API connection failed."
            ) from error

        if response.status_code >= 400:
            raise EasywayResponseError(
                f"EasyWay API rejected the request with HTTP {response.status_code}.",
                status_code=response.status_code,
                outcome_unknown=(
                    response.status_code >= 500
                    or response.status_code in {408, 429}
                ),
            )

        try:
            return response.json()
        except ValueError as error:
            raise EasywayResponseError(
                "EasyWay API returned an invalid JSON response.",
                status_code=response.status_code,
                outcome_unknown=response.status_code < 400,
            ) from error

    def _validate_configuration(self):
        missing = []
        if not self.api_user:
            missing.append("EASYWAY_API_USER")
        if not self.api_key:
            missing.append("EASYWAY_API_KEY")
        if not self.api_base_url:
            missing.append("EASYWAY_API_BASE_URL")
        if missing:
            raise EasywayConfigurationError(
                f"Missing EasyWay configuration: {', '.join(missing)}"
            )
        if not self.api_base_url.startswith("https://"):
            raise EasywayConfigurationError(
                "EASYWAY_API_BASE_URL must use HTTPS."
            )

    @staticmethod
    def _list_response(payload, key):
        if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
            raise EasywayResponseError(
                f"EasyWay API returned an invalid {key} response."
            )
        return payload[key]

    @staticmethod
    def _positive_timeout(value, label):
        try:
            timeout = float(value)
        except (TypeError, ValueError) as error:
            raise EasywayConfigurationError(
                f"EasyWay {label} must be a positive number."
            ) from error
        if timeout <= 0:
            raise EasywayConfigurationError(
                f"EasyWay {label} must be a positive number."
            )
        return timeout

    @staticmethod
    def _positive_integer(value, label):
        try:
            normalized = int(value)
        except (TypeError, ValueError) as error:
            raise EasywayConfigurationError(
                f"EasyWay {label} must be a positive integer."
            ) from error
        if normalized <= 0:
            raise EasywayConfigurationError(
                f"EasyWay {label} must be a positive integer."
            )
        return normalized

    @staticmethod
    def _positive_number(value, label):
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise EasywayConfigurationError(
                f"EasyWay {label} must be a positive number."
            ) from error
        if not normalized.is_finite() or normalized <= 0:
            raise EasywayConfigurationError(
                f"EasyWay {label} must be a positive number."
            )
        return float(normalized)
