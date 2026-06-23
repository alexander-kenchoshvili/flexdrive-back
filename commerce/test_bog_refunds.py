import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from catalog.models import Category, Product, ProductStatus

from .bog_payments import (
    BogPaymentAction,
    BogPaymentDetails,
    BogRefundResult,
    BogResponseError,
    BogTransportError,
)
from .bog_refunds import (
    reconcile_bog_refund_details,
    request_bog_full_refund,
)
from .models import (
    Order,
    OrderItem,
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderStatus,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationStatus,
)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage"
        },
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage.StaticFilesStorage"
            )
        },
    }
)
class BogRefundFlowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Refund brakes",
            slug="refund-brakes",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Refund brake pad",
            slug="refund-brake-pad",
            sku="RBP-100",
            short_description="Brake pad",
            description="Brake pad",
            price=Decimal("100.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        self.order = Order.objects.create(
            order_number="ORD-REFUND-000001",
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PAID,
            status=OrderStatus.NEW,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            first_name="Nino",
            last_name="Beridze",
            email="nino@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Saburtalo 1",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=Decimal("100.00"),
            quantity=1,
            line_total=Decimal("100.00"),
        )
        self.sale = PaymentTransaction.objects.create(
            order=self.order,
            provider=PaymentProvider.BOG,
            payment_method=OrderPaymentMethod.CARD,
            action=PaymentTransactionAction.SALE,
            status=PaymentTransactionStatus.PAID,
            amount=Decimal("100.00"),
            currency="GEL",
            provider_order_id="bog-refund-order-1",
            provider_transaction_id="bog-sale-transaction-1",
            captured_at=timezone.now(),
        )
        self.client = Mock()
        self.client.refund_full.return_value = BogRefundResult(
            key="request_received",
            message="Refund request received",
            action_id="bog-refund-action-1",
            provider_reference={
                "key": "request_received",
                "action_id": "bog-refund-action-1",
            },
        )
        self.admin_user = get_user_model().objects.create_superuser(
            username="refund-admin@example.com",
            email="refund-admin@example.com",
            password="Password123!",
        )
        self.admin_client = Client()
        self.admin_client.force_login(self.admin_user)

    def _details(
        self,
        *,
        status,
        refund_amount,
        action_status="completed",
        action="refund",
        action_amount=Decimal("100.00"),
        action_code="100",
    ):
        return BogPaymentDetails(
            order_id=self.sale.provider_order_id,
            industry="ecommerce",
            status=status,
            external_order_id=f"FD-{self.sale.public_token}",
            capture="automatic",
            request_amount=self.sale.amount,
            transfer_amount=Decimal("0.00"),
            refund_amount=Decimal(refund_amount),
            currency="GEL",
            payment_method="card",
            payment_option="direct_debit",
            transaction_id=self.sale.provider_transaction_id,
            response_code="100",
            reject_reason="",
            provider_reference={"order_id": self.sale.provider_order_id},
            actions=(
                BogPaymentAction(
                    action_id="bog-refund-action-1",
                    action=action,
                    status=action_status,
                    code=action_code,
                    amount=Decimal(action_amount),
                ),
            ),
        )

    def test_full_refund_request_is_pending_and_reuses_accepted_action(self):
        refund = request_bog_full_refund(
            order=self.order,
            client=self.client,
        )
        replay = request_bog_full_refund(
            order=self.order,
            client=self.client,
        )

        self.order.refresh_from_db()
        self.assertEqual(refund.pk, replay.pk)
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUND_PENDING)
        self.assertEqual(refund.provider_action_id, "bog-refund-action-1")
        self.assertEqual(
            self.order.payment_status,
            OrderPaymentStatus.REFUND_PENDING,
        )
        self.client.refund_full.assert_called_once_with(
            order_id=self.sale.provider_order_id,
            idempotency_key=refund.idempotency_key,
        )

    def test_timeout_keeps_same_pending_refund_and_idempotency_key(self):
        self.client.refund_full.side_effect = BogTransportError(
            code="bog_refund_full_transport_error",
            retryable=True,
            outcome_unknown=True,
        )
        with self.assertRaises(BogTransportError):
            request_bog_full_refund(order=self.order, client=self.client)

        refund = PaymentTransaction.objects.get(
            action=PaymentTransactionAction.REFUND
        )
        first_key = refund.idempotency_key
        refund.refresh_from_db()
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUND_PENDING)

        retry_client = Mock()
        retry_client.refund_full.return_value = BogRefundResult(
            key="request_received",
            message="received",
            action_id="bog-refund-action-1",
            provider_reference={"action_id": "bog-refund-action-1"},
        )
        replay = request_bog_full_refund(
            order=self.order,
            client=retry_client,
        )

        self.assertEqual(replay.pk, refund.pk)
        self.assertEqual(replay.idempotency_key, first_key)
        retry_client.refund_full.assert_called_once_with(
            order_id=self.sale.provider_order_id,
            idempotency_key=first_key,
        )

    def test_definitive_refund_rejection_restores_paid_order_state(self):
        self.client.refund_full.side_effect = BogResponseError(
            code="bog_refund_not_allowed",
            status_code=400,
            retryable=False,
        )

        with self.assertRaises(BogResponseError):
            request_bog_full_refund(order=self.order, client=self.client)

        refund = PaymentTransaction.objects.get(
            action=PaymentTransactionAction.REFUND
        )
        self.order.refresh_from_db()
        self.assertEqual(refund.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(self.order.payment_status, OrderPaymentStatus.PAID)

    def test_verified_full_refund_cancels_order_and_restores_stock_once(self):
        refund = request_bog_full_refund(
            order=self.order,
            client=self.client,
        )
        details = self._details(
            status="refunded",
            refund_amount=Decimal("100.00"),
        )

        first = reconcile_bog_refund_details(
            self.sale,
            details,
            provider_reference={"source": "payment_details"},
        )
        second = reconcile_bog_refund_details(
            self.sale,
            details,
            provider_reference={"source": "payment_details"},
        )

        refund.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(first.result, "refunded_and_cancelled")
        self.assertEqual(second.result, "already_refunded")
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUNDED)
        self.assertIsNotNone(refund.refunded_at)
        self.assertEqual(self.order.payment_status, OrderPaymentStatus.REFUNDED)
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(self.order.stock_restored_at)
        self.assertEqual(self.product.stock_qty, 5)

    def test_rejected_refund_action_returns_order_to_paid(self):
        refund = request_bog_full_refund(
            order=self.order,
            client=self.client,
        )
        result = reconcile_bog_refund_details(
            self.sale,
            self._details(
                status="completed",
                refund_amount=Decimal("0.00"),
                action_status="rejected",
                action_code="204",
            ),
            provider_reference={"source": "payment_details"},
        )

        refund.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(result.result, "refund_rejected")
        self.assertEqual(refund.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(self.order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(self.order.status, OrderStatus.NEW)
        self.assertEqual(self.product.stock_qty, 4)

    def test_partial_refund_is_not_recorded_as_full_or_restocked(self):
        refund = request_bog_full_refund(
            order=self.order,
            client=self.client,
        )
        result = reconcile_bog_refund_details(
            self.sale,
            self._details(
                status="refunded_partially",
                refund_amount=Decimal("25.00"),
                action="partial_refund",
                action_amount=Decimal("25.00"),
            ),
            provider_reference={"source": "payment_details"},
        )

        refund.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(
            result.result,
            "partial_refund_requires_manual_reconciliation",
        )
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUND_PENDING)
        self.assertEqual(
            self.order.payment_status,
            OrderPaymentStatus.REFUND_PENDING,
        )
        self.assertEqual(self.order.status, OrderStatus.NEW)
        self.assertEqual(self.product.stock_qty, 4)

    def test_conflicting_refunded_and_rejected_status_requires_review(self):
        refund = request_bog_full_refund(
            order=self.order,
            client=self.client,
        )
        result = reconcile_bog_refund_details(
            self.sale,
            self._details(
                status="refunded",
                refund_amount=Decimal("100.00"),
                action_status="rejected",
                action_code="204",
            ),
            provider_reference={"source": "payment_details"},
        )

        refund.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(result.result, "refund_reconciliation_required")
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUND_PENDING)
        self.assertEqual(refund.error_code, "bog_refund_status_conflict")
        self.assertEqual(
            self.order.payment_status,
            OrderPaymentStatus.REFUND_PENDING,
        )
        self.assertEqual(self.product.stock_qty, 4)

    def test_shipped_order_cannot_start_cancel_and_refund_flow(self):
        self.order.status = OrderStatus.SHIPPED
        self.order.save(update_fields=["status", "updated_at"])

        with self.assertRaises(DjangoValidationError):
            request_bog_full_refund(order=self.order, client=self.client)

        self.client.refund_full.assert_not_called()
        self.assertFalse(
            PaymentTransaction.objects.filter(
                action=PaymentTransactionAction.REFUND
            ).exists()
        )

    def test_paid_fulfillment_incident_without_order_can_be_refunded(self):
        reservation = StockReservation.objects.create(
            guest_token=uuid.uuid4(),
            status=StockReservationStatus.RELEASED,
            expires_at=timezone.now() - timedelta(minutes=1),
            released_at=timezone.now(),
        )
        incident_sale = PaymentTransaction.objects.create(
            reservation=reservation,
            provider=PaymentProvider.BOG,
            payment_method=OrderPaymentMethod.CARD,
            action=PaymentTransactionAction.SALE,
            status=PaymentTransactionStatus.PAID,
            amount=Decimal("100.00"),
            currency="GEL",
            provider_order_id="bog-paid-incident-1",
            provider_transaction_id="bog-paid-incident-transaction-1",
            error_code="paid_stock_unavailable",
        )

        refund = request_bog_full_refund(
            sale_payment=incident_sale,
            client=self.client,
        )

        self.assertIsNone(refund.order_id)
        self.assertEqual(refund.reservation_id, reservation.pk)
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUND_PENDING)

    def test_order_admin_requires_confirmation_before_refund_request(self):
        url = reverse(
            "admin:commerce_order_bog_refund",
            args=[self.order.pk],
        )
        with patch("commerce.admin.request_bog_full_refund") as request_refund:
            response = self.admin_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Request full refund")
        self.assertContains(response, "cannot be cancelled")
        request_refund.assert_not_called()

    def test_order_admin_submits_refund_only_after_confirmation(self):
        url = reverse(
            "admin:commerce_order_bog_refund",
            args=[self.order.pk],
        )
        refund = Mock(
            status=PaymentTransactionStatus.REFUND_PENDING,
        )
        with patch(
            "commerce.admin.request_bog_full_refund",
            return_value=refund,
        ) as request_refund:
            response = self.admin_client.post(url)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        request_refund.assert_called_once()
        call = request_refund.call_args
        self.assertEqual(call.kwargs["order"].pk, self.order.pk)
        self.assertEqual(call.kwargs["requested_by"].pk, self.admin_user.pk)

    def test_order_admin_exposes_refund_and_reconciliation_buttons(self):
        response = self.admin_client.get(
            reverse("admin:commerce_order_change", args=[self.order.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Request full BOG refund")
        self.assertContains(response, "Refresh BOG status")
