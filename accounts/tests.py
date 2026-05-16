from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .google_auth import GoogleAuthError
from .models import GoogleAccount, UserProfile
from .email_delivery import EmailDeliveryError, send_auth_email


class ProfileAPITests(APITestCase):
    def setUp(self):
        get_user_model().objects.filter(
            email__in=["owner@example.com", "taken@example.com"],
        ).delete()
        self.user = get_user_model().objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="Password123!",
            is_active=True,
            first_name="Alex",
            last_name="Ken",
        )
        self.other_user = get_user_model().objects.create_user(
            username="taken@example.com",
            email="taken@example.com",
            password="Password123!",
            is_active=True,
        )

    def test_get_profile_creates_profile_row_when_missing(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())
        self.assertEqual(response.data["email"], "owner@example.com")
        self.assertEqual(response.data["phone"], "")
        self.assertEqual(response.data["city"], "")
        self.assertEqual(response.data["address_line"], "")

    def test_patch_profile_updates_user_and_profile_fields(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("profile"),
            {
                "first_name": "Gela",
                "last_name": "Geladze",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
            },
            format="json",
        )

        self.user.refresh_from_db()
        profile = self.user.profile

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.first_name, "Gela")
        self.assertEqual(self.user.last_name, "Geladze")
        self.assertEqual(profile.phone, "555123456")
        self.assertEqual(profile.city, "Tbilisi")
        self.assertEqual(profile.address_line, "Saburtalo 1")

    def test_patch_profile_rejects_duplicate_email(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("profile"),
            {"email": "taken@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["email"][0], "A user with this email already exists.")

    def test_delete_profile_removes_user_and_clears_auth_cookies(self):
        access_token = AccessToken.for_user(self.user)
        refresh_token = RefreshToken.for_user(self.user)

        self.client.force_authenticate(user=self.user)
        self.client.cookies["access_token"] = str(access_token)
        self.client.cookies["refresh_token"] = str(refresh_token)

        response = self.client.delete(reverse("profile"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Account deleted successfully.")
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(UserProfile.objects.filter(user_id=self.user.pk).exists())
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertEqual(response.cookies["access_token"].value, "")
        self.assertEqual(response.cookies["refresh_token"].value, "")

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthSessionAPITests(APITestCase):
    def setUp(self):
        get_user_model().objects.filter(email="session@example.com").delete()
        self.user = get_user_model().objects.create_user(
            username="session@example.com",
            email="session@example.com",
            password="Password123!",
            is_active=True,
        )

    def test_login_response_includes_session_metadata(self):
        with patch("accounts.views.validate_recaptcha", return_value=True):
            response = self.client.post(
                reverse("login"),
                {
                    "email": "session@example.com",
                    "password": "Password123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["session"]["has_access"])
        self.assertTrue(response.data["session"]["has_refresh"])
        self.assertIsNotNone(response.data["session"]["access_expires_at"])
        self.assertIsNotNone(response.data["session"]["refresh_expires_at"])

    def test_refresh_response_includes_session_metadata(self):
        refresh_token = RefreshToken.for_user(self.user)
        self.client.cookies["refresh_token"] = str(refresh_token)

        response = self.client.post(reverse("token_refresh"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["session"]["has_access"])
        self.assertTrue(response.data["session"]["has_refresh"])
        self.assertIsNotNone(response.data["session"]["access_expires_at"])
        self.assertIsNotNone(response.data["session"]["refresh_expires_at"])

    def test_session_status_reports_expiry_metadata(self):
        access_token = AccessToken.for_user(self.user)
        refresh_token = RefreshToken.for_user(self.user)

        self.client.cookies["access_token"] = str(access_token)
        self.client.cookies["refresh_token"] = str(refresh_token)

        response = self.client.get(reverse("session-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_access"])
        self.assertTrue(response.data["has_refresh"])
        self.assertIsNotNone(response.data["access_expires_at"])
        self.assertIsNotNone(response.data["refresh_expires_at"])

    def test_session_status_marks_expired_access_without_losing_refresh(self):
        expired_access = AccessToken.for_user(self.user)
        expired_access.set_exp(lifetime=timedelta(seconds=-1))
        refresh_token = RefreshToken.for_user(self.user)

        self.client.cookies["access_token"] = str(expired_access)
        self.client.cookies["refresh_token"] = str(refresh_token)

        response = self.client.get(reverse("session-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["has_access"])
        self.assertTrue(response.data["has_refresh"])
        self.assertIsNone(response.data["access_expires_at"])
        self.assertIsNotNone(response.data["refresh_expires_at"])

    def test_session_status_disables_downstream_caching(self):
        response = self.client.get(reverse("session-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")


class AuthCsrfFlowAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        get_user_model().objects.filter(email="csrf-flow@example.com").delete()
        self.user = get_user_model().objects.create_user(
            username="csrf-flow@example.com",
            email="csrf-flow@example.com",
            password="Password123!",
            is_active=True,
        )

    def test_session_status_sets_csrf_cookie(self):
        response = self.client.get(reverse("session-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("csrftoken", response.cookies)
        self.assertTrue(response.cookies["csrftoken"].value)

    def test_login_succeeds_with_csrf_cookie_seeded_from_session_status(self):
        session_response = self.client.get(reverse("session-status"))
        csrf_token = session_response.cookies["csrftoken"].value

        with patch("accounts.views.validate_recaptcha", return_value=True):
            response = self.client.post(
                reverse("login"),
                {
                    "email": self.user.email,
                    "password": "Password123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)


class GoogleAuthAPITests(APITestCase):
    def setUp(self):
        self.user_model = get_user_model()
        GoogleAccount.objects.filter(
            email__in=[
                "google-new@example.com",
                "google-existing@example.com",
                "google-inactive@example.com",
                "google-linked@example.com",
            ]
        ).delete()
        self.user_model.objects.filter(
            email__in=[
                "google-new@example.com",
                "google-existing@example.com",
                "google-inactive@example.com",
                "google-linked@example.com",
            ]
        ).delete()

    def _payload(self, *, sub="google-sub-1", email="google-new@example.com"):
        return {
            "iss": "https://accounts.google.com",
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": "Nino Google",
            "given_name": "Nino",
            "family_name": "Google",
            "picture": "https://example.com/avatar.png",
        }

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("accounts.serializers.verify_google_id_token")
    def test_google_auth_creates_active_user_and_sets_session_cookies(self, mock_verify):
        mock_verify.return_value = self._payload()

        response = self.client.post(
            reverse("google_auth"),
            {"credential": "test-google-token"},
            format="json",
        )

        user = self.user_model.objects.get(email="google-new@example.com")
        google_account = GoogleAccount.objects.get(user=user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Google login successful")
        self.assertTrue(response.data["session"]["has_access"])
        self.assertTrue(response.data["session"]["has_refresh"])
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "Nino")
        self.assertEqual(user.last_name, "Google")
        self.assertEqual(google_account.google_sub, "google-sub-1")
        self.assertEqual(google_account.full_name, "Nino Google")
        self.assertEqual(google_account.picture_url, "https://example.com/avatar.png")

        me_response = self.client.get(reverse("me"))

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], user.email)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("accounts.serializers.verify_google_id_token")
    def test_google_auth_links_existing_active_user_by_verified_email(self, mock_verify):
        user = self.user_model.objects.create_user(
            username="google-existing@example.com",
            email="google-existing@example.com",
            password="Password123!",
            is_active=True,
        )
        mock_verify.return_value = self._payload(
            sub="google-sub-existing",
            email="google-existing@example.com",
        )

        response = self.client.post(
            reverse("google_auth"),
            {"credential": "test-google-token"},
            format="json",
        )

        user.refresh_from_db()
        google_account = GoogleAccount.objects.get(google_sub="google-sub-existing")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(google_account.user, user)
        self.assertTrue(user.has_usable_password())
        self.assertIsNotNone(user.last_login)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("accounts.serializers.verify_google_id_token")
    def test_google_auth_updates_existing_google_account_metadata(self, mock_verify):
        user = self.user_model.objects.create_user(
            username="google-linked@example.com",
            email="google-linked@example.com",
            password="Password123!",
            is_active=True,
        )
        GoogleAccount.objects.create(
            user=user,
            google_sub="google-sub-linked",
            email="old-google@example.com",
            email_verified=True,
            full_name="Old Name",
            picture_url="",
        )
        mock_verify.return_value = self._payload(
            sub="google-sub-linked",
            email="google-linked@example.com",
        )

        response = self.client.post(
            reverse("google_auth"),
            {"credential": "test-google-token"},
            format="json",
        )

        google_account = GoogleAccount.objects.get(google_sub="google-sub-linked")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(google_account.user, user)
        self.assertEqual(google_account.email, "google-linked@example.com")
        self.assertEqual(google_account.full_name, "Nino Google")

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("accounts.serializers.verify_google_id_token")
    def test_google_auth_rejects_unverified_email(self, mock_verify):
        payload = self._payload()
        payload["email_verified"] = False
        mock_verify.return_value = payload

        response = self.client.post(
            reverse("google_auth"),
            {"credential": "test-google-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Google email is not verified.", str(response.data))
        self.assertFalse(
            self.user_model.objects.filter(email="google-new@example.com").exists()
        )

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("accounts.serializers.verify_google_id_token")
    def test_google_auth_rejects_invalid_credential(self, mock_verify):
        mock_verify.side_effect = GoogleAuthError(
            "Google credential could not be verified."
        )

        response = self.client.post(
            reverse("google_auth"),
            {"credential": "invalid-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Google credential could not be verified.", str(response.data))

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("accounts.serializers.verify_google_id_token")
    def test_google_auth_rejects_inactive_existing_email_account(self, mock_verify):
        self.user_model.objects.create_user(
            username="google-inactive@example.com",
            email="google-inactive@example.com",
            password="Password123!",
            is_active=False,
        )
        mock_verify.return_value = self._payload(
            sub="google-sub-inactive",
            email="google-inactive@example.com",
        )

        response = self.client.post(
            reverse("google_auth"),
            {"credential": "test-google-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Account is not activated.", str(response.data))
        self.assertFalse(
            GoogleAccount.objects.filter(google_sub="google-sub-inactive").exists()
        )

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_google_auth_returns_503_when_backend_is_not_configured(self):
        response = self.client.post(
            reverse("google_auth"),
            {"credential": "test-google-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["detail"], "Google auth is not configured.")

    @override_settings(
        FRONTEND_BASE_URL="https://front.example",
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        GOOGLE_OAUTH_REDIRECT_URI="https://front.example/api/accounts/google/callback/",
    )
    def test_google_oauth_start_redirects_to_google_and_sets_state_cookie(self):
        response = self.client.get(
            reverse("google_auth_start"),
            {"next": "/profile?tab=orders", "return_path": "/login"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_oauth_state", response.cookies)

        location = response["Location"]
        parsed = urlparse(location)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "accounts.google.com")
        self.assertEqual(query["client_id"], ["client-id.apps.googleusercontent.com"])
        self.assertEqual(
            query["redirect_uri"],
            ["https://front.example/api/accounts/google/callback/"],
        )
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["scope"], ["openid email profile"])
        self.assertEqual(query["prompt"], ["select_account"])
        self.assertEqual(
            query["state"][0],
            response.cookies["google_oauth_state"].value,
        )

    @override_settings(
        FRONTEND_BASE_URL="https://front.example",
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        GOOGLE_OAUTH_REDIRECT_URI="https://front.example/api/accounts/google/callback/",
    )
    @patch("accounts.serializers.verify_google_id_token")
    @patch("accounts.views.exchange_google_authorization_code")
    def test_google_oauth_callback_sets_auth_cookies_and_redirects(
        self,
        mock_exchange_code,
        mock_verify,
    ):
        start_response = self.client.get(
            reverse("google_auth_start"),
            {"next": "/profile", "return_path": "/login"},
        )
        state = start_response.cookies["google_oauth_state"].value
        self.client.cookies["google_oauth_state"] = state
        mock_exchange_code.return_value = "id-token"
        mock_verify.return_value = self._payload(
            sub="google-redirect-sub",
            email="google-new@example.com",
        )

        response = self.client.get(
            reverse("google_auth_callback"),
            {"state": state, "code": "auth-code"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response["Location"], "https://front.example/profile")
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertEqual(response.cookies["google_oauth_state"].value, "")
        mock_exchange_code.assert_called_once_with("auth-code")
        self.assertTrue(
            GoogleAccount.objects.filter(google_sub="google-redirect-sub").exists()
        )

    @override_settings(FRONTEND_BASE_URL="https://front.example")
    def test_google_oauth_callback_rejects_missing_state(self):
        response = self.client.get(
            reverse("google_auth_callback"),
            {"code": "auth-code"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertTrue(
            response["Location"].startswith(
                "https://front.example/login?google_error=",
            )
        )


class AuthEmailDeliveryAPITests(APITestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user_model.objects.filter(
            email__in=[
                "register@example.com",
                "resend@example.com",
                "forgot@example.com",
                "failed-register@example.com",
            ]
        ).delete()

    def test_register_succeeds_when_auth_email_is_delivered(self):
        with (
            patch("accounts.views.validate_recaptcha", return_value=True),
            patch("accounts.serializers.send_auth_email") as mock_send_auth_email,
        ):
            response = self.client.post(
                reverse("register"),
                {
                    "email": "register@example.com",
                    "password": "Password123!",
                    "confirm_password": "Password123!",
                    "terms_accepted": True,
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        user = self.user_model.objects.get(email="register@example.com")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(user.is_active)
        mock_send_auth_email.assert_called_once()

    def test_register_returns_503_and_removes_user_when_email_delivery_fails(self):
        with (
            patch("accounts.views.validate_recaptcha", return_value=True),
            patch(
                "accounts.serializers.send_auth_email",
                side_effect=EmailDeliveryError(),
            ),
        ):
            response = self.client.post(
                reverse("register"),
                {
                    "email": "failed-register@example.com",
                    "password": "Password123!",
                    "confirm_password": "Password123!",
                    "terms_accepted": True,
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(
            self.user_model.objects.filter(email="failed-register@example.com").exists()
        )

    def test_resend_activation_stays_generic_when_email_delivery_fails(self):
        user = self.user_model.objects.create_user(
            username="resend@example.com",
            email="resend@example.com",
            password="Password123!",
            is_active=False,
        )
        original_token = user.activation_token

        with (
            patch("accounts.views.validate_recaptcha", return_value=True),
            patch(
                "accounts.serializers.send_auth_email",
                side_effect=EmailDeliveryError(),
            ),
        ):
            response = self.client.post(
                reverse("activate_resend"),
                {
                    "email": "resend@example.com",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(user.activation_token, original_token)

    def test_forgot_password_stays_generic_when_email_delivery_fails(self):
        user = self.user_model.objects.create_user(
            username="forgot@example.com",
            email="forgot@example.com",
            password="Password123!",
            is_active=True,
        )

        with (
            patch("accounts.views.validate_recaptcha", return_value=True),
            patch(
                "accounts.serializers.send_auth_email",
                side_effect=EmailDeliveryError(),
            ),
        ):
            response = self.client.post(
                reverse("password_forgot"),
                {
                    "email": "forgot@example.com",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(user.reset_password_token)


class PasswordResetSecurityAPITests(APITestCase):
    def setUp(self):
        get_user_model().objects.filter(email="reset-security@example.com").delete()
        self.user = get_user_model().objects.create_user(
            username="reset-security@example.com",
            email="reset-security@example.com",
            password="Password123!",
            is_active=True,
        )

    def _issue_reset_token(self):
        self.user.reset_password_token = uuid.uuid4()
        self.user.reset_password_token_created_at = timezone.now()
        self.user.save(
            update_fields=["reset_password_token", "reset_password_token_created_at"]
        )
        return self.user.reset_password_token

    def test_reset_password_blacklists_active_refresh_tokens_and_clears_cookies(self):
        first_refresh = RefreshToken.for_user(self.user)
        second_refresh = RefreshToken.for_user(self.user)
        access_token = AccessToken.for_user(self.user)
        reset_token = self._issue_reset_token()

        self.client.cookies["access_token"] = str(access_token)
        self.client.cookies["refresh_token"] = str(first_refresh)

        with patch("accounts.views.validate_recaptcha", return_value=True):
            response = self.client.post(
                reverse("password_reset"),
                {
                    "token": str(reset_token),
                    "password": "NewPassword123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.user.check_password("NewPassword123!"))
        self.assertIsNone(self.user.reset_password_token)
        self.assertIsNone(self.user.reset_password_token_created_at)
        self.assertEqual(OutstandingToken.objects.filter(user=self.user).count(), 2)
        self.assertEqual(BlacklistedToken.objects.filter(token__user=self.user).count(), 2)
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertEqual(response.cookies["access_token"].value, "")
        self.assertEqual(response.cookies["refresh_token"].value, "")
        self.assertNotEqual(str(first_refresh), str(second_refresh))

    def test_old_refresh_token_cannot_refresh_session_after_password_reset(self):
        refresh_token = RefreshToken.for_user(self.user)
        reset_token = self._issue_reset_token()

        with patch("accounts.views.validate_recaptcha", return_value=True):
            response = self.client.post(
                reverse("password_reset"),
                {
                    "token": str(reset_token),
                    "password": "NewPassword123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.cookies["refresh_token"] = str(refresh_token)
        refresh_response = self.client.post(reverse("token_refresh"))

        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__user=self.user).exists()
        )

    def test_old_access_token_cannot_access_protected_route_after_password_reset(self):
        old_access_token = AccessToken.for_user(self.user)
        reset_token = self._issue_reset_token()

        with patch("accounts.views.validate_recaptcha", return_value=True):
            response = self.client.post(
                reverse("password_reset"),
                {
                    "token": str(reset_token),
                    "password": "NewPassword123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.cookies["access_token"] = str(old_access_token)
        protected_response = self.client.get(reverse("me"))

        self.assertEqual(protected_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_after_password_reset_receives_valid_current_tokens(self):
        reset_token = self._issue_reset_token()

        with patch("accounts.views.validate_recaptcha", return_value=True):
            reset_response = self.client.post(
                reverse("password_reset"),
                {
                    "token": str(reset_token),
                    "password": "NewPassword123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)

        with patch("accounts.views.validate_recaptcha", return_value=True):
            login_response = self.client.post(
                reverse("login"),
                {
                    "email": self.user.email,
                    "password": "NewPassword123!",
                    "recaptcha_token": "test-token",
                },
                format="json",
            )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        me_response = self.client.get(reverse("me"))

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], self.user.email)


class AuthEmailFormattingTests(SimpleTestCase):
    @override_settings(
        BREVO_API_KEY="test-key",
        BREVO_API_TIMEOUT=10,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    @patch("accounts.email_delivery.requests.post")
    def test_send_auth_email_includes_html_content_for_brevo(self, mock_post):
        mock_post.return_value.status_code = 201

        send_auth_email(
            subject="Activate your account",
            text_content="Plain text body",
            html_content='<p><a href="https://example.com/activate/token/">Activate</a></p>',
            recipients=["user@example.com"],
        )

        payload = mock_post.call_args.kwargs["json"]

        self.assertEqual(payload["textContent"], "Plain text body")
        self.assertEqual(
            payload["htmlContent"],
            '<p><a href="https://example.com/activate/token/">Activate</a></p>',
        )

    @override_settings(
        BREVO_API_KEY="",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_send_auth_email_attaches_html_alternative_for_django_backend(self):
        send_auth_email(
            subject="Activate your account",
            text_content="Plain text body",
            html_content='<p><a href="https://example.com/activate/token/">Activate</a></p>',
            recipients=["user@example.com"],
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, "Plain text body")
        self.assertEqual(
            mail.outbox[0].alternatives,
            [('<p><a href="https://example.com/activate/token/">Activate</a></p>', "text/html")],
        )
