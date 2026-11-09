"""Wingo reference-only transport. No booking, pricing calls or retries."""

import json
import math
from urllib.parse import urlsplit

import requests
from django.conf import settings


MAX_REFERENCE_BYTES = 8 * 1024 * 1024


class WingoError(Exception):
    """Staff-safe errors; provider bodies and credentials must not be included."""


class WingoConfigurationError(WingoError):
    pass


class WingoTransportError(WingoError):
    def __init__(self):
        super().__init__("Wingo-სთან კავშირი ვერ დამყარდა. არსებული მონაცემები შენარჩუნდა.")


class WingoResponseError(WingoError):
    def __init__(self, *, status_code=None):
        self.status_code = status_code
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

    def _get(self, path, *, params=None):
        try:
            response = self.http_client.request(
                "GET", self.api_base_url + path,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                params=params, timeout=self.timeout, allow_redirects=False, stream=True,
            )
        except requests.RequestException:
            raise WingoTransportError() from None
        try:
            if not 200 <= response.status_code < 300:
                raise WingoResponseError(status_code=response.status_code)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise WingoResponseError(status_code=response.status_code)
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                raw.extend(chunk)
                if len(raw) > MAX_REFERENCE_BYTES:
                    raise WingoResponseError()
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
