import json
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import requests
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from .facebook_auth import fetch_facebook_email_permission
from .models import FacebookAccount


FACEBOOK_SETTINGS = {
    "FRONTEND_BASE_URL": "https://front.example",
    "FACEBOOK_APP_ID": "test-app",
    "FACEBOOK_APP_SECRET": "test-secret",
    "FACEBOOK_OAUTH_REDIRECT_URI": "https://front.example/auth/facebook/callback",
    "FACEBOOK_GRAPH_API_VERSION": "v25.0",
}


@override_settings(**FACEBOOK_SETTINGS)
class FacebookEmailPermissionClientTests(SimpleTestCase):
    def _response(self, data, status=200):
        response = Mock(status_code=status, content=json.dumps(data).encode())
        response.json.return_value = data
        return response

    @patch("accounts.facebook_auth.requests.get")
    def test_only_email_status_is_returned_and_token_is_not_in_url(self, get):
        for value in ("granted", "declined", "expired"):
            with self.subTest(value=value):
                get.return_value = self._response({"data": [
                    {"permission": "public_profile", "status": "granted"},
                    {"permission": "email", "status": value, "private": "PRIVATE-MARKER"},
                ]})
                self.assertEqual(fetch_facebook_email_permission("TOKEN-MARKER"), value)
                args, kwargs = get.call_args
                self.assertEqual(args, ("https://graph.facebook.com/v25.0/me/permissions",))
                self.assertEqual(kwargs["headers"], {"Authorization": "Bearer TOKEN-MARKER"})
                self.assertNotIn("TOKEN-MARKER", str(kwargs["params"]))
                self.assertFalse(kwargs["allow_redirects"])
                self.assertEqual(kwargs["timeout"], 10)

    @patch("accounts.facebook_auth.requests.get")
    def test_missing_email_is_distinct_from_invalid_or_failed_response(self, get):
        get.return_value = self._response({"data": [{"permission": "public_profile", "status": "granted"}]})
        self.assertEqual(fetch_facebook_email_permission("token"), "not_granted")
        for payload in ({}, {"data": None}, {"data": [{}]}, {"data": [None]},
                        {"data": [{"permission": "email", "status": "other"}]},
                        {"data": [{"permission": "email", "status": []}]},
                        {"data": [{"permission": "email", "status": {}}]},
                        {"data": [{"permission": "email", "status": "granted"}] * 2}):
            with self.subTest(payload=payload):
                get.return_value = self._response(payload)
                self.assertEqual(fetch_facebook_email_permission("token"), "unavailable")
        get.return_value = self._response({"data": []}, status=302)
        self.assertEqual(fetch_facebook_email_permission("token"), "unavailable")
        get.return_value = self._response({"data": []})
        get.return_value.content = b"x" * 65537
        self.assertEqual(fetch_facebook_email_permission("token"), "unavailable")
        get.side_effect = requests.RequestException("PRIVATE-MARKER TOKEN-MARKER")
        self.assertEqual(fetch_facebook_email_permission("token"), "unavailable")
        get.reset_mock()
        self.assertEqual(fetch_facebook_email_permission(""), "unavailable")
        get.assert_not_called()


@override_settings(**FACEBOOK_SETTINGS)
class FacebookEmailRecoveryTests(APITestCase):
    def _start(self, *, retry=None):
        query = {"next": "/profile?tab=orders", "return_path": "/login"}
        if retry is not None:
            query["rerequest_email"] = retry
        response = self.client.get(reverse("facebook_auth_start"), query)
        state = response.cookies["facebook_oauth_state"].value
        self.client.cookies["facebook_oauth_state"] = state
        return response, state

    def _callback(self, state, permission, *, with_email=False):
        profile = {"id": "PRIVATE-ID-MARKER", "name": "PRIVATE-NAME-MARKER"}
        if with_email:
            profile["email"] = "verified-recovery@example.com"
        with patch("accounts.views.exchange_facebook_authorization_code", return_value="TOKEN-MARKER"), \
             patch("accounts.views.fetch_facebook_profile", return_value=profile), \
             patch("accounts.views.fetch_facebook_email_permission", return_value=permission) as read:
            response = self.client.get(reverse("facebook_auth_callback"), {"state": state, "code": "CODE-MARKER"})
        return response, read

    def test_normal_login_never_reasks_and_only_explicit_exact_opt_in_does(self):
        for retry in (None, "0", "true", "1"):
            with self.subTest(retry=retry):
                response, _ = self._start(retry=retry)
                query = parse_qs(urlparse(response["Location"]).query)
                self.assertEqual(query.get("auth_type"), ["rerequest"] if retry == "1" else None)
                self.assertEqual(query["scope"], ["email,public_profile"])

    def test_missing_email_has_precise_reasons_no_account_or_auth_cookie_and_private_logs(self):
        users_before = get_user_model().objects.count()
        accounts_before = FacebookAccount.objects.count()
        for permission, expected in (
            ("declined", "facebook_email_declined"), ("expired", "facebook_email_expired"),
            ("not_granted", "facebook_email_not_granted"), ("granted", "facebook_email_unavailable"),
            ("unavailable", "facebook_email_check_unavailable"),
        ):
            with self.subTest(permission=permission):
                _, state = self._start()
                with self.assertLogs("accounts.views", level="WARNING") as logs:
                    response, read = self._callback(state, permission)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(parse_qs(urlparse(response["Location"]).query)["facebook_error"], [expected])
                self.assertNotIn("access_token", response.cookies)
                self.assertNotIn("refresh_token", response.cookies)
                self.assertEqual(response.cookies["facebook_oauth_state"].value, "")
                read.assert_called_once_with("TOKEN-MARKER")
                self.assertIn(f"permission_status={permission}", logs.output[0])
                self.assertNotIn("MARKER", str(logs.output) + response["Location"])
        self.assertEqual(get_user_model().objects.count(), users_before)
        self.assertEqual(FacebookAccount.objects.count(), accounts_before)

    def test_failed_rerequest_does_not_offer_another_automatic_retry(self):
        _, state = self._start(retry="1")
        with self.assertLogs("accounts.views", level="WARNING"):
            response, _ = self._callback(state, "declined")
        self.assertEqual(parse_qs(urlparse(response["Location"]).query)["facebook_error"], ["facebook_email_retry_failed"])
        self.assertNotIn("facebook.com", response["Location"])

    def test_a_successful_rerequest_uses_normal_login_and_never_reads_permissions(self):
        _, state = self._start(retry="1")
        response, read = self._callback(state, "declined", with_email=True)
        self.assertEqual(response["Location"], "https://front.example/profile?tab=orders")
        self.assertIn("access_token", response.cookies)
        read.assert_not_called()
        self.assertTrue(FacebookAccount.objects.filter(user__email="verified-recovery@example.com").exists())

    @patch("accounts.views.fetch_facebook_email_permission")
    @patch("accounts.views.exchange_facebook_authorization_code")
    def test_invalid_oauth_state_never_reaches_provider(self, exchange, read):
        self.client.get(reverse("facebook_auth_callback"), {"state": "tampered", "code": "code"})
        exchange.assert_not_called()
        read.assert_not_called()
