import io
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from .credo_checkout import apply_credo_observation
from .credo_payments import CredoResponseError, CredoStatusResult, CredoTransportError
from .credo_reconciliation import due_credo_applications, reconcile_credo_application
from .credo_status import CredoStatus
from .models import CredoApplication, Order, PaymentTransaction
from .test_credo_checkout import CredoCheckoutFixture


class CredoReconciliationTests(CredoCheckoutFixture):
    def pending(self):
        application = self.prepare().application
        application.submission_state = "unknown"
        application.save(update_fields=["submission_state"])
        client = Mock()
        client.merchant_id = application.merchant_id
        client.get_status.return_value = CredoStatusResult(CredoStatus.PROCESSING)
        return application, client

    def reconcile(self, application, client, **overrides):
        options = dict(client=client, created_before=timezone.now()+timedelta(seconds=1),
                       attempted_before=timezone.now()+timedelta(seconds=1))
        options.update(overrides)
        return reconcile_credo_application(application.pk, **options)

    def test_prepared_unsent_application_is_not_polled(self):
        application = self.prepare().application
        client = Mock()
        self.assertEqual(self.reconcile(application, client), "skipped")
        client.get_status.assert_not_called()

    def test_background_read_can_finish_checkout_without_any_browser_or_repeat_post(self):
        application, client = self.pending()
        client.get_status.return_value = CredoStatusResult(CredoStatus.SIGNED)
        self.assertEqual(self.reconcile(application, client), "ready")
        application.refresh_from_db()
        self.assertIsNotNone(application.order_id)
        self.assertIsNone(application.bank_check_token)
        self.assertIsNotNone(application.bank_checked_at)
        client.get_status.assert_called_once_with(order_code=application.order_code)
        client.create_order.assert_not_called()
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_funding_wait_is_polled_and_clean_terminal_completion_is_not(self):
        application, client = self.pending()
        client.get_status.return_value = CredoStatusResult(CredoStatus.SIGNED)
        self.reconcile(application, client)
        client.get_status.return_value = CredoStatusResult(CredoStatus.COMPLETED)
        self.assertEqual(self.reconcile(application, client), "resolved")
        self.assertEqual(self.reconcile(application, client), "skipped")
        self.assertEqual(client.get_status.call_count, 2)
        self.assertEqual(Order.objects.count(), 1)

    def test_current_worker_lease_prevents_another_status_request(self):
        application, client = self.pending()
        token = uuid.uuid4()
        CredoApplication.objects.filter(pk=application.pk).update(
            bank_check_token=token, bank_check_lock_until=timezone.now()+timedelta(minutes=1),
        )
        self.assertEqual(self.reconcile(application, client), "skipped")
        client.get_status.assert_not_called()
        application.refresh_from_db()
        self.assertEqual(application.bank_check_token, token)

    def test_retry_interval_is_honored(self):
        application, client = self.pending()
        self.reconcile(application, client)
        self.assertEqual(self.reconcile(application, client, attempted_before=timezone.now()-timedelta(minutes=1)), "skipped")
        client.get_status.assert_called_once()

    def test_transport_error_does_not_reject_cancel_or_release_a_loan(self):
        application, client = self.pending()
        client.get_status.side_effect = CredoTransportError(code="credo_transport_error", retryable=True)
        self.assertEqual(self.reconcile(application, client), "failed")
        application.refresh_from_db()
        self.assertIsNone(application.bank_status)
        self.assertIsNone(application.bank_checked_at)
        self.assertIsNotNone(application.bank_check_attempted_at)
        self.assertEqual(application.last_issue, "credo_transport_error")
        self.assertEqual(application.reservation.status, "active")
        self.assertIsNone(application.bank_check_token)

    def test_not_found_during_ambiguous_creation_never_triggers_a_second_create(self):
        application, client = self.pending()
        client.get_status.side_effect = CredoResponseError(code="credo_application_not_found")
        self.assertEqual(self.reconcile(application, client), "failed")
        application.refresh_from_db()
        self.assertIsNone(application.bank_status)
        self.assertFalse(application.needs_review)
        self.assertEqual(application.submission_state, "unknown")
        client.create_order.assert_not_called()

    def test_merchant_mismatch_fails_closed_before_bank_request(self):
        application, client = self.pending()
        client.merchant_id = "888888888888"
        self.assertEqual(self.reconcile(application, client), "failed")
        client.get_status.assert_not_called()
        application.refresh_from_db()
        self.assertTrue(application.needs_review)
        self.assertEqual(application.last_issue, "credo_merchant_mismatch")

    def test_expired_worker_response_cannot_overwrite_a_newer_lease(self):
        application, client = self.pending()
        newer_token = uuid.uuid4()
        def newer_worker(**kwargs):
            CredoApplication.objects.filter(pk=application.pk).update(
                bank_check_token=newer_token, bank_check_lock_until=timezone.now()+timedelta(minutes=1),
            )
            return CredoStatusResult(CredoStatus.SIGNED)
        client.get_status.side_effect = newer_worker
        self.assertEqual(self.reconcile(application, client), "skipped")
        application.refresh_from_db()
        self.assertIsNone(application.bank_status)
        self.assertEqual(application.bank_check_token, newer_token)
        self.assertFalse(Order.objects.exists())

    def test_explicit_newer_read_supersedes_a_running_worker(self):
        application, client = self.pending()
        def newer_read(**kwargs):
            apply_credo_observation(application.pk, 5)
            return CredoStatusResult(CredoStatus.PROCESSING)
        client.get_status.side_effect = newer_read
        self.assertEqual(self.reconcile(application, client), "skipped")
        application.refresh_from_db()
        self.assertEqual(application.bank_status, 5)
        self.assertFalse(application.needs_review)
        self.assertEqual(Order.objects.count(), 1)

    def test_unknown_bank_status_keeps_original_incident_until_manual_review(self):
        application, client = self.pending()
        client.get_status.side_effect = CredoResponseError(code="credo_unknown_application_status")
        self.reconcile(application, client)
        client.get_status.side_effect = None
        client.get_status.return_value = CredoStatusResult(CredoStatus.SIGNED)
        self.assertEqual(self.reconcile(application, client), "review")
        application.refresh_from_db()
        self.assertEqual(application.last_issue, "credo_unknown_application_status")
        self.assertTrue(application.needs_review)
        self.assertFalse(Order.objects.exists())

    def test_dry_run_never_constructs_client_or_claims_records(self):
        application, _ = self.pending()
        CredoApplication.objects.filter(pk=application.pk).update(created_at=timezone.now()-timedelta(minutes=2))
        output = io.StringIO()
        with patch("commerce.management.commands.reconcile_credo_applications.CredoPaymentsClient") as client:
            call_command("reconcile_credo_applications", min_age_seconds=1, retry_seconds=60,
                         dry_run=True, stdout=output)
        self.assertIn("No API calls or writes", output.getvalue())
        self.assertIn("Eligible applications: 1", output.getvalue())
        client.assert_not_called()
        application.refresh_from_db()
        self.assertIsNone(application.bank_check_attempted_at)

    def test_disabled_reconciliation_never_sends_status_requests(self):
        application, _ = self.pending()
        CredoApplication.objects.filter(pk=application.pk).update(created_at=timezone.now()-timedelta(minutes=2))
        with override_settings(CREDO_STATUS_CHECK_ENABLED=False), self.assertRaises(CommandError):
            call_command("reconcile_credo_applications", min_age_seconds=1, retry_seconds=60)
        application.refresh_from_db()
        self.assertIsNone(application.bank_check_attempted_at)

    def test_status_job_is_independent_from_new_checkout_enable_flag(self):
        application, client = self.pending()
        CredoApplication.objects.filter(pk=application.pk).update(created_at=timezone.now()-timedelta(minutes=2))
        with override_settings(CREDO_STATUS_CHECK_ENABLED=True, CREDO_PAYMENTS_ENABLED=False), patch(
            "commerce.management.commands.reconcile_credo_applications.CredoPaymentsClient", return_value=client,
        ):
            output = io.StringIO()
            call_command("reconcile_credo_applications", min_age_seconds=1, retry_seconds=60, stdout=output)
        client.get_status.assert_called_once()
        self.assertIn("pending=1", output.getvalue())

    def test_failed_status_request_does_not_erase_an_existing_fulfillment_issue(self):
        application, client = self.pending()
        application.needs_review = True
        application.last_issue = "credo_stock_unavailable"
        application.save()
        client.get_status.side_effect = CredoTransportError(code="credo_transport_error")
        self.reconcile(application, client)
        application.refresh_from_db()
        self.assertEqual(application.last_issue, "credo_stock_unavailable")
