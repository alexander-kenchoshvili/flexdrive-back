from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from . import test_bog_refunds as fixtures
from .bog_refunds import request_bog_full_refund, reconcile_bog_refund_details
from .models import OrderReturn, OwnedStockLot


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CustomerReturnTests(TestCase):
    def setUp(self):
        fixtures.BogRefundFlowTests.setUp(self)
        self.order.status = "delivered"
        self.order.save(update_fields=["status"])
        self.start_url = reverse("admin:commerce_order_return_start", args=[self.order.pk])
        self.receive_url = reverse("admin:commerce_order_return_receive", args=[self.order.pk])
        self.refund_url = reverse("admin:commerce_order_bog_refund", args=[self.order.pk])
        self.order_url = reverse("admin:commerce_order_change", args=[self.order.pk])

    def start(self):
        self.assertEqual(self.admin_client.post(self.start_url, {"confirm": "on"}).status_code, 302)
        return OrderReturn.objects.get(order=self.order)

    def test_start_is_physical_only_and_unreceived_refund_cannot_bypass(self):
        page = self.admin_client.get(self.order_url)
        self.assertContains(page, self.start_url)
        self.assertNotContains(page, self.refund_url)
        self.admin_client.get(self.start_url)
        self.assertFalse(OrderReturn.objects.exists())
        case = self.start()
        self.start()
        self.assertEqual(case.receipt_status, "awaiting")
        self.assertEqual(OrderReturn.objects.count(), 1)
        self.assertFalse(OwnedStockLot.objects.exists())
        for kwargs in ({"disposition": "from_customer"}, {"disposition": "on_hand", "not_dispatched": True}, {}):
            with self.assertRaises(ValidationError):
                request_bog_full_refund(order=self.order, client=self.client, requested_by=self.admin_user, **kwargs)
        self.client.refund_full.assert_not_called()
        page = self.admin_client.get(self.order_url)
        self.assertContains(page, self.receive_url)
        self.assertNotContains(page, self.refund_url)

    def test_receive_then_separate_refund_and_bank_replay(self):
        case = self.start()
        line = case.lines.get()
        payload = {"confirm": "on", f"saleable_{line.pk}": 1, f"unsaleable_{line.pk}": 0}
        self.assertContains(self.admin_client.get(self.receive_url), "გასაყიდად უვარგისი")
        for _ in range(2):
            self.assertEqual(self.admin_client.post(self.receive_url, payload).status_code, 302)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(self.product.owned_stock_qty, 1)
        self.client.refund_full.assert_not_called()
        page = self.admin_client.get(self.order_url)
        self.assertContains(page, self.refund_url)
        self.assertNotContains(page, self.receive_url)
        self.assertNotContains(self.admin_client.get(self.refund_url), "მომწოდებლისგან ეს შეკვეთა უკვე შეძენილია?")
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            self.assertEqual(self.admin_client.post(self.refund_url, {"confirm": "on"}).status_code, 302)
        details = fixtures.BogRefundFlowTests._details(self, status="refunded", refund_amount=Decimal("100"))
        for _ in range(2):
            reconcile_bog_refund_details(self.sale, details, provider_reference={"source": "payment_details"})
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.product.owned_stock_qty, self.product.stock_qty), (1, 4))
        self.assertEqual((self.order.payment_status, self.order.status), ("refunded", "cancelled"))
        self.assertEqual(OwnedStockLot.objects.count(), 1)

    def test_incomplete_receipt_rejected_unsaleable_never_becomes_stock(self):
        case = self.start()
        line = case.lines.get()
        payload = {"confirm": "on", f"saleable_{line.pk}": 0, f"unsaleable_{line.pk}": 0}
        self.assertContains(self.admin_client.post(self.receive_url, payload), "სრული დაბრუნებისთვის საჭიროა ყველა ნივთის მიღება.")
        case.refresh_from_db()
        self.assertEqual(case.receipt_status, "awaiting")
        payload[f"unsaleable_{line.pk}"] = 1
        self.assertEqual(self.admin_client.post(self.receive_url, payload).status_code, 302)
        self.assertFalse(OwnedStockLot.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 0)
        self.assertContains(self.admin_client.get(self.order_url), self.refund_url)

    def test_staff_without_order_change_cannot_start_or_receive(self):
        self.admin_user.is_superuser = False
        self.admin_user.save(update_fields=["is_superuser"])
        for url in [self.start_url, self.receive_url, self.refund_url]:
            self.assertEqual(self.admin_client.post(url, {"confirm": "on"}).status_code, 403)
        self.assertFalse(OrderReturn.objects.exists())
