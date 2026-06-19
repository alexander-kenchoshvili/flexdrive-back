import os
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from common.throttling import CachedAnonRateThrottle
from config import settings as project_settings


class DeploymentConfigurationTests(SimpleTestCase):
    def valid_settings(self):
        return {
            "app_env": "staging",
            "debug": False,
            "secret_key": "staging-secret",
            "cache_enabled": True,
            "cache_redis_url": "redis://cache.internal:6379",
            "frontend_base_url": "https://frontend.example",
            "allowed_hosts": ["backend.example"],
            "cors_allowed_origins": ["https://frontend.example"],
            "csrf_trusted_origins": ["https://frontend.example"],
            "session_cookie_secure": True,
            "csrf_cookie_secure": True,
            "api_cookie_secure": True,
            "secure_ssl_redirect": True,
        }

    def test_development_allows_local_defaults(self):
        settings = self.valid_settings()
        settings.update(
            app_env="development",
            debug=True,
            secret_key=project_settings.DEVELOPMENT_SECRET_KEY,
            cache_enabled=False,
            cache_redis_url="",
            frontend_base_url="http://localhost:3000",
            allowed_hosts=[],
            cors_allowed_origins=[],
            csrf_trusted_origins=[],
            session_cookie_secure=False,
            csrf_cookie_secure=False,
            api_cookie_secure=False,
            secure_ssl_redirect=False,
        )

        project_settings._validate_deployed_environment(**settings)

    def test_local_environment_defaults_to_development(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "", "RENDER": "", "RENDER_SERVICE_ID": ""},
            clear=False,
        ):
            os.environ.pop("APP_ENV", None)
            self.assertEqual(
                project_settings._parse_app_environment(),
                "development",
            )

    def test_render_requires_explicit_app_environment(self):
        with patch.dict(
            os.environ,
            {"RENDER": "true"},
            clear=False,
        ):
            os.environ.pop("APP_ENV", None)
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "APP_ENV must be explicitly configured on Render",
            ):
                project_settings._parse_app_environment()

    def test_staging_rejects_missing_redis(self):
        settings = self.valid_settings()
        settings.update(cache_enabled=False, cache_redis_url="")

        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "CACHE_ENABLED must be true; CACHE_REDIS_URL must be configured",
        ):
            project_settings._validate_deployed_environment(**settings)

    def test_staging_accepts_secure_configuration(self):
        project_settings._validate_deployed_environment(**self.valid_settings())


class ThrottlingCacheTests(SimpleTestCase):
    def setUp(self):
        caches["throttling"].clear()

    def tearDown(self):
        caches["throttling"].clear()

    def test_throttle_history_is_stored_in_dedicated_cache(self):
        request = APIRequestFactory().get("/", REMOTE_ADDR="203.0.113.10")
        request.user = AnonymousUser()
        throttle = CachedAnonRateThrottle()
        throttle.rate = "2/min"
        throttle.num_requests, throttle.duration = throttle.parse_rate(throttle.rate)

        self.assertTrue(throttle.allow_request(request, view=None))
        self.assertTrue(throttle.allow_request(request, view=None))
        self.assertFalse(throttle.allow_request(request, view=None))
