import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .credo_access import credo_access_cookie_name
from .credo_payments import CredoStatusResult, CredoTransportError
from .credo_status import CredoStatus
from .models import CredoApplication, Order, PaymentTransaction
from .services import CART_TOKEN_COOKIE_NAME
from .test_credo_checkout import CredoCheckoutFixture


@override_settings(CREDO_STATUS_CHECK_ENABLED=True, CREDO_PAYMENTS_ENABLED=False)
class CredoOwnerRefreshTests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        self.application = self.prepare(is_test=True).application
        self.application.submission_state = "submitted"
        self.application.save(update_fields=["submission_state"])
        self.bank = Mock(merchant_id=self.application.merchant_id)
        self.bank.get_status.return_value = CredoStatusResult(CredoStatus.PROCESSING)
        patch("commerce.credo_views.configured_credo_client", return_value=self.bank).start()
        self.client = APIClient()
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        self.url = reverse("commerce-credo-application-refresh", kwargs={"public_token": self.application.public_token})

    def test_owner_refresh_polls_but_repeated_clicks_and_other_tabs_share_server_cooldown(self):
        first = self.client.post(self.url)
        second = self.client.post(self.url, {"bank_status": 12}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["stage"], "processing")
        self.bank.get_status.assert_called_once_with(order_code=self.application.order_code)
        self.bank.create_order.assert_not_called()
        self.assertFalse(Order.objects.exists())
        self.assertEqual(second["Cache-Control"], "no-store")

    def test_signature_creates_one_order_and_browser_stops_polling_signed_application(self):
        self.bank.get_status.return_value = CredoStatusResult(CredoStatus.SIGNED)
        response = self.client.post(self.url)
        self.assertTrue(response.data["ready_to_ship"])
        self.assertIsNotNone(response.data["order_public_token"])
        self.assertEqual(Order.objects.get().payment_status, "pending")
        CredoApplication.objects.filter(pk=self.application.pk).update(bank_check_attempted_at=timezone.now()-timedelta(minutes=1))
        self.client.post(self.url)
        self.bank.get_status.assert_called_once()
        self.assertEqual(Order.objects.count(), 1)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_denial_releases_hold_without_creating_order(self):
        self.bank.get_status.return_value = CredoStatusResult(CredoStatus.REJECTED)
        response = self.client.post(self.url)
        self.assertEqual(response.data["stage"], "rejected")
        self.assertTrue(response.data["can_restart_checkout"])
        self.application.refresh_from_db()
        self.assertEqual(self.application.reservation.status, "released")
        self.assertFalse(Order.objects.exists())

    def test_another_guest_and_uuid_alone_cannot_poll_bank(self):
        for cookie in (None, str(uuid.uuid4())):
            self.client.cookies.clear()
            if cookie: self.client.cookies[CART_TOKEN_COOKIE_NAME] = cookie
            self.assertEqual(self.client.post(self.url).status_code, 404)
        self.bank.get_status.assert_not_called()

    def test_signed_cookie_survives_missing_source_cookie(self):
        response = HttpResponse()
        response.set_signed_cookie(credo_access_cookie_name(self.application.public_token), str(self.application.public_token), salt="credo-application")
        self.client.cookies.clear(); self.client.cookies.update(response.cookies)
        self.assertEqual(self.client.post(self.url).status_code, 200)
        self.bank.get_status.assert_called_once()

    def test_existing_cron_lease_blocks_browser_bank_read(self):
        CredoApplication.objects.filter(pk=self.application.pk).update(
            bank_check_token=uuid.uuid4(), bank_check_lock_until=timezone.now()+timedelta(minutes=1))
        self.assertEqual(self.client.post(self.url).status_code, 200)
        self.bank.get_status.assert_not_called()

    def test_new_status_read_allowed_after_thirty_second_cooldown(self):
        self.client.post(self.url)
        CredoApplication.objects.filter(pk=self.application.pk).update(bank_check_attempted_at=timezone.now()-timedelta(seconds=31))
        self.client.post(self.url)
        self.assertEqual(self.bank.get_status.call_count, 2)

    def test_transport_failure_is_not_denial_and_keeps_hold(self):
        self.bank.get_status.side_effect = CredoTransportError(code="credo_transport_error")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 503)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.bank_status)
        self.assertEqual(self.application.reservation.status, "active")
        self.assertNotIn("transport", response.content.decode())

    @override_settings(CREDO_STATUS_CHECK_ENABLED=False)
    def test_status_switch_disables_http_without_preventing_saved_state_read(self):
        self.assertEqual(self.client.post(self.url).status_code, 200)
        self.bank.get_status.assert_not_called()

    def test_prepared_unsent_or_review_application_cannot_trigger_http(self):
        for values in ({"submission_state": "prepared"}, {"submission_state": "submitted", "needs_review": True}):
            CredoApplication.objects.filter(pk=self.application.pk).update(**values)
            self.assertEqual(self.client.post(self.url).status_code, 200)
        self.bank.get_status.assert_not_called()

    def test_post_requires_csrf_and_get_never_runs_refresh(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        protected = APIClient(enforce_csrf_checks=True)
        protected.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        rejected = protected.post(self.url)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json()["code"], "csrf_failed")
        self.bank.get_status.assert_not_called()
        session = protected.get("/api/accounts/session/")
        token = session.cookies["csrftoken"].value
        self.assertEqual(protected.post(self.url, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.bank.get_status.assert_called_once()
