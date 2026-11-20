from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from commerce.models import Order, PaymentTransaction, StockReservation
from .operations import _payments

START = datetime(2026, 11, 20, 5, 15, tzinfo=timezone.utc)


class PaymentAttemptContextTests(TestCase):
    def attempt(self, *, minute=0, status="failed", service="fast", owner="a" * 64, product=37,
                quantity=1, price="60.00", source="cart", checkout_ref=123, confirmed=True, linked=True):
        delivery = Decimal("19" if service == "fast" else "9")
        subtotal = Decimal(price) * quantity
        snapshot = {"version": 1, "source": source, "owner_fingerprint": owner,
            "source_reference": {"cart_id" if source == "cart" else "buy_now_session_id": checkout_ref},
            "buyer": {"phone": "PRIVATE-PHONE", "personal_number": "PRIVATE-PERSONAL", "email": "PRIVATE-EMAIL"},
            "items": [{"product_id": product, "quantity": quantity, "unit_price": price,
                       "sku": "PRIVATE-SUPPLIER", "accounting": {"purchase_unit_gross": "PRIVATE-COST"}}],
            "totals": {"subtotal": str(subtotal), "delivery": str(delivery), "total": str(subtotal + delivery), "currency": "GEL"},
            "delivery": {"service_slug": service}}
        order = Order.objects.create(order_number=f"ATTEMPT-{uuid4().hex[:16]}", subtotal=subtotal,
                                     total=subtotal + delivery, payment_status="paid") if status == "paid" and linked else None
        reservation = StockReservation.objects.create(guest_token=uuid4(), expires_at=START + timedelta(days=1))
        payment = PaymentTransaction.objects.create(order=order, reservation=reservation, provider="bog", action="sale",
            status=status, amount=subtotal + delivery, provider_order_id="PRIVATE-BANK-ID", checkout_snapshot=snapshot,
            error_code="bog_108" if status == "failed" else "", error_message="PRIVATE-ERROR",
            provider_reference={"source": "callback", "token": "PRIVATE-TOKEN", "details": {
                "order_status": {"key": "rejected" if status == "failed" else "completed"},
                "reject_reason": "Authentication Declined" if status == "failed" else "",
                "payment_detail": {"code": "108" if status == "failed" else "100", "card_number": "PRIVATE-CARD"}}})
        created = START + timedelta(minutes=minute)
        PaymentTransaction.objects.filter(pk=payment.pk).update(created_at=created, updated_at=created + timedelta(seconds=60),
            captured_at=created + timedelta(seconds=60) if status == "paid" and confirmed else None)
        payment.refresh_from_db()
        return payment

    def test_three_fast_bank_rejections_link_to_later_standard_success_without_rewriting_history(self):
        failed = [self.attempt(minute=minute) for minute in (0, 3, 54)]
        success = self.attempt(minute=60, status="paid", service="standard")
        original = list(PaymentTransaction.objects.order_by("pk").values())
        report = _payments({"payments": "failed"})
        self.assertEqual(report["summary"]["failed"], 3)
        self.assertEqual(report["total"], 3)
        for row in report["items"]:
            context = row["attempt_context"]
            self.assertEqual(context["failure"]["kind"], "authentication_declined")
            self.assertEqual(context["failure"]["code"], "108")
            self.assertEqual(context["checkout"], {"subtotal": "60.00", "delivery": "19.00", "total": "79.00",
                                                   "service": "fast", "service_label": "სწრაფი მიტანა"})
            self.assertEqual([entry["id"] for entry in context["history"]], [payment.pk for payment in failed] + [success.pk])
            self.assertEqual(context["later_success"]["order_number"], success.order.order_number)
            self.assertEqual(context["later_success"]["amount"], "69.00")
            self.assertEqual(context["later_success"]["checkout"]["service"], "standard")
            self.assertFalse(context["history_limited"])
        self.assertNotIn("PRIVATE", str(report))
        self.assertNotIn("a" * 64, str(report))
        self.assertEqual(list(PaymentTransaction.objects.order_by("pk").values()), original)

    def test_same_phone_does_not_link_other_owner_source_basket_price_quantity_or_day(self):
        base = self.attempt()
        for changed in ({"owner": "b" * 64}, {"source": "buy_now"}, {"checkout_ref": 124}, {"product": 38},
                        {"price": "61.00"}, {"quantity": 2}, {"minute": 1441}):
            options = {"status": "paid", "service": "standard", "minute": 1, **changed}
            self.attempt(**options)
        context = next(row for row in _payments({"payments": "failed"})["items"] if row["id"] == base.pk)["attempt_context"]
        self.assertIsNone(context["later_success"])
        self.assertEqual([row["id"] for row in context["history"]], [base.pk])

    def test_only_confirmed_linked_sale_counts_as_later_success_and_refund_state_stays_visible(self):
        self.attempt()
        self.attempt(minute=1, status="paid", confirmed=False)
        self.attempt(minute=2, status="paid", linked=False)
        self.assertIsNone(_payments({"payments": "failed"})["items"][0]["attempt_context"]["later_success"])
        success = self.attempt(minute=3, status="paid")
        Order.objects.filter(pk=success.order_id).update(payment_status="refunded")
        later = _payments({"payments": "failed"})["items"][0]["attempt_context"]["later_success"]
        self.assertEqual(later["settlement_label"], "თანხა დაბრუნებულია")

    def test_unknown_private_error_is_never_echoed_and_expiration_is_not_card_expiry(self):
        payment = self.attempt()
        reference = deepcopy(payment.provider_reference)
        reference["details"]["reject_reason"] = "PRIVATE-ERROR"
        reference["details"]["payment_detail"]["code"] = "PRIVATE-CODE"
        PaymentTransaction.objects.filter(pk=payment.pk).update(provider_reference=reference)
        context = _payments({"payments": "failed"})["items"][0]["attempt_context"]
        self.assertEqual(context["failure"]["kind"], "bank_rejected")
        self.assertIsNone(context["failure"]["code"])
        self.assertNotIn("PRIVATE", str(context))
        reference["details"]["reject_reason"] = "expiration"
        PaymentTransaction.objects.filter(pk=payment.pk).update(provider_reference=reference)
        self.assertEqual(_payments({"payments": "failed"})["items"][0]["attempt_context"]["failure"]["kind"], "expired")

    def test_legacy_and_malformed_snapshots_remain_unknown_without_crashing_or_guessing(self):
        payment = self.attempt()
        for bad in (None, [], {"source": [], "items": []}, {"totals": {"subtotal": "NaN"}},
                    {**payment.checkout_snapshot, "delivery": {"service_slug": []}, "owner_fingerprint": []}):
            PaymentTransaction.objects.filter(pk=payment.pk).update(checkout_snapshot=bad or {})
            context = _payments({"payments": "failed"})["items"][0]["attempt_context"]
            self.assertEqual(context["history"], [])
            self.assertIsNone(context["later_success"])
            self.assertIsNone(context["match_basis"])
        PaymentTransaction.objects.filter(pk=payment.pk).update(provider_reference={}, provider_order_id="")
        self.assertEqual(_payments({"payments": "failed"})["items"][0]["attempt_context"]["failure"]["kind"], "start_unconfirmed")

    def test_context_limits_are_explicit_and_query_count_is_bounded_and_select_only(self):
        for minute in range(14):
            self.attempt(minute=minute)

        def only_select(execute, sql, params, many, context):
            self.assertEqual(sql.lstrip().split()[0].upper(), "SELECT")
            return execute(sql, params, many, context)

        with connection.execute_wrapper(only_select), CaptureQueriesContext(connection) as queries, \
                patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
            report = _payments({"payments": "failed"})
        self.assertLessEqual(len(queries), 4)
        self.assertTrue(all(row["attempt_context"]["history_limited"] for row in report["items"]))
        self.assertTrue(all(len(row["attempt_context"]["history"]) <= 12 for row in report["items"]))
        with patch("business.payment_attempts.MAX_CANDIDATES", 2):
            report = _payments({"payments": "failed"})
        self.assertTrue(all(row["attempt_context"]["history_limited"] for row in report["items"]))
