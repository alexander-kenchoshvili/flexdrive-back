import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .credo_checkout import apply_credo_observation
from .credo_payments import CredoCreateOrderResult, CredoTransportError, CredoValidationError
from .credo_submission import submit_credo_application
from .models import BuyNowSession, CredoApplication, Order, StockReservation
from .services import CART_TOKEN_COOKIE_NAME, BUY_NOW_TOKEN_COOKIE_NAME
from .test_credo_checkout import CredoCheckoutFixture


@override_settings(CREDO_PAYMENTS_ENABLED=True, CREDO_STATUS_CHECK_ENABLED=True,
                   CREDO_RESERVATION_TTL_SECONDS=1200, CREDO_TEST_MODE=True,
                   CREDO_REDIRECT_ORIGIN="https://ganvadeba.credo.ge")
class CredoSubmissionTests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        self.bank = Mock(merchant_id="999999999999")
        self.bank.create_order.return_value = CredoCreateOrderResult("https://ganvadeba.credo.ge/installment/test")
        patch("commerce.credo_submission.configured_credo_client", return_value=self.bank).start()
        patch("commerce.credo_views.validate_recaptcha", return_value=True).start()
        patch("commerce.credo_views.build_terms_acceptance_snapshot", return_value=self.terms).start()
        patch("commerce.serializers.resolve_delivery_location", return_value=SimpleNamespace(name="Tbilisi")).start()
        self.api = APIClient()
        self.api.cookies[CART_TOKEN_COOKIE_NAME] = str(self.cart.guest_token)
        self.url = reverse("commerce-cart-credo-start")
        self.payload = {**self.data, "requested_offer": "dayavi", "delivery_quote_token": "test-quote"}

    def post(self, **overrides):
        return self.api.post(self.url, {**self.payload, **overrides}, format="json", HTTP_IDEMPOTENCY_KEY=str(self.key))

    def test_both_offers_share_one_bank_contract_with_exact_delivery_included(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], "69.00")
        self.assertEqual(response.data["requested_offer"], "dayavi")
        self.assertEqual(response["Cache-Control"], "no-store")
        call = self.bank.create_order.call_args.kwargs
        self.assertEqual(str(call["total_amount"]), "69.00")
        self.assertEqual(str(call["delivery_amount"]), "9.00")
        self.assertNotIn("requested_offer", call)
        self.assertNotIn("personal_number", str(call))
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CredoApplication.objects.get().is_test)

    def test_repeated_submit_and_lost_response_replay_never_create_twice(self):
        first, second = self.post(), self.post()
        self.assertEqual(first.data["application_token"], second.data["application_token"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.bank.create_order.assert_called_once()
        self.assertEqual(CredoApplication.objects.count(), 1)

    def test_timeout_returns_existing_unknown_state_and_never_retries_post(self):
        self.bank.create_order.side_effect = CredoTransportError(code="credo_transport_error", outcome_unknown=True)
        first, replay = self.post(), self.post()
        self.assertEqual(first.status_code, 201)
        self.assertIsNone(first.data["redirect_url"])
        self.assertFalse(replay.data["can_restart_checkout"])
        self.assertEqual(CredoApplication.objects.get().submission_state, "unknown")
        self.assertEqual(CredoApplication.objects.get().reservation.status, "active")
        self.bank.create_order.assert_called_once()

    def test_crash_after_claim_remains_readback_only(self):
        application = self.prepare().application
        self.bank.create_order.side_effect = RuntimeError("unexpected")
        with self.assertRaises(RuntimeError):
            submit_credo_application(application.pk, client=self.bank)
        application.refresh_from_db()
        self.assertEqual(application.submission_state, "submitting")
        submit_credo_application(application.pk, client=self.bank)
        self.bank.create_order.assert_called_once()

    def test_conflicting_bank_read_during_definite_local_failure_requires_review(self):
        application = self.prepare().application
        def fail(**kwargs):
            apply_credo_observation(application.pk, 2)
            raise CredoValidationError(code="credo_invalid_currency")
        self.bank.create_order.side_effect = fail
        result = submit_credo_application(application.pk, client=self.bank)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.submission_state, "unknown")
        self.assertEqual(result.reservation.status, "active")

    def test_rehashed_malformed_basket_is_reviewed_without_a_bank_request(self):
        from .checkout_snapshots import snapshot_hash
        application = self.prepare().application
        snapshot = application.checkout_snapshot
        snapshot.pop("integrity_hash")
        snapshot["items"] = [{"quantity": 1}]
        snapshot["integrity_hash"] = snapshot_hash(snapshot)
        CredoApplication.objects.filter(pk=application.pk).update(checkout_snapshot=snapshot, snapshot_digest=snapshot["integrity_hash"])
        result = submit_credo_application(application.pk, client=self.bank)
        self.assertTrue(result.needs_review)
        self.bank.create_order.assert_not_called()

    def test_expired_unsent_hold_never_reaches_bank(self):
        application = self.prepare().application
        StockReservation.objects.filter(pk=application.reservation_id).update(expires_at=timezone.now()-timedelta(seconds=1))
        result = submit_credo_application(application.pk, client=self.bank)
        self.assertEqual(result.submission_state, "failed")
        self.bank.create_order.assert_not_called()

    def test_definite_local_preflight_failure_releases_only_unsent_hold(self):
        self.bank.create_order.side_effect = CredoValidationError(code="credo_invalid_currency")
        response = self.post()
        self.assertTrue(response.data["can_restart_checkout"])
        self.assertEqual(CredoApplication.objects.get().submission_state, "failed")
        self.assertEqual(CredoApplication.objects.get().reservation.status, "released")
        self.post()
        self.bank.create_order.assert_called_once()

    def test_changed_offer_on_existing_key_conflicts_without_bank_call(self):
        self.post()
        response = self.post(requested_offer="installment")
        self.assertEqual(response.status_code, 409)
        self.bank.create_order.assert_called_once()

    def test_new_key_after_refresh_recovers_active_application_without_a_second_post(self):
        first = self.post()
        self.key = uuid.uuid4()
        recovered = self.post()
        self.assertEqual(recovered.status_code, 409, recovered.data)
        self.assertEqual(recovered.data["application"]["application_token"], first.data["application_token"])
        self.bank.create_order.assert_called_once()

    def test_signed_continuation_cookie_expires(self):
        response = self.post()
        del self.api.cookies[CART_TOKEN_COOKIE_NAME]
        url = reverse("commerce-credo-application-status", args=[response.data["application_token"]])
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp()+31*86400):
            self.assertEqual(self.api.get(url).status_code, 404)

    def test_forged_amount_cannot_change_server_total(self):
        response = self.post(amount="0.01", is_test=False, merchant_id="123")
        self.assertEqual(response.data["amount"], "69.00")
        application = CredoApplication.objects.get()
        self.assertEqual(application.merchant_id, self.bank.merchant_id)
        self.assertTrue(application.is_test)

    @override_settings(CREDO_PAYMENTS_ENABLED=False)
    def test_disabled_start_does_not_validate_captcha_create_hold_or_call_bank(self):
        with patch("commerce.credo_views.validate_recaptcha") as captcha:
            response = self.post()
        self.assertEqual(response.status_code, 503)
        captcha.assert_not_called()
        self.bank.create_order.assert_not_called()
        self.assertFalse(CredoApplication.objects.exists())

    @override_settings(CREDO_STATUS_CHECK_ENABLED=False)
    def test_no_new_starts_when_status_checks_are_disabled(self):
        self.assertEqual(self.post().status_code, 503)
        self.assertFalse(StockReservation.objects.exists())

    def test_validation_and_captcha_failures_never_submit(self):
        for fields in ({"personal_number": "123"}, {"terms_accepted": False}, {"requested_offer": "other"}):
            self.assertEqual(self.post(**fields).status_code, 400)
        with patch("commerce.credo_views.validate_recaptcha", return_value=False):
            self.assertEqual(self.post().status_code, 403)
        self.assertFalse(CredoApplication.objects.exists())
        self.bank.create_order.assert_not_called()

    def test_uuid_without_owner_cookie_is_not_access(self):
        response = self.post()
        url = reverse("commerce-credo-application-status", args=[response.data["application_token"]])
        outsider = APIClient()
        self.assertEqual(outsider.get(url).status_code, 404)
        self.assertEqual(outsider.post(self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY=str(self.key)).status_code, 409)
        self.bank.create_order.assert_called_once()

    def test_signed_cookie_survives_source_session_and_cannot_be_forged(self):
        response = self.post()
        url = reverse("commerce-credo-application-status", args=[response.data["application_token"]])
        del self.api.cookies[CART_TOKEN_COOKIE_NAME]
        self.assertEqual(self.api.get(url).status_code, 200)
        self.assertEqual(self.post().status_code, 200)
        cookie = next(name for name in self.api.cookies if name.startswith("fd_credo_"))
        self.assertTrue(response.cookies[cookie]["httponly"])
        self.api.cookies[cookie] = response.data["application_token"]
        self.assertEqual(self.api.get(url).status_code, 404)

    def test_buy_now_consumption_replays_original_application(self):
        token = uuid.uuid4()
        BuyNowSession.objects.create(guest_token=token, product=self.product, quantity=1,
            unit_price_snapshot="60.00")
        self.api.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = str(token)
        self.url = reverse("commerce-buy-now-credo-start")
        first = self.post()
        self.assertEqual(first.status_code, 201, first.data)
        application = CredoApplication.objects.get()
        apply_credo_observation(application.pk, 12)
        self.assertFalse(BuyNowSession.objects.exists())
        replay = self.post()
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertTrue(replay.data["ready_to_ship"])
        self.assertIsNone(replay.data["redirect_url"])
        self.bank.create_order.assert_called_once()

    def test_account_erase_during_http_cannot_restore_snapshot_or_expose_link(self):
        def finish(**kwargs):
            CredoApplication.objects.update(checkout_snapshot={}, snapshot_digest="", needs_review=True, last_issue="credo_owner_account_deleted")
            return CredoCreateOrderResult("https://ganvadeba.credo.ge/installment/test")
        self.bank.create_order.side_effect = finish
        response = self.post()
        self.assertIsNone(response.data["redirect_url"])
        self.assertEqual(response.data["stage"], "review")
        self.assertEqual(CredoApplication.objects.get().checkout_snapshot, {})

    def test_http_is_outside_submission_transaction(self):
        application = self.prepare().application
        # TestCase itself is atomic; the submission's own savepoint is gone.
        depth = len(connection.savepoint_ids)
        def finish(**kwargs):
            self.assertEqual(len(connection.savepoint_ids), depth)
            return CredoCreateOrderResult("https://ganvadeba.credo.ge/installment/test")
        self.bank.create_order.side_effect = finish
        submit_credo_application(application.pk, client=self.bank)
