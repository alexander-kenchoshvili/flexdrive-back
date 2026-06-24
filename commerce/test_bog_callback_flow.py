import base64
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITransactionTestCase

from catalog.models import Category, Product, ProductStatus

from .bog_callbacks import (
    reconcile_bog_payment,
    verify_bog_callback_signature,
)
from .bog_payments import (
    BogCreateOrderResult,
    BogPaymentDetails,
    BogRefundResult,
    BogTransportError,
)
from .bog_refunds import request_bog_full_refund
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    CheckoutAttempt,
    Order,
    OrderPaymentMethod,
    OrderPaymentStatus,
    PaymentTransaction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationStatus,
)
CALLBACK_TEST_SETTINGS = {
    "BOG_PAYMENTS_ENABLED": True,
    "BOG_CLIENT_ID": "test-client",
    "BOG_CLIENT_SECRET": "test-secret",
    "BOG_CALLBACK_PUBLIC_URL": (
        "https://flexdrive-back.example/api/commerce/payments/bog/callback/"
    ),
    "BOG_FRONTEND_SUCCESS_URL": (
        "https://flexdrive-front.example/checkout/payment/success"
    ),
    "BOG_FRONTEND_FAIL_URL": (
        "https://flexdrive-front.example/checkout/payment/fail"
    ),
    "BOG_ORDER_TTL_MINUTES": 15,
    "BOG_STOCK_RESERVATION_TTL_SECONDS": 1020,
    "BOG_CALLBACK_MAX_BODY_BYTES": 256 * 1024,
}


