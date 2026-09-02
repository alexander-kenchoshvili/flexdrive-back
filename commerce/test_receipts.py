from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Order,
    OrderItem,
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderReceipt,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
)
from .receipts import (
    build_receipt_access_payload,
    get_or_create_order_receipt,
    issue_receipt_access_token,
)


class OrderReceiptAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="receipt-owner",
            email="owner@example.com",
            password="test-password-123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-user",
            email="other@example.com",
            password="test-password-123",
        )

    def create_order(
        self,
        *,
        suffix="000001",
        user=None,
        method=OrderPaymentMethod.CARD,
        payment_status=OrderPaymentStatus.PAID,
        item_count=1,
    ):
        subtotal = Decimal("23.40") * item_count
        order = Order.objects.create(
            user=user,
            order_number=f"ORD-RECEIPT-{suffix}",
            payment_method=method,
            payment_status=payment_status,
            subtotal=subtotal,
            delivery_price=Decimal("8.00"),
            total=subtotal + Decimal("8.00"),
            first_name="ნინო",
            last_name="მჭედლიშვილი",
            email="nino.receipt@example.com",
            phone="+995 555 12 34 56",
            city="თბილისი",
            delivery_region_name="თბილისი",
            delivery_city_name="თბილისი",
            address_line="ვაჟა-ფშაველას გამზირი 71, ბინა 24",
        )
        for index in range(item_count):
            OrderItem.objects.create(
                order=order,
                product_name=f"სამუხრუჭე ხუნდების კომპლექტი {index + 1}",
                sku=f"FD-BRAKE-{index + 1:03d}",
                unit_price=Decimal("23.40"),
                quantity=1,
                line_total=Decimal("23.40"),
            )
        if method == OrderPaymentMethod.CARD and payment_status == OrderPaymentStatus.PAID:
            PaymentTransaction.objects.create(
                order=order,
                provider=PaymentProvider.BOG,
                payment_method=OrderPaymentMethod.CARD,
                action=PaymentTransactionAction.SALE,
                status=PaymentTransactionStatus.PAID,
                amount=order.total,
                currency="GEL",
                provider_order_id=f"provider-order-{suffix}",
                provider_transaction_id=f"provider-payment-{suffix}",
                captured_at=timezone.now(),
            )
        return order

    def receipt_url(self, order):
        return reverse(
            "commerce-order-receipt",
            kwargs={"public_token": order.public_token},
        )

    def test_guest_requires_signed_receipt_token(self):
        order = self.create_order()

        response = self.client.get(self.receipt_url(order))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "receipt_access_denied")

    def test_guest_can_download_pdf_with_matching_token(self):
        order = self.create_order()
        receipt = get_or_create_order_receipt(order)

        response = self.client.get(
            self.receipt_url(order),
            HTTP_X_RECEIPT_TOKEN=issue_receipt_access_token(receipt),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(order.order_number, response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreater(len(response.content), 10_000)

    def test_token_cannot_be_reused_for_another_order(self):
        first_order = self.create_order(suffix="000002")
        second_order = self.create_order(suffix="000003")
        token = issue_receipt_access_token(get_or_create_order_receipt(first_order))

        response = self.client.get(
            self.receipt_url(second_order),
            HTTP_X_RECEIPT_TOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "receipt_token_invalid")

    def test_authenticated_owner_can_download_without_guest_token(self):
        order = self.create_order(user=self.user)
        self.client.force_authenticate(self.user)

        response = self.client.get(self.receipt_url(order))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_another_authenticated_user_is_denied(self):
        order = self.create_order(user=self.user)
        self.client.force_authenticate(self.other_user)

        response = self.client.get(self.receipt_url(order))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_card_order_is_not_eligible(self):
        order = self.create_order(
            suffix="000004",
            payment_status=OrderPaymentStatus.PENDING,
        )

        response = self.client.get(self.receipt_url(order))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "receipt_not_eligible")
        self.assertFalse(OrderReceipt.objects.filter(order=order).exists())

    def test_paid_status_without_paid_transaction_is_rejected(self):
        order = self.create_order(
            suffix="000005",
            payment_status=OrderPaymentStatus.PENDING,
        )
        Order.objects.filter(pk=order.pk).update(payment_status=OrderPaymentStatus.PAID)
        order.refresh_from_db()

        response = self.client.get(self.receipt_url(order))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "receipt_paid_transaction_missing")

    @override_settings(ORDER_RECEIPT_ALLOW_COD_PREVIEW=False)
    def test_cash_on_delivery_is_rejected_when_preview_is_disabled(self):
        order = self.create_order(
            suffix="000006",
            method=OrderPaymentMethod.CASH_ON_DELIVERY,
            payment_status=OrderPaymentStatus.PENDING,
        )

        response = self.client.get(self.receipt_url(order))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "receipt_not_eligible")

    @override_settings(ORDER_RECEIPT_ALLOW_COD_PREVIEW=True)
    def test_cash_on_delivery_preview_is_explicitly_marked(self):
        order = self.create_order(
            suffix="000007",
            method=OrderPaymentMethod.CASH_ON_DELIVERY,
            payment_status=OrderPaymentStatus.PENDING,
        )
        receipt = get_or_create_order_receipt(order)

        response = self.client.get(
            self.receipt_url(order),
            HTTP_X_RECEIPT_TOKEN=issue_receipt_access_token(receipt),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(receipt.document_snapshot["is_preview"])
        self.assertEqual(
            receipt.document_snapshot["payment"]["status_label"],
            "სატესტო რეჟიმი · გადახდა ჩაბარებისას",
        )

    def test_receipt_snapshot_does_not_change_with_order(self):
        order = self.create_order(suffix="000008")
        receipt = get_or_create_order_receipt(order)
        original_snapshot = receipt.document_snapshot
        original_hash = receipt.content_hash

        Order.objects.filter(pk=order.pk).update(
            first_name="შეცვლილი",
            total=Decimal("999.00"),
        )
        OrderItem.objects.filter(order=order).update(product_name="შეცვლილი პროდუქტი")
        same_receipt = get_or_create_order_receipt(Order.objects.get(pk=order.pk))

        self.assertEqual(same_receipt.pk, receipt.pk)
        self.assertEqual(same_receipt.document_snapshot, original_snapshot)
        self.assertEqual(same_receipt.content_hash, original_hash)

    def test_tampered_receipt_snapshot_is_not_rendered(self):
        order = self.create_order(suffix="000014")
        receipt = get_or_create_order_receipt(order)
        tampered_snapshot = dict(receipt.document_snapshot)
        tampered_order = dict(tampered_snapshot["order"])
        tampered_order["total"] = "0.01"
        tampered_snapshot["order"] = tampered_order
        OrderReceipt.objects.filter(pk=receipt.pk).update(
            document_snapshot=tampered_snapshot
        )

        response = self.client.get(
            self.receipt_url(order),
            HTTP_X_RECEIPT_TOKEN=issue_receipt_access_token(receipt),
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "receipt_integrity_failed")

    def test_many_products_generate_a_multi_page_capable_pdf(self):
        order = self.create_order(suffix="000009", item_count=48)
        receipt = get_or_create_order_receipt(order)

        response = self.client.get(
            self.receipt_url(order),
            HTTP_X_RECEIPT_TOKEN=issue_receipt_access_token(receipt),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreater(len(response.content), 25_000)

    def test_public_order_summary_does_not_expose_receipt_credentials(self):
        order = self.create_order(suffix="000010")

        response = self.client.get(
            reverse(
                "commerce-order-summary",
                kwargs={"public_token": order.public_token},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("receipt_url", response.data)
        self.assertNotIn("receipt_access_token", response.data)

    def test_paid_card_status_returns_receipt_access(self):
        order = self.create_order(suffix="000011")
        payment = order.payment_transactions.get()

        response = self.client.get(
            reverse(
                "commerce-card-payment-status",
                kwargs={"public_token": payment.public_token},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("receipt_url", response.data)
        self.assertIn("receipt_access_token", response.data)
        self.assertTrue(OrderReceipt.objects.filter(order=order).exists())

    @patch("commerce.views.validate_recaptcha", return_value=True)
    def test_verified_order_lookup_returns_receipt_access(self, _validate_recaptcha):
        order = self.create_order(suffix="000012")

        response = self.client.post(
            reverse("commerce-order-lookup"),
            {
                "order_number": order.order_number,
                "phone": order.phone,
                "recaptcha_token": "test-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("receipt_url", response.data)
        self.assertIn("receipt_access_token", response.data)

    @override_settings(ORDER_RECEIPT_ALLOW_COD_PREVIEW=True)
    def test_checkout_response_helper_can_issue_cod_preview_access(self):
        order = self.create_order(
            suffix="000013",
            method=OrderPaymentMethod.CASH_ON_DELIVERY,
            payment_status=OrderPaymentStatus.PENDING,
        )
        request = self.client.get("/").wsgi_request

        payload = build_receipt_access_payload(order, request)

        self.assertIn("receipt_url", payload)
        self.assertIn("receipt_access_token", payload)
        self.assertTrue(order.receipt.document_snapshot["is_preview"])
