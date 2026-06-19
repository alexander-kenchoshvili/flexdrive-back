from django.core.cache import caches
from rest_framework.throttling import (
    AnonRateThrottle,
    ScopedRateThrottle,
    UserRateThrottle,
)


class ThrottlingCacheMixin:
    cache = caches["throttling"]


class CachedScopedRateThrottle(ThrottlingCacheMixin, ScopedRateThrottle):
    pass


class CachedAnonRateThrottle(ThrottlingCacheMixin, AnonRateThrottle):
    pass


class CachedUserRateThrottle(ThrottlingCacheMixin, UserRateThrottle):
    pass
