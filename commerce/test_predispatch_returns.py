from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from . import test_bog_refunds as fixtures
from .bog_payments import BogTransportError
from .bog_refunds import request_bog_full_refund, reconcile_bog_refund_details
from .models import OrderReturn, OwnedStockLot
from .services import can_transition_order_status
from .supplier_stock import create_supplier_stock_holds_for_order


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PredispatchReturnTests(TestCase):
    def setUp(self):
        fixtures.BogRefundFlowTests.setUp(self)
        self.product.supplier_source = "cross_motors"
        self.product.supplier_stock_qty = 5
        self.product.save(update_fields=["supplier_source", "supplier_stock_qty"])
        self.hold = create_supplier_stock_holds_for_order(order=self.order)[0]
        self.url = reverse("admin:commerce_order_bog_refund", args=[self.order.pk])

    def request_refund(self, disposition):
        return request_bog_full_refund(order=self.order, client=self.client, requested_by=self.admin_user,
                                       disposition=disposition, not_dispatched=True)

    def complete(self):
        details = fixtures.BogRefundFlowTests._details(self, status="refunded", refund_amount=Decimal("100"))
        return reconcile_bog_refund_details(self.sale, details, provider_reference={"source": "payment_details"})

    def test_unpurchased_releases_hold_only_after_bank_confirmation(self):
        self.request_refund("not_purchased")
        self.hold.refresh_from_db()
        self.assertTrue(self.hold.is_active)
        self.assertFalse(OwnedStockLot.objects.exists())
        self.complete()
        self.complete()
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 5)
        self.assertEqual(self.product.owned_stock_qty, 0)
        self.assertEqual(self.order.status, "cancelled")

    def test_on_hand_receipt_and_bank_replay_never_double_stock(self):
        self.request_refund("on_hand")
        self.request_refund("on_hand")
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 1)
        self.complete()
        self.complete()
        self.product.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertEqual((self.product.owned_stock_qty, self.product.stock_qty), (1, 4))
        self.assertTrue(self.hold.is_active)
        self.assertEqual(OwnedStockLot.objects.count(), 1)
        self.client.refund_full.assert_called_once()

    def test_timeout_retry_keeps_receipt_and_same_bank_key(self):
        response = self.client.refund_full.return_value
        self.client.refund_full.side_effect = BogTransportError(code="timeout", retryable=True, outcome_unknown=True)
        with self.assertRaises(BogTransportError):
            self.request_refund("on_hand")
        first_key = self.client.refund_full.call_args.kwargs["idempotency_key"]
        self.assertFalse(can_transition_order_status(self.order, "processing"))
        self.client.refund_full.side_effect = None
        self.client.refund_full.return_value = response
        self.request_refund("on_hand")
        self.assertEqual(first_key, self.client.refund_full.call_args.kwargs["idempotency_key"])
        self.assertEqual(OwnedStockLot.objects.count(), 1)

    def test_georgian_form_requires_choice_and_confirmation_without_bank_call(self):
        page = self.admin_client.get(self.url)
        self.assertContains(page, "მომწოდებლისგან ეს შეკვეთა უკვე შეძენილია?")
        self.assertNotContains(page, 'checked')
        with patch("commerce.return_admin.request_bog_full_refund") as bank:
            page = self.admin_client.post(self.url, {})
            self.assertContains(page, "აირჩიეთ ნივთების მდგომარეობა.")
            bank.assert_not_called()
        self.assertFalse(OrderReturn.objects.exists())

    def test_admin_confirmation_calls_real_flow_with_mock_bank(self):
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            response = self.admin_client.post(self.url, {"disposition": "on_hand", "not_dispatched": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OwnedStockLot.objects.count(), 1)
        self.client.refund_full.assert_called_once()
        page = self.admin_client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertContains(page, "თანხის დაბრუნება მუშავდება")

    def test_shipped_post_and_payment_admin_cannot_bypass_choice(self):
        payment_url = reverse("admin:commerce_paymenttransaction_bog_refund", args=[self.sale.pk])
        response = self.admin_client.post(payment_url, {})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.order.status = "shipped"
        self.order.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.request_refund("on_hand")
        self.client.refund_full.assert_not_called()
        self.assertFalse(OrderReturn.objects.exists())

    def test_confirmed_disposition_cannot_be_changed_on_retry(self):
        self.request_refund("on_hand")
        with self.assertRaises(ValidationError):
            self.request_refund("not_purchased")
        self.assertEqual(OwnedStockLot.objects.count(), 1)
