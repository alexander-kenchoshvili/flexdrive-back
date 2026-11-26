from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from .credo_checkout import apply_credo_observation
from .credo_payments import CredoStatusResult
from .credo_status import CredoStatus
from .credo_testing import close_cancelled_credo_test, require_local_credo_test_environment
from .models import CredoApplication, Order, PaymentTransaction, WingoShipment
from .test_credo_checkout import CredoCheckoutFixture


class LocalTestScopeTests(SimpleTestCase):
    @override_settings(DEBUG=True, APP_ENV="development", CREDO_TEST_MODE=True, BASE_DIR="C:/local/shop")
    def test_only_exact_local_database_is_accepted(self):
        with patch("commerce.credo_testing.connection") as db:
            db.vendor = "sqlite"
            db.settings_dict = {"NAME": "C:/local/shop/db.sqlite3"}
            require_local_credo_test_environment()
            for vendor, name in (("postgresql", "production"), ("sqlite", "C:/other/db.sqlite3")):
                db.vendor = vendor; db.settings_dict = {"NAME": name}
                with self.assertRaises(ValidationError): require_local_credo_test_environment()
            db.vendor = "sqlite"; db.settings_dict = {"NAME": "C:/local/shop/db.sqlite3"}
            for change in ({"DEBUG": False}, {"APP_ENV": "production"}, {"CREDO_TEST_MODE": False}):
                with override_settings(**change), self.assertRaises(ValidationError):
                    require_local_credo_test_environment()


class LocalTestClosureTests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        # The scope itself is independently tested above; fixtures use memory DB.
        patch("commerce.credo_testing.require_local_credo_test_environment").start()
        patch("commerce.management.commands.close_cancelled_credo_test.require_local_credo_test_environment").start()
        self.user.is_staff = True; self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.application = apply_credo_observation(self.prepare(is_test=True).application.pk, 12)
        self.order = self.application.order

    def cancelled(self):
        self.application = apply_credo_observation(self.application.pk, 7)

    def close(self, **overrides):
        return close_cancelled_credo_test(**{
            "application_id": self.application.pk, "actor": self.user,
            "bank_reference": "pilot-cancel-1", "confirmed_unshipped": True, **overrides,
        })

    def test_bank_cancels_first_then_dry_run_and_one_audited_stock_restoration(self):
        with self.assertRaises(ValidationError): self.close(commit=True)
        self.cancelled()
        self.assertTrue(self.application.needs_review)
        self.assertEqual(self.application.bank_status, 12)
        self.assertFalse(self.close()["closed"])
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_qty, 9)
        self.assertFalse(LogEntry.objects.exists())
        self.assertTrue(self.close(commit=True)["changed"])
        self.assertFalse(self.close(commit=True)["changed"])
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_qty, 10)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.payment_status, "cancelled")
        self.assertIsNotNone(self.order.stock_restored_at)
        self.application.refresh_from_db(); self.assertEqual(self.application.bank_status, 7)
        self.assertFalse(self.application.needs_review)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.assertFalse(PaymentTransaction.objects.exists())
        self.purchase_event.assert_not_called()
        # Repeated trusted bank7 does not reopen or restock.
        apply_credo_observation(self.application.pk, 7)
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_qty, 10)

    def test_stale_or_different_bank_evidence_cannot_restore_stock(self):
        self.cancelled()
        for values in ({"bank_checked_at": timezone.now()-timedelta(minutes=6)},
                       {"last_observed_status": 6}, {"last_issue": "credo_snapshot_integrity_failed"}):
            with self.subTest(values=values):
                original = {key: getattr(self.application, key) for key in values}
                CredoApplication.objects.filter(pk=self.application.pk).update(**values)
                with self.assertRaises(ValidationError): self.close(commit=True)
                CredoApplication.objects.filter(pk=self.application.pk).update(**original)

    def test_real_or_funded_applications_and_sent_orders_are_blocked(self):
        self.cancelled()
        for values in ({"is_test": False}, {"funding_completed_at": timezone.now()}, {"purchase_queued_at": timezone.now()}):
            original = {key: getattr(self.application, key) for key in values}
            CredoApplication.objects.filter(pk=self.application.pk).update(**values)
            with self.assertRaises(ValidationError): self.close(commit=True)
            CredoApplication.objects.filter(pk=self.application.pk).update(**original)
        for status in ("shipped", "delivered"):
            Order.objects.filter(pk=self.order.pk).update(status=status)
            with self.assertRaises(ValidationError): self.close(commit=True)

    def test_even_ambiguous_wingo_booking_blocks_stock_restoration(self):
        self.cancelled()
        WingoShipment.objects.create(order=self.order, state="unknown", account_mode="test", api_base_url="https://carrier.example")
        with self.assertRaises(ValidationError): self.close(commit=True)

    def test_permissions_and_explicit_unshipped_confirmation_are_required(self):
        self.cancelled()
        with self.assertRaises(ValidationError): self.close(commit=True, confirmed_unshipped=False)
        with self.assertRaises(ValidationError): self.close(commit=True, bank_reference="")
        with self.assertRaises(PermissionDenied): self.close(commit=True, actor=Mock(is_active=False))

    def test_failure_to_audit_rolls_back_all_stock_and_status_changes(self):
        self.cancelled()
        with patch.object(LogEntry.objects, "log_actions", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError): self.close(commit=True)
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_qty, 9)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "new")
        self.application.refresh_from_db(); self.assertTrue(self.application.needs_review)

    def test_cli_defaults_to_dry_run(self):
        self.cancelled()
        options = {"actor_id": self.user.pk, "bank_reference": "pilot-1", "confirm_unshipped": True, "stdout": StringIO()}
        call_command("close_cancelled_credo_test", str(self.application.public_token), **options)
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_qty, 9)
        call_command("close_cancelled_credo_test", str(self.application.public_token), commit=True, **options)
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_qty, 10)


@override_settings(CREDO_STATUS_CHECK_ENABLED=True)
class LocalWatcherTests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        patch("commerce.management.commands.watch_credo_local_tests.require_local_credo_test_environment").start()
        self.bank = Mock()
        self.bank.merchant_id = "999999999999"
        self.bank.get_status.return_value = CredoStatusResult(CredoStatus.SIGNED)
        patch("commerce.management.commands.watch_credo_local_tests.configured_credo_client", return_value=self.bank).start()

    def watch(self):
        call_command("watch_credo_local_tests", once=True, stdout=StringIO())

    def test_idle_watcher_makes_no_requests(self):
        self.watch(); self.bank.get_status.assert_not_called(); self.bank.create_order.assert_not_called()

    def test_only_submitted_test_application_is_polled_and_creates_pending_order(self):
        application = self.prepare(is_test=True).application
        CredoApplication.objects.filter(pk=application.pk).update(submission_state="submitted", created_at=timezone.now()-timedelta(minutes=1))
        self.watch()
        self.bank.get_status.assert_called_once_with(order_code=application.order_code)
        self.bank.create_order.assert_not_called()
        application.refresh_from_db(); self.assertEqual(application.order.payment_status, "pending")
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_non_test_applications_are_not_polled(self):
        application = self.prepare(is_test=False).application
        CredoApplication.objects.filter(pk=application.pk).update(submission_state="submitted", created_at=timezone.now()-timedelta(minutes=1))
        self.watch(); self.bank.get_status.assert_not_called()

    @override_settings(CREDO_STATUS_CHECK_ENABLED=False)
    def test_disabled_status_flag_prevents_requests(self):
        with self.assertRaises(CommandError): self.watch()
        self.bank.get_status.assert_not_called()
