import hashlib
from collections.abc import Mapping

from django.core.cache import caches
from rest_framework.throttling import SimpleRateThrottle


class BusinessLoginIpThrottle(SimpleRateThrottle):
    scope = "business_login"
    cache = caches["throttling"]

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class BusinessLoginAccountThrottle(SimpleRateThrottle):
    scope = "business_login_account"
    cache = caches["throttling"]

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, Mapping) else {}
        username = str(data.get("username", "")).strip().casefold()[:150]
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
