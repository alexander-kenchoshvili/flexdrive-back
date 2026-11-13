import time
from urllib.parse import quote
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.response import Response

from common.storefront_access import PREVIEW_COOKIE, PREVIEW_MAX_AGE, PREVIEW_SALT, make_preview_code
from commerce.views import BogPaymentCallbackAPIView
from commerce.wingo_webhooks import WingoWebhookAPIView
from pages.models import LaunchControl


@override_settings(
    STOREFRONT_ACCESS_GUARD_ENABLED=True,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class LaunchAccessTests(TestCase):
    def setUp(self):
        self.control, _ = LaunchControl.objects.update_or_create(pk=1, defaults={"public_open": False, "preview_version": 1})
        self.status_url = reverse("launch-status")
        self.admin_url = reverse("admin:pages_launchcontrol_changelist")
        self.owner = get_user_model().objects.create_superuser("launch-owner", "launch-owner@example.test", "test-only")

    def preview_client(self):
        client = Client(enforce_csrf_checks=True)
        client.cookies[PREVIEW_COOKIE] = make_preview_code(self.control)
        return client

    def test_status_is_public_read_only_and_never_cached(self):
        response = self.client.get(self.status_url)
        self.assertEqual(response.json(), {"guard_enabled": True, "public_open": False, "preview_allowed": False})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.status_url).status_code, 403)
        self.assertFalse(LaunchControl.objects.get(pk=1).public_open)

    def test_anonymous_direct_backend_hosts_and_unsafe_routes_are_blocked(self):
        for path in ("/api/pages/site-settings/", "/api/catalog/", "/api/accounts/session/", "/api/business/access/", "/unknown/"):
            for host in ("testserver", "localhost"):
                response = self.client.get(path, HTTP_HOST=host, HTTP_X_PREVIEW_ACCESS="true", HTTP_X_FORWARDED_HOST="localhost")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "storefront_not_open")
                self.assertIn("no-store", response["Cache-Control"])
        response = self.client.post("/api/commerce/orders/checkout/", {})
        self.assertEqual(response.json()["code"], "storefront_not_open")

    def test_valid_preview_cookie_allows_actual_cms_response(self):
        client = self.preview_client()
        self.assertTrue(client.get(self.status_url).json()["preview_allowed"])
        response = client.get("/api/pages/site-settings/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("site_name", response.json())
        self.assertIn("no-store", response["Cache-Control"])

    def test_preview_does_not_replace_api_csrf_or_account_authentication(self):
        client = self.preview_client()
        self.assertEqual(client.get("/api/accounts/me/").status_code, 401)
        response = client.post("/api/accounts/logout/", {})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "csrf_failed")

    def test_h3_percent_encoded_cookie_works_without_any_auth_header(self):
        self.client.cookies[PREVIEW_COOKIE] = quote(make_preview_code(self.control), safe="")
        self.assertTrue(self.client.get(self.status_url).json()["preview_allowed"])
        self.assertEqual(self.client.get("/api/pages/site-settings/").status_code, 200)

    def test_tampered_expired_wrong_salt_and_oversized_codes_are_rejected(self):
        code = make_preview_code(self.control)
        with patch("django.core.signing.time.time", return_value=time.time() - PREVIEW_MAX_AGE - 2):
            expired = make_preview_code(self.control)
        codes = [code + "x", expired, signing.dumps({"version": 1}, salt="another-purpose"), "x" * 513]
        for token in codes:
            self.client.cookies[PREVIEW_COOKIE] = token
            self.assertFalse(self.client.get(self.status_url).json()["preview_allowed"])
            self.assertEqual(self.client.get("/api/pages/site-settings/").status_code, 403)

    def test_revocation_invalidates_previously_valid_cookie(self):
        client = self.preview_client()
        self.control.preview_version += 1
        self.control.save()
        self.assertFalse(client.get(self.status_url).json()["preview_allowed"])
        self.assertEqual(client.get("/api/pages/site-settings/").status_code, 403)

    def test_single_database_switch_opens_and_closes_without_cache_or_env_change(self):
        for public_open in (True, False, True):
            self.control.public_open = public_open
            self.control.save()
            self.assertEqual(self.client.get(self.status_url).json()["public_open"], public_open)
            self.assertEqual(self.client.get("/api/pages/site-settings/").status_code, 200 if public_open else 403)

    def test_missing_control_and_database_failure_deny_access(self):
        with patch("common.storefront_access.LaunchControl.objects.get", side_effect=DatabaseError("private database details")):
            for url in (self.status_url, "/api/pages/site-settings/"):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b"private database details", response.content)
        self.control.delete()
        self.assertEqual(self.client.get(self.status_url).status_code, 503)
        self.assertEqual(self.client.get("/api/pages/site-settings/").status_code, 503)

    def test_only_exact_post_callbacks_bypass_gate_and_keep_their_handlers(self):
        routes = [
            ("/api/commerce/payments/bog/callback/", BogPaymentCallbackAPIView),
            ("/api/commerce/wingo/webhook/12345678-1234-1234-1234-123456789abc/test-token/", WingoWebhookAPIView),
        ]
        for url, view_class in routes:
            with patch.object(view_class, "post", return_value=Response({"reached": True})) as handler:
                response = self.client.post(url, {}, content_type="application/json")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["reached"])
                handler.assert_called_once()
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url + "forged/", {}).status_code, 403)

    def test_admin_login_remains_available_but_not_public_admin_access(self):
        self.assertEqual(self.client.get(reverse("admin:login")).status_code, 200)
        self.assertEqual(self.client.get(self.admin_url).status_code, 302)
        self.assertEqual(self.client.get("/manager-fd/accounting/").status_code, 302)

    def test_only_owner_can_view_or_change_control(self):
        staff = get_user_model().objects.create_user("launch-staff", "launch-staff@example.test", "test-only", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.admin_url).status_code, 403)
        self.assertEqual(self.client.post(self.admin_url, {"action": "open"}).status_code, 403)
        self.assertFalse(LaunchControl.objects.get(pk=1).public_open)

    def test_open_is_explicit_csrf_protected_idempotent_and_audited(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.get(self.admin_url + "?action=open")
        self.assertContains(response, "საიტის საჯაროდ გახსნა")
        self.assertFalse(LaunchControl.objects.get(pk=1).public_open)
        self.assertEqual(client.post(self.admin_url, {"action": "open"}).status_code, 403)
        csrf = client.cookies["csrftoken"].value
        for _ in range(2):
            self.assertEqual(client.post(self.admin_url, {"action": "open", "csrfmiddlewaretoken": csrf}).status_code, 302)
        self.assertTrue(self.client.get(self.status_url).json()["public_open"])
        self.assertEqual(LogEntry.objects.filter(user=self.owner, change_message="საიტი საჯაროდ გაიხსნა.").count(), 1)
        client.post(self.admin_url, {"action": "close", "csrfmiddlewaretoken": csrf})
        self.assertFalse(self.client.get(self.status_url).json()["public_open"])

    def test_admin_generates_code_without_storing_it_and_can_revoke_it(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.admin_url, {"action": "preview"})
        self.assertEqual(response.status_code, 200)
        code = response.context_data["preview_code"]
        self.assertEqual(signing.loads(code, salt=PREVIEW_SALT)["version"], self.control.preview_version)
        self.assertNotIn(code, LogEntry.objects.latest("id").change_message)
        self.assertIsNone(self.client.get(self.admin_url).context_data["preview_code"])
        self.client.cookies[PREVIEW_COOKIE] = code
        self.assertTrue(self.client.get(self.status_url).json()["preview_allowed"])
        self.client.post(self.admin_url, {"action": "revoke"})
        self.assertFalse(self.client.get(self.status_url).json()["preview_allowed"])

    @override_settings(STOREFRONT_ACCESS_GUARD_ENABLED=False)
    def test_disabled_environment_keeps_existing_site_and_refuses_launch_actions(self):
        self.assertEqual(self.client.get("/api/pages/site-settings/").status_code, 200)
        self.assertFalse(self.client.get(self.status_url).json()["guard_enabled"])
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self.admin_url), "დროებითი დაცვა ჯერ არ არის ჩართული")
        self.assertEqual(self.client.post(self.admin_url, {"action": "open"}).status_code, 400)

    def test_only_one_control_row_can_exist(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LaunchControl.objects.create(pk=2)

    def test_invalid_activation_flag_cannot_silently_turn_protection_off(self):
        from config.settings import _parse_strict_bool_env
        with patch.dict("os.environ", {"STOREFRONT_ACCESS_GUARD_ENABLED": "tru"}):
            with self.assertRaises(ImproperlyConfigured):
                _parse_strict_bool_env("STOREFRONT_ACCESS_GUARD_ENABLED")