class BogCallbackFlowTests(APITransactionTestCase):
    serialized_rollback = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        cls.public_key_pem = (
            cls.private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )

    def setUp(self):
        self.settings_override = override_settings(
            **CALLBACK_TEST_SETTINGS,
            BOG_CALLBACK_PUBLIC_KEY=self.public_key_pem,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.user = get_user_model().objects.create_user(
            username="callback-buyer@example.com",
            email="callback-buyer@example.com",
            password="Password123!",
            is_active=True,
        )
        self.category = Category.objects.create(
            name="Callback Brakes",
            slug="callback-brakes",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Callback brake disc",
            slug="callback-brake-disc",
            sku="CBD-100",
            short_description="Brake disc",
            description="Brake disc",
            price=Decimal("90.00"),
            stock_qty=3,
            status=ProductStatus.PUBLISHED,
        )
        self.client.force_authenticate(user=self.user)
        self.recaptcha_patcher = patch(
            "commerce.views.validate_recaptcha",
            return_value=True,
        )
        self.recaptcha_patcher.start()
        self.addCleanup(self.recaptcha_patcher.stop)

        self.provider_client = Mock()
        self.provider_patcher = patch(
            "commerce.card_payments.BogPaymentsClient.from_settings",
            return_value=self.provider_client,
        )
        self.provider_patcher.start()
        self.addCleanup(self.provider_patcher.stop)

    def _checkout_payload(self):
        return {
            "first_name": "Nino",
            "last_name": "Beridze",
            "email": "nino@example.com",
            "phone": "555123456",
            "city": "Tbilisi",
            "address_line": "Saburtalo 1",
            "note": "",
            "terms_accepted": True,
            "payment_method": OrderPaymentMethod.CARD,
            "recaptcha_token": "test-token",
        }

    def _provider_result(self, order_id):
        return BogCreateOrderResult(
            order_id=order_id,
            redirect_url=f"https://payment.bog.ge/?order_id={order_id}",
            details_url=(
                "https://api.bog.ge/payments/v1/receipt/"
                f"{order_id}"
            ),
            provider_reference={"id": order_id},
        )

    def _start_cart_payment(
        self,
        *,
        quantity=1,
        order_id="bog-callback-order-1",
        provider_error=None,
    ):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=quantity,
            unit_price_snapshot=self.product.price,
        )
        if provider_error is None:
            self.provider_client.create_order.return_value = (
                self._provider_result(order_id)
            )
        else:
            self.provider_client.create_order.side_effect = provider_error
        response = self.client.post(
            reverse("commerce-cart-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        return cart, response, PaymentTransaction.objects.get()

    def _start_buy_now_payment(self, *, quantity=1, order_id="bog-buy-now-1"):
        session = BuyNowSession.objects.create(
            user=self.user,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=quantity,
        )
        self.provider_client.create_order.return_value = self._provider_result(
            order_id
        )
        response = self.client.post(
            reverse("commerce-buy-now-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        return session, response, PaymentTransaction.objects.get()

    def _callback_payload(
        self,
        payment,
        *,
        callback_status="completed",
        order_id=None,
        amount=None,
        currency="GEL",
        payment_method="card",
        payment_option="direct_debit",
        transaction_id=None,
        capture="automatic",
    ):
        amount = Decimal(amount if amount is not None else payment.amount)
        transaction_id = (
            transaction_id
            if transaction_id is not None
            else f"transaction-{payment.public_token}"
        )
        return {
            "event": "order_payment",
            "zoned_request_time": "2026-06-23T12:00:00.000000Z",
            "body": {
                "order_id": order_id or payment.provider_order_id,
                "industry": "ecommerce",
                "capture": capture,
                "external_order_id": f"FD-{payment.public_token}",
                "order_status": {
                    "key": callback_status,
                    "value": callback_status,
                },
                "buyer": {
                    "full_name": "Nino Beridze",
                    "email": "nino@example.com",
                    "phone_number": "555123456",
                },
                "purchase_units": {
                    "request_amount": f"{amount:.2f}",
                    "transfer_amount": (
                        f"{amount:.2f}"
                        if callback_status == "completed"
                        else "0.00"
                    ),
                    "refund_amount": "0.00",
                    "currency_code": currency,
                },
                "payment_detail": {
                    "transfer_method": {
                        "key": payment_method,
                        "value": "Card",
                    },
                    "payment_option": payment_option,
                    "transaction_id": (
                        transaction_id
                        if callback_status == "completed"
                        else ""
                    ),
                    "payer_identifier": "548888xxxxxx9893",
                    "card_expiry_date": "03/30",
                    "auth_code": "123456",
                    "code": "100",
                },
            },
        }

    def _signed_callback_request(self, payload, *, raw_body=None, signature=None):
        raw_body = raw_body or json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if signature is None:
            signature = base64.b64encode(
                self.private_key.sign(
                    raw_body,
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
            ).decode("ascii")
        return self.client.generic(
            "POST",
            reverse("commerce-bog-payment-callback"),
            raw_body,
            content_type="application/json",
            HTTP_CALLBACK_SIGNATURE=signature,
        )

    def test_valid_completed_callback_creates_paid_order_once(self):
        cart, start_response, payment = self._start_cart_payment(quantity=2)

        response = self._signed_callback_request(
            self._callback_payload(payment)
        )

        payment.refresh_from_db()
        reservation = payment.reservation
        reservation.refresh_from_db()
        self.product.refresh_from_db()
        order = Order.objects.get()
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "completed")
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(payment.order, order)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(order.payment_method, OrderPaymentMethod.CARD)
        self.assertEqual(order.total, Decimal("180.00"))
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(self.product.stock_qty, 1)
        self.assertEqual(reservation.status, StockReservationStatus.COMPLETED)
        self.assertEqual(reservation.completed_order, order)
        self.assertEqual(cart.items.count(), 0)
        self.assertEqual(
            CheckoutAttempt.objects.get(key=payment.idempotency_key).order,
            order,
        )
        self.assertEqual(
            payment.provider_reference["details"]["buyer"],
            "[REDACTED]",
        )
        self.assertNotIn(
            "548888xxxxxx9893",
            str(payment.provider_reference),
        )

    def test_duplicate_completed_callback_does_not_duplicate_order_or_stock(self):
        _, _, payment = self._start_cart_payment(quantity=1)
        payload = self._callback_payload(payment)

        first = self._signed_callback_request(payload)
        second = self._signed_callback_request(payload)

        self.product.refresh_from_db()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["result"], "already_completed")
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().items.count(), 1)
        self.assertEqual(self.product.stock_qty, 2)

    def test_callback_without_signature_changes_nothing(self):
        _, _, payment = self._start_cart_payment()
        raw_body = json.dumps(self._callback_payload(payment)).encode("utf-8")

        response = self._signed_callback_request(
            self._callback_payload(payment),
            raw_body=raw_body,
            signature="",
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["code"],
            "bog_callback_signature_missing",
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(Order.objects.count(), 0)

    def test_signature_is_verified_against_exact_raw_body(self):
        _, _, payment = self._start_cart_payment()
        payload = self._callback_payload(payment)
        signed_body = json.dumps(payload, separators=(",", ":")).encode()
        signature = base64.b64encode(
            self.private_key.sign(
                signed_body,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        ).decode()
        changed_body = signed_body.replace(
            b'"request_amount":"90.00"',
            b'"request_amount":"91.00"',
        )

        response = self._signed_callback_request(
            payload,
            raw_body=changed_body,
            signature=signature,
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["code"],
            "bog_callback_signature_invalid",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_signed_amount_mismatch_is_rejected_without_state_change(self):
        _, _, payment = self._start_cart_payment()

        response = self._signed_callback_request(
            self._callback_payload(payment, amount="91.00")
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "bog_callback_amount_mismatch",
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(Order.objects.count(), 0)

    def test_signed_non_card_method_is_rejected(self):
        _, _, payment = self._start_cart_payment()

        response = self._signed_callback_request(
            self._callback_payload(payment, payment_method="google_pay")
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "bog_callback_payment_method_mismatch",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_signed_capture_mode_mismatch_is_rejected(self):
        _, _, payment = self._start_cart_payment()

        response = self._signed_callback_request(
            self._callback_payload(payment, capture="manual")
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "bog_callback_capture_mismatch",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_signed_recurrent_payment_option_is_rejected(self):
        _, _, payment = self._start_cart_payment()

        response = self._signed_callback_request(
            self._callback_payload(payment, payment_option="recurrent")
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "bog_callback_payment_option_mismatch",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_rejected_callback_releases_reservation_without_order(self):
        cart, _, payment = self._start_cart_payment(quantity=2)

        response = self._signed_callback_request(
            self._callback_payload(payment, callback_status="rejected")
        )

        payment.refresh_from_db()
        reservation = payment.reservation
        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "rejected")
        self.assertEqual(payment.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(reservation.status, StockReservationStatus.RELEASED)
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(Order.objects.count(), 0)

    def test_late_rejected_callback_cannot_regress_paid_order(self):
        _, _, payment = self._start_cart_payment()
        completed = self._signed_callback_request(
            self._callback_payload(payment)
        )

        rejected = self._signed_callback_request(
            self._callback_payload(payment, callback_status="rejected")
        )

        payment.refresh_from_db()
        order = Order.objects.get()
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.data["result"], "late_rejection_ignored")
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)

    def test_processing_callback_keeps_attempt_pending(self):
        _, _, payment = self._start_cart_payment()

        response = self._signed_callback_request(
            self._callback_payload(payment, callback_status="processing")
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "pending")
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(payment.error_code, "")
        self.assertEqual(Order.objects.count(), 0)

    def test_unknown_status_stays_pending_for_reconciliation(self):
        _, _, payment = self._start_cart_payment()

        response = self._signed_callback_request(
            self._callback_payload(payment, callback_status="new_future_status")
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "reconciliation_required")
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(
            payment.error_code,
            "bog_unknown_status_requires_reconciliation",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_incomplete_refund_status_requires_reconciliation(self):
        _, _, payment = self._start_cart_payment()
        self._signed_callback_request(self._callback_payload(payment))
        payment.refresh_from_db()

        response = self._signed_callback_request(
            self._callback_payload(payment, callback_status="refunded")
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["result"],
            "refund_reconciliation_required",
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        refund = PaymentTransaction.objects.get(
            action="refund",
        )
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUND_PENDING)
        self.assertEqual(refund.error_code, "bog_refund_amount_mismatch")
        self.assertEqual(Order.objects.count(), 1)

    def test_refund_callback_before_local_paid_state_is_flagged_not_crashed(self):
        _, _, payment = self._start_cart_payment(quantity=1)
        payload = self._callback_payload(
            payment,
            callback_status="refunded",
        )
        payload["body"]["purchase_units"]["refund_amount"] = (
            f"{payment.amount:.2f}"
        )
        payload["body"]["actions"] = [
            {
                "action_id": "out-of-order-refund-action",
                "action": "refund",
                "status": "completed",
                "code": "100",
                "amount": f"{payment.amount:.2f}",
            }
        ]

        response = self._signed_callback_request(payload)

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["result"],
            "refund_reconciliation_required",
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(
            payment.error_code,
            "bog_refund_requires_manual_reconciliation",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_signed_full_refund_callback_finalizes_refund_and_stock_once(self):
        _, _, payment = self._start_cart_payment(quantity=1)
        self._signed_callback_request(self._callback_payload(payment))
        payment.refresh_from_db()
        order = payment.order
        refund_client = Mock()
        refund_client.refund_full.return_value = BogRefundResult(
            key="request_received",
            message="received",
            action_id="bog-refund-callback-action-1",
            provider_reference={
                "key": "request_received",
                "action_id": "bog-refund-callback-action-1",
            },
        )
        request_bog_full_refund(order=order, client=refund_client)

        payload = self._callback_payload(
            payment,
            callback_status="refunded",
        )
        payload["body"]["purchase_units"]["refund_amount"] = (
            f"{payment.amount:.2f}"
        )
        payload["body"]["actions"] = [
            {
                "action_id": "bog-refund-callback-action-1",
                "action": "refund",
                "status": "completed",
                "code": "100",
                "amount": f"{payment.amount:.2f}",
            }
        ]
        first = self._signed_callback_request(payload)
        second = self._signed_callback_request(payload)

        refund = PaymentTransaction.objects.get(action="refund")
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(first.data["result"], "refunded_and_cancelled")
        self.assertEqual(second.data["result"], "already_refunded")
        self.assertEqual(refund.status, PaymentTransactionStatus.REFUNDED)
        self.assertEqual(order.payment_status, OrderPaymentStatus.REFUNDED)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.product.stock_qty, 3)

    def test_callback_can_recover_provider_order_after_start_timeout(self):
        _, start_response, payment = self._start_cart_payment(
            provider_error=BogTransportError(
                code="bog_create_order_transport_error",
                retryable=True,
                outcome_unknown=True,
            )
        )
        self.assertEqual(
            start_response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(payment.provider_order_id, "")
        recovered_order_id = "bog-recovered-order"

        response = self._signed_callback_request(
            self._callback_payload(
                payment,
                order_id=recovered_order_id,
            )
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(payment.provider_order_id, recovered_order_id)
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(Order.objects.count(), 1)

    def test_authenticated_payment_details_reconciliation_uses_same_finalizer(self):
        _, _, payment = self._start_cart_payment()
        details_client = Mock()
        details_client.get_payment_details.return_value = BogPaymentDetails(
            order_id=payment.provider_order_id,
            industry="ecommerce",
            status="completed",
            external_order_id=f"FD-{payment.public_token}",
            capture="automatic",
            request_amount=payment.amount,
            transfer_amount=payment.amount,
            refund_amount=Decimal("0.00"),
            currency="GEL",
            payment_method="card",
            payment_option="direct_debit",
            transaction_id="details-transaction-1",
            response_code="100",
            reject_reason="",
            provider_reference={
                "order_id": payment.provider_order_id,
            },
        )

        result = reconcile_bog_payment(payment, client=details_client)

        payment.refresh_from_db()
        self.assertEqual(result.result, "completed")
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(
            payment.provider_reference["source"],
            "payment_details",
        )
        self.assertEqual(Order.objects.count(), 1)

    def test_expired_reservation_can_finalize_after_fresh_stock_check(self):
        _, _, payment = self._start_cart_payment(quantity=2)
        StockReservation.objects.filter(pk=payment.reservation_id).update(
            status=StockReservationStatus.EXPIRED,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = self._signed_callback_request(
            self._callback_payload(payment)
        )

        payment.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.product.stock_qty, 1)

    def test_paid_callback_never_drives_stock_negative(self):
        _, _, payment = self._start_cart_payment(quantity=2)
        Product.objects.filter(pk=self.product.pk).update(stock_qty=1)

        response = self._signed_callback_request(
            self._callback_payload(payment)
        )

        payment.refresh_from_db()
        reservation = payment.reservation
        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "paid_fulfillment_blocked")
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(payment.error_code, "paid_stock_unavailable")
        self.assertEqual(reservation.status, StockReservationStatus.RELEASED)
        self.assertEqual(self.product.stock_qty, 1)
        self.assertEqual(Order.objects.count(), 0)

    def test_late_success_for_older_attempt_does_not_override_newer_attempt(self):
        _, _, first_payment = self._start_cart_payment(
            order_id="bog-old-order"
        )
        rejected = self._signed_callback_request(
            self._callback_payload(
                first_payment,
                callback_status="rejected",
            )
        )
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)

        CartItem.objects.update_or_create(
            cart=Cart.objects.get(user=self.user),
            product=self.product,
            defaults={
                "quantity": 1,
                "unit_price_snapshot": self.product.price,
            },
        )
        self.provider_client.create_order.side_effect = None
        self.provider_client.create_order.return_value = self._provider_result(
            "bog-new-order"
        )
        new_response = self.client.post(
            reverse("commerce-cart-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        newer_payment = PaymentTransaction.objects.exclude(
            pk=first_payment.pk
        ).get()

        late_success = self._signed_callback_request(
            self._callback_payload(
                first_payment,
                callback_status="completed",
            )
        )

        first_payment.refresh_from_db()
        newer_payment.refresh_from_db()
        self.assertEqual(new_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(late_success.status_code, status.HTTP_200_OK)
        self.assertEqual(
            late_success.data["result"],
            "paid_fulfillment_blocked",
        )
        self.assertEqual(
            first_payment.error_code,
            "paid_older_attempt_requires_refund",
        )
        self.assertEqual(first_payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(newer_payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(Order.objects.count(), 0)

    def test_duplicate_provider_transaction_id_is_rejected(self):
        _, _, first_payment = self._start_cart_payment(
            order_id="bog-first-order"
        )
        shared_transaction_id = "shared-provider-transaction"
        first_response = self._signed_callback_request(
            self._callback_payload(
                first_payment,
                transaction_id=shared_transaction_id,
            )
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        cart = Cart.objects.get(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=1,
            unit_price_snapshot=self.product.price,
        )
        self.provider_client.create_order.return_value = self._provider_result(
            "bog-second-order"
        )
        self.client.post(
            reverse("commerce-cart-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        second_payment = PaymentTransaction.objects.exclude(
            pk=first_payment.pk
        ).get()

        second_response = self._signed_callback_request(
            self._callback_payload(
                second_payment,
                transaction_id=shared_transaction_id,
            )
        )

        second_payment.refresh_from_db()
        self.assertEqual(second_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            second_response.data["code"],
            "bog_callback_transaction_id_duplicate",
        )
        self.assertEqual(
            second_payment.status,
            PaymentTransactionStatus.PENDING,
        )
        self.assertEqual(Order.objects.count(), 1)

    def test_tampered_snapshot_blocks_order_but_records_paid_payment(self):
        _, _, payment = self._start_cart_payment()
        changed_snapshot = {
            **payment.checkout_snapshot,
            "buyer": {
                **payment.checkout_snapshot["buyer"],
                "city": "Changed city",
            },
        }
        PaymentTransaction.objects.filter(pk=payment.pk).update(
            checkout_snapshot=changed_snapshot
        )

        response = self._signed_callback_request(
            self._callback_payload(payment)
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "paid_fulfillment_blocked")
        self.assertEqual(
            payment.error_code,
            "paid_snapshot_integrity_failed",
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PAID)
        self.assertEqual(Order.objects.count(), 0)

    def test_paid_cart_consumes_only_paid_quantity_from_changed_cart(self):
        cart, _, payment = self._start_cart_payment(quantity=1)
        cart_item = cart.items.get()
        cart_item.quantity = 3
        cart_item.save(update_fields=["quantity", "updated_at"])

        response = self._signed_callback_request(
            self._callback_payload(payment)
        )

        cart_item.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(cart_item.quantity, 2)
        self.assertEqual(Order.objects.get().items.get().quantity, 1)

    def test_completed_buy_now_callback_removes_unchanged_session(self):
        session, _, payment = self._start_buy_now_payment(quantity=1)

        response = self._signed_callback_request(
            self._callback_payload(payment)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(BuyNowSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(Order.objects.count(), 1)

    def test_public_payment_status_contains_created_order_token(self):
        _, _, payment = self._start_cart_payment()
        self._signed_callback_request(self._callback_payload(payment))
        payment.refresh_from_db()

        response = self.client.get(
            reverse(
                "commerce-card-payment-status",
                kwargs={"public_token": payment.public_token},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            str(response.data["order_public_token"]),
            str(payment.order.public_token),
        )
        self.assertEqual(response.data["order_number"], payment.order.order_number)
        self.assertEqual(response.data["status"], PaymentTransactionStatus.PAID)

    def test_callback_is_the_only_commerce_post_exempt_from_csrf(self):
        _, _, payment = self._start_cart_payment()
        payload = self._callback_payload(payment)
        raw_body = json.dumps(payload, separators=(",", ":")).encode()
        signature = base64.b64encode(
            self.private_key.sign(
                raw_body,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        ).decode()
        csrf_client = Client(enforce_csrf_checks=True)

        callback_response = csrf_client.post(
            reverse("commerce-bog-payment-callback"),
            raw_body,
            content_type="application/json",
            HTTP_CALLBACK_SIGNATURE=signature,
        )
        cart_response = csrf_client.post(
            reverse("commerce-cart-item-list"),
            json.dumps({"product_id": self.product.pk, "quantity": 1}),
            content_type="application/json",
        )

        self.assertEqual(callback_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cart_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            cart_response.json()["code"],
            "csrf_failed",
        )

    @override_settings(BOG_CALLBACK_MAX_BODY_BYTES=10)
    def test_oversized_callback_is_rejected_before_signature_processing(self):
        response = self.client.generic(
            "POST",
            reverse("commerce-bog-payment-callback"),
            b'{"more":"than ten bytes"}',
            content_type="application/json",
            HTTP_CALLBACK_SIGNATURE="not-used",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
        self.assertEqual(
            response.data["code"],
            "bog_callback_body_too_large",
        )

    def test_signature_helper_rejects_invalid_base64(self):
        with self.assertRaisesMessage(
            Exception,
            "Callback signature is invalid.",
        ):
            verify_bog_callback_signature(
                b'{"event":"order_payment"}',
                "not valid base64!",
                public_key_pem=self.public_key_pem,
            )

    def test_signed_json_with_duplicate_keys_is_rejected(self):
        _, _, payment = self._start_cart_payment()
        body = self._callback_payload(payment)["body"]
        raw_body = (
            '{"event":"order_payment","event":"order_payment",'
            '"zoned_request_time":"2026-06-23T12:00:00Z",'
            f'"body":{json.dumps(body, separators=(",", ":"))}'
            "}"
        ).encode("utf-8")

        response = self._signed_callback_request(
            {},
            raw_body=raw_body,
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["code"],
            "bog_callback_invalid_json",
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(Order.objects.count(), 0)
