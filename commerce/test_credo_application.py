import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .models import (
    CheckoutAttempt, CredoApplication, Order, PaymentTransaction, StockReservation,
)


class CredoApplicationFoundationTests(TestCase):
    def make_application(self, **overrides):
        attempt = CheckoutAttempt.objects.create(
            key=uuid.uuid4(), source="cart", owner_fingerprint="a" * 64, request_fingerprint="b" * 64,
        )
        reservation = StockReservation.objects.create(
            guest_token=uuid.uuid4(), source="cart", expires_at=timezone.now() + timedelta(minutes=20),
        )
        values = {
            "checkout_attempt": attempt, "reservation": reservation,
            "merchant_id": "999999999999", "order_code": "FD" + uuid.uuid4().hex,
            "requested_offer": CredoApplication.Offer.DAYAVI, "requested_amount": Decimal("100.00"),
            "checkout_snapshot": {"version": 1}, "snapshot_digest": "a" * 64,
        }
        values.update(overrides)
        return CredoApplication.objects.create(**values)

    def test_creation_is_private_evidence_not_a_receipt_or_order(self):
        application = self.make_application()
        application.full_clean()
        self.assertIsNone(application.bank_status)
        self.assertIsNone(application.order_id)
        self.assertIsNone(application.funding_completed_at)
        self.assertEqual(application.submission_state, "prepared")
        self.assertEqual(application.requested_amount, Decimal("100.00"))
        self.assertFalse(PaymentTransaction.objects.exists())
        self.assertFalse(Order.objects.exists())
        self.assertFalse(hasattr(application, "secret_key"))

    def test_bank_order_code_cannot_be_reused(self):
        first = self.make_application()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_application(order_code=first.order_code)

    def test_attempt_and_reservation_cannot_have_two_applications(self):
        first = self.make_application()
        for field in ("checkout_attempt", "reservation"):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_application(**{field: getattr(first, field)})

    def test_database_rejects_invalid_money_currency_offer_and_effective_status(self):
        for values in (
            {"requested_amount": Decimal("0.00")}, {"requested_amount": Decimal("-1.00")},
            {"currency": "USD"}, {"requested_offer": "unknown"},
            {"submission_state": "paid"}, {"bank_status": 200},
        ):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_application(**values)

    def test_unknown_observation_can_be_retained_without_becoming_effective(self):
        application = self.make_application(bank_status=12, last_observed_status=999, needs_review=True)
        application.full_clean()
        application.refresh_from_db()
        self.assertEqual(application.bank_status, 12)
        self.assertEqual(application.last_observed_status, 999)
        self.assertTrue(application.needs_review)

    def test_source_mismatch_and_nonobject_snapshot_fail_validation(self):
        application = self.make_application()
        application.reservation.source = "buy_now"
        with self.assertRaises(ValidationError):
            application.full_clean()
        application.reservation.source = "cart"
        application.checkout_snapshot = []
        with self.assertRaises(ValidationError):
            application.full_clean()

    def test_financing_evidence_and_its_targets_are_protected_from_deletion(self):
        application = self.make_application()
        with self.assertRaises(ValidationError):
            application.delete()
        with self.assertRaises(ValidationError):
            CredoApplication.objects.filter(pk=application.pk).delete()
        for target in (application.reservation, application.checkout_attempt):
            with self.subTest(target=type(target).__name__), self.assertRaises(ProtectedError):
                target.delete()

    def test_offer_records_entry_choice_without_claiming_final_bank_product(self):
        for offer in CredoApplication.Offer.values:
            with self.subTest(offer=offer):
                application = self.make_application(requested_offer=offer)
                application.full_clean()
                self.assertEqual(application.requested_offer, offer)
                self.assertFalse(hasattr(application, "final_offer"))
