from unittest.mock import patch
from io import StringIO

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from dotenv import dotenv_values
from rest_framework.test import APIRequestFactory

from .credo import load_credo_environment
from commerce.credo_views import CredoAvailabilityAPIView, CredoApplicationStartAPIView


class CredoEnvironmentTests(SimpleTestCase):
    def configured(self):
        return {
            "CREDO_MERCHANT_ID": "999999999999", "CREDO_SECRET_KEY": "  fake$sign#value  ",
            "CREDO_ORDER_URL": "https://bank.example/widget_api/order.php",
            "CREDO_STATUS_URL": "https://bank.example/widget/api.php",
            "CREDO_REDIRECT_ORIGIN": "https://bank.example",
        }

    def test_absent_and_credentials_only_configurations_never_enable_requests(self):
        for env in ({}, self.configured()):
            values = load_credo_environment(env)
            self.assertFalse(values["CREDO_PAYMENTS_ENABLED"])
            self.assertFalse(values["CREDO_STATUS_CHECK_ENABLED"])
            self.assertTrue(values["CREDO_TEST_MODE"])
            self.assertIsNone(values["CREDO_RESERVATION_TTL_SECONDS"])
            with override_settings(**values), patch("requests.request") as http:
                response = CredoAvailabilityAPIView.as_view()(APIRequestFactory().get("/"))
            self.assertFalse(response.data["enabled"])
            http.assert_not_called()

    def test_disabled_post_never_enters_checkout_or_creates_bank_client(self):
        with override_settings(**load_credo_environment(self.configured())), patch(
            "commerce.credo_submission.configured_credo_client",
        ) as client:
            response = CredoApplicationStartAPIView.as_view()(APIRequestFactory().post("/", {}))
        self.assertEqual(response.status_code, 503)
        client.assert_not_called()

    def test_signing_key_retains_significant_spaces_dollar_and_hash(self):
        env = self.configured()
        self.assertEqual(load_credo_environment(env)["CREDO_SECRET_KEY"], env["CREDO_SECRET_KEY"])
        parsed = dotenv_values(stream=StringIO("CREDO_SECRET_KEY='  fake$sign#value  '\n"), interpolate=False)
        self.assertEqual(load_credo_environment(parsed)["CREDO_SECRET_KEY"], "  fake$sign#value  ")

    def test_enabled_status_checks_can_continue_with_new_starts_disabled(self):
        values = load_credo_environment({**self.configured(), "CREDO_STATUS_CHECK_ENABLED": "true"})
        self.assertTrue(values["CREDO_STATUS_CHECK_ENABLED"])
        self.assertFalse(values["CREDO_PAYMENTS_ENABLED"])
        self.assertIsNone(values["CREDO_RESERVATION_TTL_SECONDS"])

    def test_start_requires_explicit_status_checks_and_stock_policy(self):
        env = {**self.configured(), "CREDO_PAYMENTS_ENABLED": "true"}
        with self.assertRaises(ImproperlyConfigured): load_credo_environment(env)
        env["CREDO_STATUS_CHECK_ENABLED"] = "true"
        with self.assertRaises(ImproperlyConfigured): load_credo_environment(env)
        env["CREDO_RESERVATION_TTL_SECONDS"] = "1200"
        self.assertEqual(load_credo_environment(env)["CREDO_RESERVATION_TTL_SECONDS"], 1200)

    def test_invalid_booleans_ttls_and_timeouts_fail_without_printing_values(self):
        for name, value in (
            ("CREDO_PAYMENTS_ENABLED", "secret-invalid"), ("CREDO_STATUS_CHECK_ENABLED", "maybe"),
            ("CREDO_TEST_MODE", "maybe"), ("CREDO_RESERVATION_TTL_SECONDS", "-1"),
            ("CREDO_RESERVATION_TTL_SECONDS", "604801"), ("CREDO_RESERVATION_TTL_SECONDS", "1.2"),
            ("CREDO_HTTP_READ_TIMEOUT_SECONDS", "nan"), ("CREDO_HTTP_READ_TIMEOUT_SECONDS", "inf"),
            ("CREDO_HTTP_CONNECT_TIMEOUT_SECONDS", "0"), ("CREDO_HTTP_CONNECT_TIMEOUT_SECONDS", "301"),
        ):
            with self.subTest(name=name, value=value), self.assertRaises(ImproperlyConfigured) as error:
                load_credo_environment({**self.configured(), name: value})
            self.assertNotIn("secret-invalid", str(error.exception))
            self.assertIn(name, str(error.exception))

    def test_unsafe_urls_and_invalid_credentials_never_appear_in_errors(self):
        for name, value in (
            ("CREDO_ORDER_URL", "http://bank.example/private"),
            ("CREDO_STATUS_URL", "https://user:private-secret@bank.example/status"),
            ("CREDO_STATUS_URL", "https://bank.example/status?hash=private-secret"),
            ("CREDO_REDIRECT_ORIGIN", "https://bank.example/installment/"),
            ("CREDO_MERCHANT_ID", "not-an-id"), ("CREDO_MERCHANT_ID", "0"),
            ("CREDO_SECRET_KEY", "private-secret\n"),
        ):
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured) as error:
                load_credo_environment({**self.configured(), name: value})
            self.assertNotIn("private-secret", str(error.exception))

    def test_enabled_client_requires_all_explicit_connection_fields(self):
        for name in ("CREDO_MERCHANT_ID", "CREDO_SECRET_KEY", "CREDO_ORDER_URL", "CREDO_STATUS_URL", "CREDO_REDIRECT_ORIGIN"):
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured):
                load_credo_environment({**self.configured(), "CREDO_STATUS_CHECK_ENABLED": "true", name: ""})
