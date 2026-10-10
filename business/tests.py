from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.core.cache import caches
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .authentication import BUSINESS_COOKIE, BUSINESS_COOKIE_PATH, SESSION_KIND, session_store


class BusinessAccessTests(APITestCase):
    def setUp(self):
        caches["throttling"].clear()
        self.permission = Permission.objects.get(content_type__app_label="business", codename="view_dashboard")
        User = get_user_model()
        self.owner = User.objects.create_superuser("business-owner", "business-owner@example.test", "Owner-password-123")
        self.staff = User.objects.create_user("business-staff", "business-staff@example.test", "Staff-password-123", is_staff=True)
        self.customer = User.objects.create_user("business-customer", "business-customer@example.test", "Customer-password-123")

    def login(self, user=None, password="Owner-password-123", client=None):
        user = user or self.owner
        client = client or self.client
        with patch("business.views.validate_recaptcha", return_value=True):
            return client.post(reverse("business:login"), {
                "username": user.username, "password": password, "recaptcha_token": "fresh-captcha",
            }, format="json")

    def test_permission_anchor_has_no_database_table(self):
        from django.db import connection
        self.assertNotIn("business_dashboardaccess", connection.introspection.table_names())

    def test_anonymous_and_customer_cookies_cannot_access_dashboard(self):
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)
        self.client.cookies["access_token"] = str(AccessToken.for_user(self.customer))
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)

    def test_existing_admin_session_does_not_authorize_business_api(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)
        self.client.cookies[BUSINESS_COOKIE] = self.client.cookies["sessionid"].value
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)

    def test_owner_login_sets_only_scoped_http_only_business_cookie(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.cookies), {BUSINESS_COOKIE})
        cookie = response.cookies[BUSINESS_COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], BUSINESS_COOKIE_PATH)
        self.assertNotIn("session_key", response.data)
        self.assertEqual(self.client.get(reverse("business:access")).data["user"]["id"], self.owner.pk)

    def test_staff_requires_explicit_business_permission(self):
        self.assertEqual(self.login(self.staff, "Staff-password-123").status_code, 400)
        self.staff.user_permissions.add(self.permission)
        self.assertEqual(self.login(self.staff, "Staff-password-123").status_code, 200)

    def test_customer_even_with_permission_and_accountant_remain_denied(self):
        self.customer.user_permissions.add(self.permission)
        self.assertEqual(self.login(self.customer, "Customer-password-123").status_code, 400)
        accounting = Permission.objects.get(content_type__app_label="commerce", codename="view_accounting_report")
        self.staff.user_permissions.add(accounting)
        self.assertEqual(self.login(self.staff, "Staff-password-123").status_code, 400)

    def test_wrong_password_unknown_username_and_non_privileged_login_have_same_error(self):
        wrong = self.login(password="wrong")
        with patch("business.views.validate_recaptcha", return_value=True):
            unknown = self.client.post(reverse("business:login"), {
                "username": "does-not-exist", "password": "wrong", "recaptcha_token": "fresh-captcha",
            }, format="json")
        denied = self.login(self.staff, "Staff-password-123")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.data, unknown.data)
        self.assertEqual(wrong.data, denied.data)

    def test_captcha_failure_and_missing_token_never_create_session(self):
        before = Session.objects.count()
        with patch("business.views.validate_recaptcha", return_value=False) as check:
            response = self.client.post(reverse("business:login"), {
                "username": self.owner.username, "password": "Owner-password-123", "recaptcha_token": "bad",
            }, format="json")
        self.assertEqual(response.status_code, 403)
        check.assert_called_once_with("bad", expected_action="business_login", remote_ip="127.0.0.1")
        with patch("business.views.validate_recaptcha") as check:
            response = self.client.post(reverse("business:login"), {
                "username": self.owner.username, "password": "Owner-password-123",
            }, format="json")
            check.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Session.objects.count(), before)

    def test_business_login_logout_preserves_customer_and_admin_sessions(self):
        self.client.force_login(self.staff)
        admin_cookie = self.client.cookies["sessionid"].value
        customer_token = str(AccessToken.for_user(self.customer))
        self.client.cookies["access_token"] = customer_token
        self.client.cookies["refresh_token"] = "customer-refresh-unchanged"
        self.assertEqual(self.login().status_code, 200)
        business_key = self.client.cookies[BUSINESS_COOKIE].value
        self.assertEqual(self.client.get(reverse("me")).data["id"], self.customer.pk)
        response = self.client.post(reverse("business:logout"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.cookies["access_token"].value, customer_token)
        self.assertEqual(self.client.cookies["refresh_token"].value, "customer-refresh-unchanged")
        self.assertEqual(self.client.cookies["sessionid"].value, admin_cookie)
        self.assertTrue(Session.objects.filter(session_key=admin_cookie).exists())
        replay = APIClient()
        replay.cookies[BUSINESS_COOKIE] = business_key
        self.assertEqual(replay.get(reverse("business:access")).status_code, 401)

    def test_relogin_rotates_business_session_and_revokes_old_one(self):
        self.login()
        original = self.client.cookies[BUSINESS_COOKIE].value
        self.login()
        self.assertNotEqual(original, self.client.cookies[BUSINESS_COOKIE].value)
        self.assertFalse(Session.objects.filter(session_key=original).exists())

    def test_revoked_permission_is_enforced_on_next_request(self):
        self.staff.user_permissions.add(self.permission)
        self.login(self.staff, "Staff-password-123")
        self.staff.user_permissions.remove(self.permission)
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 403)
        self.assertEqual(self.client.get(reverse("business:session")).data, {"authenticated": False, "user": None})

    def test_password_change_inactive_and_expired_session_are_denied(self):
        self.login()
        self.owner.set_password("Changed-password-123")
        self.owner.save(update_fields=["password"])
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)
        self.login(password="Changed-password-123")
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)
        self.owner.is_active = True
        self.owner.save(update_fields=["is_active"])
        self.login(password="Changed-password-123")
        Session.objects.filter(session_key=self.client.cookies[BUSINESS_COOKIE].value).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(reverse("business:access")).status_code, 401)

    def test_ip_and_account_rate_limits_apply_before_captcha(self):
        with patch("business.views.validate_recaptcha", return_value=False) as check:
            for _ in range(5):
                response = self.client.post(reverse("business:login"), {"username": self.owner.username, "password": "wrong", "recaptcha_token": "bad"}, format="json")
                self.assertEqual(response.status_code, 403)
            response = self.client.post(reverse("business:login"), {"username": self.owner.username, "password": "wrong", "recaptcha_token": "bad"}, format="json", REMOTE_ADDR="192.0.2.2")
            self.assertEqual(response.status_code, 429)
            self.assertEqual(check.call_count, 5)

    def test_malformed_payload_does_not_crash(self):
        response = self.client.post(reverse("business:login"), ["invalid"], format="json")
        self.assertEqual(response.status_code, 400)

    def test_all_business_responses_disable_cache_including_csrf_errors(self):
        for endpoint in ("business:access", "business:session"):
            response = self.client.get(reverse(endpoint))
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        csrf_client = APIClient(enforce_csrf_checks=True)
        response = self.login(client=csrf_client)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_csrf_required_for_login_and_logout_and_seed_does_not_disclose_data(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.get(reverse("business:session"))
        self.assertEqual(response.data, {"authenticated": False, "user": None})
        token = response.cookies["csrftoken"].value
        with patch("business.views.validate_recaptcha", return_value=True):
            response = client.post(reverse("business:login"), {"username": self.owner.username, "password": "Owner-password-123", "recaptcha_token": "fresh"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post(reverse("business:logout")).status_code, 403)
        self.assertEqual(client.post(reverse("business:logout"), HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_business_cookie_cannot_be_reused_as_admin_session(self):
        self.login()
        key = self.client.cookies[BUSINESS_COOKIE].value
        self.assertEqual(session_store(key).get("kind"), SESSION_KIND)
        other = APIClient()
        other.cookies["sessionid"] = key
        response = other.get("/manager-fd/")
        self.assertEqual(response.status_code, 302)
