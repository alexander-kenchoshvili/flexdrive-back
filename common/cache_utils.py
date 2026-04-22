import hashlib
import json
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response


CACHE_STATUS_HEADER = "X-Cache-Status"

CACHE_GROUP_PAGES_MENU = "pages:menu"
CACHE_GROUP_PAGES_FOOTER = "pages:footer"
CACHE_GROUP_PAGES_SITE_SETTINGS = "pages:site-settings"
CACHE_GROUP_PAGES_CONTENT = "pages:content"
CACHE_GROUP_PAGES_BLOG_LIST = "pages:blog-list"
CACHE_GROUP_CATALOG_CATEGORIES = "catalog:categories"


def _normalize_value(value):
    if isinstance(value, dict):
        return {key: _normalize_value(value[key]) for key in sorted(value)}

    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]

    return value


def _normalize_query_params(query_params):
    normalized = {}
    for key in sorted(query_params.keys()):
        values = query_params.getlist(key)
        normalized[key] = values if len(values) > 1 else (values[0] if values else None)
    return normalized


def _build_request_fingerprint(request, kwargs, include_body):
    payload = {
        "method": request.method,
        "path": request.path,
        "kwargs": _normalize_value(kwargs or {}),
        "query": _normalize_query_params(request.query_params),
    }

    if include_body:
        payload["body"] = _normalize_value(request.data)

    raw_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def _group_version_key(group):
    return f"cache-group-version:{group}"


def _get_group_version(group):
    if not settings.CACHE_ENABLED:
        return 1

    version_key = _group_version_key(group)
    version = cache.get(version_key)
    if version is None:
        cache.add(version_key, 1, timeout=None)
        version = cache.get(version_key) or 1
    return int(version)


def _cache_key(group, fingerprint):
    group_version = _get_group_version(group)
    return f"public-api:{group}:v{group_version}:{fingerprint}"


def set_cache_status(response, status):
    if response is not None:
        response[CACHE_STATUS_HEADER] = status
    return response


def invalidate_group(group):
    if not settings.CACHE_ENABLED:
        return

    version_key = _group_version_key(group)
    if cache.add(version_key, 2, timeout=None):
        return

    try:
        cache.incr(version_key)
    except ValueError:
        cache.set(version_key, 2, timeout=None)


def invalidate_groups(*groups):
    for group in groups:
        invalidate_group(group)


def cache_api_response(group, ttl_setting_name, include_body=False):
    def decorator(view_method):
        @wraps(view_method)
        def wrapped(view, request, *args, **kwargs):
            if not settings.CACHE_ENABLED:
                response = view_method(view, request, *args, **kwargs)
                return set_cache_status(response, "BYPASS")

            fingerprint = _build_request_fingerprint(request, kwargs, include_body)
            cache_key = _cache_key(group, fingerprint)
            cached_payload = cache.get(cache_key)

            if cached_payload is not None:
                response = Response(
                    cached_payload["data"],
                    status=cached_payload["status"],
                )
                return set_cache_status(response, "HIT")

            response = view_method(view, request, *args, **kwargs)
            if getattr(response, "status_code", None) != 200:
                return set_cache_status(response, "BYPASS")

            cache.set(
                cache_key,
                {
                    "status": response.status_code,
                    "data": response.data,
                },
                timeout=getattr(settings, ttl_setting_name),
            )
            return set_cache_status(response, "MISS")

        return wrapped

    return decorator
