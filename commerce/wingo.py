"""Bounded Wingo transport. Mutations never retry or follow redirects."""

import json
import math
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings


MAX_REFERENCE_BYTES = 8 * 1024 * 1024
MAX_LABEL_BYTES = 20 * 1024 * 1024


class WingoError(Exception):
    """Staff-safe errors; provider bodies and credentials must not be included."""

    outcome_unknown = True


class WingoConfigurationError(WingoError):
    outcome_unknown = False


class WingoTransportError(WingoError):
    def __init__(self):
        super().__init__("Wingo-სთან კავშირი ვერ დამყარდა. არსებული მონაცემები შენარჩუნდა.")


class WingoResponseError(WingoError):
    def __init__(self, *, status_code=None, outcome_unknown=True):
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown
        message = "Wingo-ს მონაცემები არასრული ან არასწორია. არსებული მონაცემები შენარჩუნდა."
        if status_code in (401, 403):
            message = "Wingo-ს API გასაღები ან წვდომა შესამოწმებელია. არსებული მონაცემები შენარჩუნდა."
        elif status_code is not None:
            message = f"Wingo-ს პასუხი ვერ დამუშავდა (HTTP {status_code}). არსებული მონაცემები შენარჩუნდა."
        super().__init__(message)


class WingoClient:
    def __init__(self, *, api_key, api_base_url, account_mode="test",
                 connect_timeout=5, read_timeout=20, http_client=None):
        self.api_key = str(api_key or "").strip()
        self.api_base_url = str(api_base_url or "").strip().rstrip("/")
        self.account_mode = account_mode
        try:
            parsed = urlsplit(self.api_base_url)
            valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username
                     and not parsed.password and not parsed.query and not parsed.fragment)
            parsed.port  # Validate malformed ports before making a request.
        except ValueError:
            valid = False
        if (not valid or not self.api_key or len(self.api_base_url) > 500
                or any(ord(char) <= 32 or ord(char) == 127 for char in self.api_key + self.api_base_url)
                or account_mode not in ("test", "production")):
            raise WingoConfigurationError("Wingo-ს API გასაღები, მისამართი ან ანგარიშის რეჟიმი შესავსებია.")
        try:
            self.timeout = (float(connect_timeout), float(read_timeout))
        except (TypeError, ValueError):
            raise WingoConfigurationError("Wingo-ს ლოდინის დრო არასწორია.") from None
        if any(not math.isfinite(value) or value <= 0 for value in self.timeout):
            raise WingoConfigurationError("Wingo-ს ლოდინის დრო არასწორია.")
        self.http_client = http_client or requests

    @classmethod
    def from_settings(cls):
        return cls(
            api_key=settings.WINGO_API_KEY,
            api_base_url=settings.WINGO_API_BASE_URL,
            account_mode=settings.WINGO_ACCOUNT_MODE,
            connect_timeout=settings.WINGO_HTTP_CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.WINGO_HTTP_READ_TIMEOUT_SECONDS,
        )

    def get_regions(self):
        return self._get("/regions", params={"includeLocalities": 1})

    def get_localities(self, region_name):
        if not isinstance(region_name, str) or not region_name.strip() or len(region_name) > 200:
            raise WingoConfigurationError("Wingo-ს რეგიონის დასახელება არასწორია.")
        return self._get("/localities", params={"regionGe": region_name})

    def get_weight_ranges(self):
        return self._get("/car-types/weight-ranges")

    def get_delivery_types(self):
        return self._get("/delivery-types")

    def get_merchant_tariffs(self):
        return self._get("/merchant-tariffs")

    @staticmethod
    def _reference(value):
        if (not isinstance(value, str) or not value or len(value) > 200
                or any(not (char.isascii() and (char.isalnum() or char in "-_")) for char in value)):
            raise WingoConfigurationError("Wingo-ს გზავნილის ნომერი არასწორია.")
        return quote(value, safe="")

    def create_order(self, payload):
        return self._request("POST", "/orders", payload=payload)

    def get_order(self, order_id):
        return self._get("/orders/" + self._reference(order_id))

    def get_orders(self, *, page=1, limit=100):
        if type(page) is not int or not 1 <= page <= 100 or type(limit) is not int or not 1 <= limit <= 100:
            raise WingoConfigurationError("Wingo-ს ძიების გვერდი არასწორია.")
        return self._get("/orders", params={"page": page, "limit": limit})

    def get_label(self, order_id, *, size="a4"):
        if size not in {"a4", "small"}:
            raise WingoConfigurationError("სტიკერის ფორმატი არასწორია.")
        return self._request("GET", "/orders/" + self._reference(order_id) + "/label",
                             params={"format": size, "lang": "ka"}, pdf=True)

    def _get(self, path, *, params=None):
        return self._request("GET", path, params=params)

    def _request(self, method, path, *, params=None, payload=None, pdf=False):
        headers = {"X-API-Key": self.api_key, "Accept": "application/pdf" if pdf else "application/json"}
        arguments = {"headers": headers, "params": params, "timeout": self.timeout,
                     "allow_redirects": False, "stream": True}
        if payload is not None:
            arguments["json"] = payload
        try:
            response = self.http_client.request(
                method, self.api_base_url + path, **arguments,
            )
        except requests.RequestException:
            raise WingoTransportError() from None
        try:
            if not 200 <= response.status_code < 300:
                # Only documented validation/auth refusals prove no creation.
                raise WingoResponseError(status_code=response.status_code,
                    outcome_unknown=response.status_code not in {400, 401, 403, 422})
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != ("application/pdf" if pdf else "application/json"):
                raise WingoResponseError(status_code=response.status_code)
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                raw.extend(chunk)
                if len(raw) > (MAX_LABEL_BYTES if pdf else MAX_REFERENCE_BYTES):
                    raise WingoResponseError()
            if pdf:
                if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
                    raise WingoResponseError()
                return bytes(raw)
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeError):
                raise WingoResponseError() from None
            if not isinstance(body, (dict, list)):
                raise WingoResponseError()
            return body
        except requests.RequestException:
            raise WingoTransportError() from None
        finally:
            response.close()
