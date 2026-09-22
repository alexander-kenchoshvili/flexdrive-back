from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib import admin
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from .bog_payments import BogPaymentDetails, BogTransportError
from .models import (
    Order, OrderPaymentStatus, PaymentProvider, PaymentTransaction,
    PaymentTransactionAction, PaymentTransactionStatus, StockReservation,
)
from .payment_reconciliation import due_payments, reconcile_scheduled_payment


@override_settings(BOG_RECONCILIATION_ALERT_EMAIL="")
class PaymentReconciliationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.before = self.now - timedelta(minutes=10)
        self.retry_before = self.now - timedelta(minutes=15)
        self.bank = Mock()
        # Any accidental real bank or email call fails this suite.
        self.bank_factory = patch(
            "commerce.bog_callbacks.BogPaymentsClient.from_settings", return_value=self.bank,
        ).start()
        self.mail = patch("commerce.payment_reconciliation.send_transactional_email").start()
        self.addCleanup(patch.stopall)

    def payment(self, **kwargs):
        reservation = StockReservation.objects.create(
            guest_token=uuid4(), expires_at=self.now + timedelta(minutes=15),
        )
        data = dict(
            reservation=reservation, provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE, status=PaymentTransactionStatus.PENDING,
            amount=Decimal("10.00"), provider_order_id=f"bank-{uuid4()}",
            expires_at=self.now + timedelta(minutes=5),
        )
        data.update(kwargs)
        payment = PaymentTransaction.objects.create(**data)
        PaymentTransaction.objects.filter(pk=payment.pk).update(
            created_at=self.now - timedelta(minutes=20),
        )
        payment.refresh_from_db()
        return payment

    def details(self, payment, status="created"):
        return BogPaymentDetails(
            order_id=payment.provider_order_id, industry="ecommerce", status=status,
            external_order_id=f"FD-{payment.public_token}", capture="automatic",
            request_amount=payment.amount,
            transfer_amount=payment.amount if status == "completed" else Decimal("0"),
            refund_amount=Decimal("0"), currency="GEL", payment_method="card",
            payment_option="direct_debit", transaction_id=f"tx-{payment.pk}",
            response_code="100", reject_reason="", provider_reference={},
        )

    def run_payment(self, payment, **kwargs):
        return reconcile_scheduled_payment(
            payment.pk, created_before=self.before, attempted_before=self.retry_before,
            client=self.bank, **kwargs,
        )

    def age_retry(self, payment):
        PaymentTransaction.objects.filter(pk=payment.pk).update(
            reconciliation_attempted_at=self.now - timedelta(hours=1),
        )

    def test_empty_and_dry_run_make_no_calls_or_writes(self):
        call_command("reconcile_bog_payments", stdout=StringIO())
        payment = self.payment()
        out = StringIO()
        call_command("reconcile_bog_payments", dry_run=True, stdout=out)
        self.assertIn("Eligible payments in batch: 1", out.getvalue())
        payment.refresh_from_db()
        self.assertIsNone(payment.reconciliation_attempted_at)
        self.bank_factory.assert_not_called()
        self.mail.assert_not_called()

    def test_selection_excludes_recent_final_and_other_providers_actions(self):
        due = self.payment()
        recent = self.payment()
        PaymentTransaction.objects.filter(pk=recent.pk).update(created_at=self.now)
        self.payment(status=PaymentTransactionStatus.FAILED)
        self.payment(status=PaymentTransactionStatus.CANCELLED)
        self.payment(status=PaymentTransactionStatus.REFUNDED)
        self.payment(status=PaymentTransactionStatus.REFUND_PENDING)
        self.payment(provider=PaymentProvider.MOCK)
        self.payment(action=PaymentTransactionAction.REFUND)
        order = Order.objects.create(order_number="resolved", payment_status=OrderPaymentStatus.PAID, subtotal=10, total=10)
        self.payment(order=order, status=PaymentTransactionStatus.PAID)
        self.assertEqual(list(due_payments(
            created_before=self.before, attempted_before=self.retry_before,
        ).values_list("pk", flat=True)), [due.pk])

    def test_pending_poll_preserves_status_and_reservation_and_respects_cooldown(self):
        payment = self.payment()
        self.bank.get_payment_details.return_value = self.details(payment)
        self.assertEqual(self.run_payment(payment), "pending")
        self.assertEqual(self.run_payment(payment), "skipped")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(payment.reservation.status, "active")
        self.assertEqual(payment.reconciliation_issue, "")
        self.assertIsNone(payment.reconciliation_token)
        self.bank.get_payment_details.assert_called_once_with(payment.provider_order_id)
        self.bank.create_order.assert_not_called()
        self.bank.refund_full.assert_not_called()

    def test_rejection_uses_existing_reservation_release(self):
        payment = self.payment()
        self.bank.get_payment_details.return_value = self.details(payment, "rejected")
        self.assertEqual(self.run_payment(payment), "resolved")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(payment.reservation.status, "released")
        self.assertFalse(Order.objects.exists())

    def test_overdue_pending_is_reviewed_without_marking_failed(self):
        payment = self.payment(expires_at=self.now - timedelta(minutes=1))
        self.bank.get_payment_details.return_value = self.details(payment)
        self.assertEqual(self.run_payment(payment), "review")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_issue, "pending_overdue")
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)

    def test_missing_provider_id_alert_does_not_retry_payment_creation(self):
        payment = self.payment(provider_order_id="")
        self.assertEqual(self.run_payment(payment, notify_email="ops@example.com"), "review")
        self.bank.get_payment_details.assert_not_called()
        self.bank.create_order.assert_not_called()
        self.mail.assert_called_once()
        content = self.mail.call_args.kwargs["text_content"]
        self.assertIn(f"/manager-fd/commerce/paymenttransaction/{payment.pk}/", content)
        self.assertNotIn(str(payment.public_token), content)

    def test_paid_without_order_is_flagged_without_bank_call_or_order_creation(self):
        payment = self.payment(status=PaymentTransactionStatus.PAID)
        self.assertEqual(self.run_payment(payment), "review")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_issue, "paid_without_order")
        self.assertFalse(Order.objects.exists())
        self.bank.get_payment_details.assert_not_called()

    def test_bank_paid_but_invalid_snapshot_is_not_blindly_fulfilled(self):
        payment = self.payment()
        self.bank.get_payment_details.return_value = self.details(payment, "completed")
        self.assertEqual(self.run_payment(payment), "review")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertIsNone(payment.order_id)
        self.assertEqual(payment.reconciliation_issue, "paid_without_order")
        self.bank.refund_full.assert_not_called()

    def test_unknown_provider_state_is_flagged_without_inventing_status(self):
        payment = self.payment()
        self.bank.get_payment_details.return_value = self.details(payment, "unknown")
        self.assertEqual(self.run_payment(payment), "review")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_issue, "provider_review_required")
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)

    def test_bank_failure_is_private_retryable_and_releases_lease(self):
        payment = self.payment()
        self.bank.get_payment_details.side_effect = BogTransportError("SECRET: buyer@example.com")
        self.assertEqual(self.run_payment(payment), "failed")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_issue, "bank_request_failed")
        self.assertEqual(payment.error_message, "")
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertIsNone(payment.reconciliation_token)
        self.age_retry(payment)
        self.bank.get_payment_details.side_effect = None
        self.bank.get_payment_details.return_value = self.details(payment)
        self.assertEqual(self.run_payment(payment), "pending")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_issue, "")

    def test_foreign_payment_response_is_rejected(self):
        payment, other = self.payment(), self.payment()
        self.bank.get_payment_details.return_value = self.details(other, "rejected")
        self.assertEqual(self.run_payment(payment), "failed")
        other.refresh_from_db()
        self.assertEqual(other.status, PaymentTransactionStatus.PENDING)

    def test_active_lease_skips_and_expired_lease_is_recoverable(self):
        payment = self.payment(reconciliation_token=uuid4(), reconciliation_lock_until=self.now + timedelta(minutes=5))
        self.assertEqual(self.run_payment(payment), "skipped")
        self.bank.get_payment_details.assert_not_called()
        PaymentTransaction.objects.filter(pk=payment.pk).update(reconciliation_lock_until=self.now - timedelta(seconds=1))
        self.bank.get_payment_details.return_value = self.details(payment)
        self.assertEqual(self.run_payment(payment), "pending")

    def test_overlapping_run_skips_same_payment(self):
        payment = self.payment()
        def request(_):
            self.assertEqual(self.run_payment(payment), "skipped")
            return self.details(payment)
        self.bank.get_payment_details.side_effect = request
        self.assertEqual(self.run_payment(payment), "pending")
        self.bank.get_payment_details.assert_called_once()

    def test_lost_lease_does_not_apply_or_release_new_owner(self):
        payment = self.payment()
        newer_token = uuid4()
        def request(_):
            PaymentTransaction.objects.filter(pk=payment.pk).update(reconciliation_token=newer_token)
            return self.details(payment, "rejected")
        self.bank.get_payment_details.side_effect = request
        self.assertEqual(self.run_payment(payment), "skipped")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_token, newer_token)
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)

    def test_lease_expiring_during_bank_request_does_not_apply_response(self):
        payment = self.payment()
        def request(_):
            PaymentTransaction.objects.filter(pk=payment.pk).update(
                reconciliation_lock_until=self.now - timedelta(seconds=1),
            )
            return self.details(payment, "rejected")
        self.bank.get_payment_details.side_effect = request
        self.assertEqual(self.run_payment(payment), "skipped")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(payment.reconciliation_issue, "")

    def test_concurrent_callback_resolution_is_not_overwritten(self):
        payment = self.payment()
        order = Order.objects.create(order_number="callback", payment_status=OrderPaymentStatus.PAID, subtotal=10, total=10)
        def request(_):
            PaymentTransaction.objects.filter(pk=payment.pk).update(order=order, status=PaymentTransactionStatus.PAID)
            return self.details(payment, "unknown")
        self.bank.get_payment_details.side_effect = request
        self.assertEqual(self.run_payment(payment), "skipped")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(payment.error_code, "")

    def test_stale_issue_cleared_without_bank_call_after_manual_resolution(self):
        payment = self.payment(status=PaymentTransactionStatus.REFUNDED, reconciliation_issue="paid_without_order")
        self.assertEqual(self.run_payment(payment), "resolved")
        payment.refresh_from_db()
        self.assertEqual(payment.reconciliation_issue, "")
        self.bank.get_payment_details.assert_not_called()

    def test_identical_notifications_are_limited_to_daily(self):
        payment = self.payment(status=PaymentTransactionStatus.PAID)
        self.run_payment(payment, notify_email="ops@example.com")
        self.age_retry(payment)
        self.run_payment(payment, notify_email="ops@example.com")
        self.mail.assert_called_once()
        self.age_retry(payment)
        PaymentTransaction.objects.filter(pk=payment.pk).update(reconciliation_notified_at=self.now - timedelta(days=2))
        self.run_payment(payment, notify_email="ops@example.com")
        self.assertEqual(self.mail.call_count, 2)

    def test_failed_notification_is_not_marked_sent_and_can_retry(self):
        payment = self.payment(provider_order_id="")
        self.mail.side_effect = RuntimeError("secret")
        with self.assertRaises(RuntimeError):
            self.run_payment(payment, notify_email="ops@example.com")
        payment.refresh_from_db()
        self.assertIsNone(payment.reconciliation_notified_at)
        self.assertIsNone(payment.reconciliation_token)
        self.age_retry(payment)
        self.mail.side_effect = None
        self.run_payment(payment, notify_email="ops@example.com")
        self.assertEqual(self.mail.call_count, 2)

    def test_command_continues_after_error_and_returns_failure(self):
        bad, good = self.payment(), self.payment()
        def request(order_id):
            if order_id == bad.provider_order_id:
                raise BogTransportError("SECRET")
            return self.details(good)
        self.bank.get_payment_details.side_effect = request
        out, err = StringIO(), StringIO()
        with self.assertRaises(CommandError):
            call_command("reconcile_bog_payments", stdout=out, stderr=err)
        self.assertIn("pending=1", out.getvalue())
        self.assertIn("failed=1", out.getvalue())
        self.assertNotIn("SECRET", out.getvalue() + err.getvalue())
        self.assertEqual(self.bank.get_payment_details.call_count, 2)

    def test_command_batch_limit_and_time_budget(self):
        self.payment(provider_order_id="")
        self.payment(provider_order_id="")
        with self.assertRaises(CommandError):
            call_command("reconcile_bog_payments", limit=1, stdout=StringIO(), stderr=StringIO())
        self.assertEqual(PaymentTransaction.objects.filter(reconciliation_attempted_at__isnull=False).count(), 1)
        with patch("commerce.management.commands.reconcile_bog_payments.monotonic", side_effect=[0, 601]):
            call_command("reconcile_bog_payments", stdout=StringIO())
        self.assertEqual(PaymentTransaction.objects.filter(reconciliation_attempted_at__isnull=False).count(), 1)

    def test_invalid_arguments_and_email_rejected(self):
        for option in ("limit", "min_age_minutes", "retry_minutes", "max_seconds"):
            with self.subTest(option=option), self.assertRaises(CommandError):
                call_command("reconcile_bog_payments", **{option: 0}, stdout=StringIO())
        with override_settings(BOG_RECONCILIATION_ALERT_EMAIL="invalid"), self.assertRaises(CommandError):
            call_command("reconcile_bog_payments", stdout=StringIO())
        self.bank_factory.assert_not_called()

    def test_monitoring_fields_are_admin_read_only(self):
        model_admin = admin.site._registry[PaymentTransaction]
        for name in ("reconciliation_issue", "reconciliation_token", "reconciliation_attempted_at"):
            self.assertIn(name, model_admin.readonly_fields)
