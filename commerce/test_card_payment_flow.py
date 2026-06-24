import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, Lock
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITransactionTestCase

from catalog.models import Category, Product, ProductStatus

from .bog_payments import (
    BogCreateOrderResult,
    BogResponseError,
    BogTransportError,
)
from .card_payments import is_checkout_snapshot_intact, start_cart_card_payment
from .legal import TermsAcceptanceSnapshot
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    CheckoutAttempt,
    Order,
    OrderCheckoutSource,
    OrderPaymentMethod,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationStatus,
)
from .services import (
    BUY_NOW_TOKEN_COOKIE_NAME,
    CART_TOKEN_COOKIE_NAME,
    StockReservationError,
    build_checkout_owner_fingerprint,
    build_checkout_request_fingerprint,
    create_stock_reservation_from_cart,
    get_available_stock_quantity,
)


BOG_TEST_SETTINGS = {
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
}


@override_settings(**BOG_TEST_SETTINGS)
class CardPaymentFlowAPITests(APITransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="card-buyer@example.com",
            email="card-buyer@example.com",
            password="Password123!",
            is_active=True,
        )
        self.category = Category.objects.create(
            name="Brakes",
            slug="card-payment-brakes",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Brake pad set",
            slug="card-payment-brake-pad-set",
            sku="BP-100",
            short_description="Brake pads",
            description="Brake pad set",
            price=Decimal("80.00"),
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
        self.provider_factory = self.provider_patcher.start()
        self.addCleanup(self.provider_patcher.stop)

    def _checkout_payload(self, **overrides):
        payload = {
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
        payload.update(overrides)
        return payload

    def _create_cart(self, *, quantity=1):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=quantity,
            unit_price_snapshot=self.product.price,
        )
        return cart

    def _create_other_product(self):
        return Product.objects.create(
            category=self.category,
            name="Oil filter",
            slug=f"card-payment-oil-filter-{uuid.uuid4()}",
            sku=f"OF-{uuid.uuid4()}",
            short_description="Oil filter",
            description="Oil filter",
            price=Decimal("40.00"),
            stock_qty=3,
            status=ProductStatus.PUBLISHED,
        )

    def _provider_result(self, suffix="1"):
        order_id = f"bog-order-{suffix}"
        return BogCreateOrderResult(
            order_id=order_id,
            redirect_url=f"https://payment.bog.ge/?order_id={order_id}",
            details_url=(
                "https://api.bog.ge/payments/v1/receipt/"
                f"{order_id}"
            ),
            provider_reference={
                "id": order_id,
                "_links": {
                    "redirect": {
                        "href": (
                            "https://payment.bog.ge/"
                            f"?order_id={order_id}"
                        )
                    }
                },
            },
        )

    def _start_cart_payment(self, idempotency_key, **payload_overrides):
        return self.client.post(
            reverse("commerce-cart-card-payment-start"),
            self._checkout_payload(**payload_overrides),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(idempotency_key),
            REMOTE_ADDR="203.0.113.20",
            HTTP_USER_AGENT="Card payment test",
        )

    def test_cart_payment_start_reserves_stock_without_reducing_it(self):
        self._create_cart(quantity=2)
        self.provider_client.create_order.return_value = self._provider_result()
        idempotency_key = uuid.uuid4()

        response = self._start_cart_payment(idempotency_key)

        self.product.refresh_from_db()
        payment = PaymentTransaction.objects.get()
        reservation = StockReservation.objects.get()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], PaymentTransactionStatus.PENDING)
        self.assertEqual(response.data["result"], PaymentTransactionStatus.PENDING)
        self.assertEqual(
            response.data["redirect_url"],
            "https://payment.bog.ge/?order_id=bog-order-1",
        )
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(reservation.status, StockReservationStatus.ACTIVE)
        self.assertEqual(reservation.items.get().quantity, 2)
        self.assertGreater(
            reservation.expires_at,
            timezone.now() + timedelta(minutes=15),
        )
        self.assertEqual(payment.provider, PaymentProvider.BOG)
        self.assertEqual(payment.action, PaymentTransactionAction.SALE)
        self.assertEqual(payment.idempotency_key, idempotency_key)
        self.assertEqual(payment.provider_order_id, "bog-order-1")
        self.assertEqual(payment.amount, Decimal("160.00"))
        self.assertEqual(payment.currency, "GEL")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(payment.checkout_snapshot["source"], "cart")
        self.assertEqual(
            payment.checkout_snapshot["items"][0]["quantity"],
            2,
        )
        self.assertEqual(
            payment.checkout_snapshot["terms"]["ip_address"],
            "203.0.113.20",
        )
        self.assertEqual(
            payment.checkout_snapshot["terms"]["user_agent"],
            "Card payment test",
        )
        self.assertTrue(payment.checkout_snapshot["integrity_hash"])
        self.assertTrue(
            is_checkout_snapshot_intact(payment.checkout_snapshot)
        )
        changed_snapshot = {
            **payment.checkout_snapshot,
            "totals": {
                **payment.checkout_snapshot["totals"],
                "total": "1.00",
            },
        }
        self.assertFalse(is_checkout_snapshot_intact(changed_snapshot))
        provider_call = self.provider_client.create_order.call_args.kwargs
        self.assertEqual(provider_call["idempotency_key"], idempotency_key)
        self.assertEqual(provider_call["total_amount"], "160.00")
        self.assertEqual(provider_call["delivery_amount"], "0.00")
        self.assertEqual(provider_call["basket"][0]["product_id"], "BP-100")
        self.assertEqual(provider_call["basket"][0]["quantity"], 2)
        self.assertEqual(provider_call["ttl_minutes"], 15)
        self.assertIn(
            f"payment_token={payment.public_token}",
            provider_call["success_url"],
        )
        self.assertIn(
            f"payment_token={payment.public_token}",
            provider_call["fail_url"],
        )

    def test_cart_payment_start_respects_other_customer_reservation(self):
        other_user = get_user_model().objects.create_user(
            username="other-card-buyer@example.com",
            email="other-card-buyer@example.com",
            password="Password123!",
            is_active=True,
        )
        other_cart = Cart.objects.create(user=other_user)
        CartItem.objects.create(
            cart=other_cart,
            product=self.product,
            quantity=3,
            unit_price_snapshot=self.product.price,
        )
        create_stock_reservation_from_cart(
            cart=other_cart,
            user=other_user,
        )
        self._create_cart(quantity=1)

        response = self._start_cart_payment(uuid.uuid4())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "cart_availability_changed")
        self.assertEqual(
            response.data["cart_issues"][0]["issue_type"],
            "out_of_stock",
        )
        self.assertIn("cart_item_id", response.data["cart_issues"][0])
        self.assertEqual(PaymentTransaction.objects.count(), 0)
        self.provider_client.create_order.assert_not_called()

    def test_guest_cart_payment_keeps_guest_ownership_and_cookie(self):
        self.client.force_authenticate(user=None)
        add_response = self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.pk, "quantity": 1},
            format="json",
        )
        self.provider_client.create_order.return_value = self._provider_result(
            "guest-cart"
        )

        response = self._start_cart_payment(uuid.uuid4())

        payment = PaymentTransaction.objects.get()
        reservation = payment.reservation
        self.assertEqual(add_response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(reservation.user_id)
        self.assertIsNotNone(reservation.guest_token)
        self.assertEqual(
            str(reservation.guest_token),
            self.client.cookies[CART_TOKEN_COOKIE_NAME].value,
        )

    def test_provider_request_runs_after_database_transaction_commits(self):
        self._create_cart()

        def create_order(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            return self._provider_result()

        self.provider_client.create_order.side_effect = create_order

        response = self._start_cart_payment(uuid.uuid4())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_successful_same_key_replay_does_not_call_bog_twice(self):
        self._create_cart()
        self.provider_client.create_order.return_value = self._provider_result()
        idempotency_key = uuid.uuid4()

        first = self._start_cart_payment(idempotency_key)
        second = self._start_cart_payment(idempotency_key)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.assertEqual(
            first.data["payment_token"],
            second.data["payment_token"],
        )
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(StockReservation.objects.count(), 1)
        self.provider_client.create_order.assert_called_once()

    def test_timeout_can_be_retried_with_same_local_and_bog_key(self):
        cart = self._create_cart()
        self.provider_client.create_order.side_effect = [
            BogTransportError(
                code="bog_create_order_transport_error",
                retryable=True,
                outcome_unknown=True,
            ),
            self._provider_result("retry"),
        ]
        idempotency_key = uuid.uuid4()

        first = self._start_cart_payment(idempotency_key)
        cart_item = cart.items.get()
        cart_item.quantity = 2
        cart_item.save(update_fields=["quantity", "updated_at"])
        second = self._start_cart_payment(idempotency_key)

        payment = PaymentTransaction.objects.get()
        reservation = StockReservation.objects.get()
        self.assertEqual(
            first.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(first.data["code"], "card_payment_start_pending")
        self.assertTrue(first.data["retryable"])
        self.assertEqual(first.data["payment"]["payment_token"], str(payment.public_token))
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.assertEqual(payment.idempotency_key, idempotency_key)
        self.assertEqual(reservation.items.get().quantity, 1)
        self.assertEqual(self.provider_client.create_order.call_count, 2)
        first_call, second_call = self.provider_client.create_order.call_args_list
        self.assertEqual(
            first_call.kwargs["idempotency_key"],
            second_call.kwargs["idempotency_key"],
        )
        self.assertEqual(first_call.kwargs["total_amount"], "80.00")
        self.assertEqual(second_call.kwargs["total_amount"], "80.00")
        self.assertEqual(first_call.kwargs["basket"], second_call.kwargs["basket"])

    def test_second_key_is_blocked_while_payment_is_active(self):
        self._create_cart()
        self.provider_client.create_order.return_value = self._provider_result()

        first = self._start_cart_payment(uuid.uuid4())
        second = self._start_cart_payment(uuid.uuid4())

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "card_payment_already_active")
        self.assertEqual(
            second.data["payment"]["payment_token"],
            first.data["payment_token"],
        )
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(StockReservation.objects.count(), 1)
        self.provider_client.create_order.assert_called_once()

    def test_cart_card_payment_allows_different_product_while_previous_payment_is_active(
        self,
    ):
        cart = self._create_cart()
        other_product = self._create_other_product()
        self.provider_client.create_order.side_effect = [
            self._provider_result("first"),
            self._provider_result("second"),
        ]

        first = self._start_cart_payment(uuid.uuid4())
        first_payment = PaymentTransaction.objects.get()
        first_reservation = first_payment.reservation

        cart.items.all().delete()
        CartItem.objects.create(
            cart=cart,
            product=other_product,
            quantity=1,
            unit_price_snapshot=other_product.price,
        )
        second = self._start_cart_payment(uuid.uuid4())

        first_payment.refresh_from_db()
        first_reservation.refresh_from_db()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(
            first.data["payment_token"],
            second.data["payment_token"],
        )
        self.assertEqual(PaymentTransaction.objects.count(), 2)
        self.assertEqual(StockReservation.objects.count(), 2)
        self.assertEqual(first_payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(first_reservation.status, StockReservationStatus.ACTIVE)
        self.assertEqual(
            {
                reservation.items.get().product_id
                for reservation in StockReservation.objects.all()
            },
            {self.product.pk, other_product.pk},
        )

    def test_cod_checkout_is_blocked_while_cart_card_payment_is_active(self):
        self._create_cart()
        self.provider_client.create_order.return_value = self._provider_result()
        start_response = self._start_cart_payment(uuid.uuid4())

        cod_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(
                payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            ),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.product.refresh_from_db()
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(cod_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            cod_response.data["code"],
            "card_payment_already_active",
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(self.product.stock_qty, 3)

    def test_cod_checkout_allows_different_cart_product_while_card_payment_is_active(
        self,
    ):
        cart = self._create_cart()
        other_product = self._create_other_product()
        self.provider_client.create_order.return_value = self._provider_result()
        start_response = self._start_cart_payment(uuid.uuid4())
        pending_payment = PaymentTransaction.objects.get()
        pending_reservation = pending_payment.reservation

        cart.items.all().delete()
        CartItem.objects.create(
            cart=cart,
            product=other_product,
            quantity=1,
            unit_price_snapshot=other_product.price,
        )
        cod_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(
                payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            ),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.product.refresh_from_db()
        other_product.refresh_from_db()
        pending_payment.refresh_from_db()
        pending_reservation.refresh_from_db()
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(cod_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(
            order.payment_method,
            OrderPaymentMethod.CASH_ON_DELIVERY,
        )
        self.assertEqual(order.items.get().product, other_product)
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(other_product.stock_qty, 2)
        self.assertEqual(pending_payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(pending_reservation.status, StockReservationStatus.ACTIVE)
        self.assertEqual(pending_reservation.items.get().product, self.product)

    def test_definitive_provider_rejection_fails_attempt_and_releases_stock(self):
        self._create_cart()
        self.provider_client.create_order.side_effect = BogResponseError(
            code="bog_invalid_request",
            status_code=400,
            retryable=False,
        )

        response = self._start_cart_payment(uuid.uuid4())

        payment = PaymentTransaction.objects.get()
        reservation = StockReservation.objects.get()
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["code"], "card_payment_start_failed")
        self.assertFalse(response.data["retryable"])
        self.assertEqual(payment.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(payment.error_code, "bog_invalid_request")
        self.assertEqual(reservation.status, StockReservationStatus.RELEASED)
        self.assertEqual(CartItem.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 3)

    def test_retryable_provider_rejection_keeps_attempt_and_reservation_pending(self):
        self._create_cart()
        self.provider_client.create_order.side_effect = BogResponseError(
            code="bog_create_order_rejected",
            status_code=503,
            retryable=True,
        )

        response = self._start_cart_payment(uuid.uuid4())

        payment = PaymentTransaction.objects.get()
        reservation = StockReservation.objects.get()
        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(reservation.status, StockReservationStatus.ACTIVE)

    def test_failed_attempt_allows_new_key_and_new_reservation(self):
        self._create_cart()
        self.provider_client.create_order.side_effect = [
            BogResponseError(
                code="bog_invalid_request",
                status_code=400,
                retryable=False,
            ),
            self._provider_result("second"),
        ]

        first = self._start_cart_payment(uuid.uuid4())
        second = self._start_cart_payment(uuid.uuid4())

        self.assertEqual(first.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PaymentTransaction.objects.count(), 2)
        self.assertEqual(
            StockReservation.objects.filter(
                status=StockReservationStatus.ACTIVE
            ).count(),
            1,
        )

    def test_buy_now_payment_preserves_session_and_stock(self):
        session = BuyNowSession.objects.create(
            user=self.user,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=2,
        )
        self.provider_client.create_order.return_value = self._provider_result(
            "buy-now"
        )

        response = self.client.post(
            reverse("commerce-buy-now-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.product.refresh_from_db()
        payment = PaymentTransaction.objects.get()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(BuyNowSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(payment.checkout_snapshot["source"], "buy_now")
        self.assertEqual(
            payment.checkout_snapshot["source_reference"][
                "buy_now_session_id"
            ],
            session.pk,
        )
        self.assertEqual(payment.checkout_snapshot["items"][0]["quantity"], 2)

    def test_guest_buy_now_payment_keeps_session_and_guest_cookie(self):
        self.client.force_authenticate(user=None)
        session_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.pk, "quantity": 1},
            format="json",
        )
        self.provider_client.create_order.return_value = self._provider_result(
            "guest-buy-now"
        )

        response = self.client.post(
            reverse("commerce-buy-now-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        payment = PaymentTransaction.objects.get()
        reservation = payment.reservation
        self.assertEqual(session_response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(reservation.user_id)
        self.assertIsNotNone(reservation.guest_token)
        self.assertTrue(
            BuyNowSession.objects.filter(
                guest_token=reservation.guest_token
            ).exists()
        )
        self.assertEqual(
            str(reservation.guest_token),
            self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value,
        )

    def test_cod_checkout_is_blocked_while_buy_now_card_payment_is_active(self):
        session = BuyNowSession.objects.create(
            user=self.user,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=1,
        )
        self.provider_client.create_order.return_value = self._provider_result(
            "buy-now-active"
        )
        start_response = self.client.post(
            reverse("commerce-buy-now-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        cod_response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(
                payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            ),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.product.refresh_from_db()
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(cod_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            cod_response.data["code"],
            "card_payment_already_active",
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertTrue(BuyNowSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(self.product.stock_qty, 3)

    def test_cod_checkout_allows_different_buy_now_product_while_card_payment_is_active(
        self,
    ):
        other_product = self._create_other_product()
        session = BuyNowSession.objects.create(
            user=self.user,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=1,
        )
        self.provider_client.create_order.return_value = self._provider_result(
            "buy-now-active"
        )
        start_response = self.client.post(
            reverse("commerce-buy-now-card-payment-start"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        pending_payment = PaymentTransaction.objects.get()
        pending_reservation = pending_payment.reservation

        session.product = other_product
        session.unit_price_snapshot = other_product.price
        session.save(
            update_fields=["product", "unit_price_snapshot", "updated_at"]
        )
        cod_response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(
                payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            ),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.product.refresh_from_db()
        other_product.refresh_from_db()
        pending_payment.refresh_from_db()
        pending_reservation.refresh_from_db()
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(cod_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.checkout_source, OrderCheckoutSource.BUY_NOW)
        self.assertEqual(
            order.payment_method,
            OrderPaymentMethod.CASH_ON_DELIVERY,
        )
        self.assertEqual(order.items.get().product, other_product)
        self.assertFalse(BuyNowSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(other_product.stock_qty, 2)
        self.assertEqual(pending_payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(pending_reservation.status, StockReservationStatus.ACTIVE)
        self.assertEqual(pending_reservation.items.get().product, self.product)

    def test_payment_status_endpoint_exposes_no_provider_or_customer_data(self):
        self._create_cart()
        self.provider_client.create_order.return_value = self._provider_result()
        start_response = self._start_cart_payment(uuid.uuid4())

        self.client.force_authenticate(user=None)
        response = self.client.get(
            reverse(
                "commerce-card-payment-status",
                kwargs={
                    "public_token": start_response.data["payment_token"],
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["payment_token"],
            start_response.data["payment_token"],
        )
        self.assertIsNone(response.data["order_public_token"])
        self.assertIsNone(response.data["order_number"])
        self.assertNotIn("provider_order_id", response.data)
        self.assertNotIn("provider_reference", response.data)
        self.assertNotIn("checkout_snapshot", response.data)
        self.assertNotIn("email", str(response.data))
        self.assertNotIn("phone", str(response.data))

    def test_expired_unconfirmed_attempt_stays_pending_for_verification(self):
        self._create_cart()
        self.provider_client.create_order.side_effect = BogTransportError(
            code="bog_create_order_transport_error",
            retryable=True,
            outcome_unknown=True,
        )
        start_response = self._start_cart_payment(uuid.uuid4())
        payment = PaymentTransaction.objects.get()
        reservation = payment.reservation
        expired_at = timezone.now() - timedelta(seconds=1)
        snapshot = {
            **payment.checkout_snapshot,
            "provider_order_expires_at": expired_at.isoformat(),
        }
        PaymentTransaction.objects.filter(pk=payment.pk).update(
            expires_at=expired_at,
            checkout_snapshot=snapshot,
        )
        StockReservation.objects.filter(pk=reservation.pk).update(
            expires_at=expired_at
        )

        response = self.client.get(
            reverse(
                "commerce-card-payment-status",
                kwargs={
                    "public_token": start_response.data["payment"][
                        "payment_token"
                    ],
                },
            )
        )

        payment.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["status"],
            PaymentTransactionStatus.PENDING,
        )
        self.assertEqual(response.data["result"], "verification_pending")
        self.assertFalse(response.data["can_retry_start"])
        self.assertIsNone(response.data["redirect_url"])
        self.assertEqual(payment.status, PaymentTransactionStatus.PENDING)
        self.assertEqual(reservation.status, StockReservationStatus.ACTIVE)

        second_response = self._start_cart_payment(uuid.uuid4())
        self.assertEqual(
            second_response.status_code,
            status.HTTP_409_CONFLICT,
        )
        self.assertEqual(
            second_response.data["code"],
            "card_payment_already_active",
        )

    def test_unknown_payment_status_token_returns_404(self):
        response = self.client.get(
            reverse(
                "commerce-card-payment-status",
                kwargs={"public_token": uuid.uuid4()},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_card_start_requires_idempotency_key(self):
        self._create_cart()

        response = self.client.post(
            reverse("commerce-cart-card-payment-start"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("idempotency_key", response.data)
        self.assertEqual(PaymentTransaction.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)
        self.provider_client.create_order.assert_not_called()

    def test_card_start_requires_uuid4_idempotency_key(self):
        self._create_cart()

        response = self._start_cart_payment(uuid.uuid1())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data["idempotency_key"]),
            "Idempotency-Key must be a UUID version 4.",
        )
        self.assertEqual(PaymentTransaction.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)
        self.provider_client.create_order.assert_not_called()

    def test_card_start_rejects_cash_on_delivery_payload(self):
        self._create_cart()

        response = self._start_cart_payment(
            uuid.uuid4(),
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("payment_method", response.data)
        self.assertEqual(PaymentTransaction.objects.count(), 0)

    def test_card_start_requires_terms_acceptance(self):
        self._create_cart()

        response = self._start_cart_payment(
            uuid.uuid4(),
            terms_accepted=False,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("terms_accepted", response.data)
        self.assertEqual(PaymentTransaction.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)
        self.provider_client.create_order.assert_not_called()

    def test_card_start_requires_valid_recaptcha(self):
        self._create_cart()

        with patch("commerce.views.validate_recaptcha", return_value=False):
            response = self._start_cart_payment(uuid.uuid4())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PaymentTransaction.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)
        self.provider_client.create_order.assert_not_called()

    def test_same_key_with_changed_customer_payload_is_rejected(self):
        self._create_cart()
        self.provider_client.create_order.return_value = self._provider_result()
        idempotency_key = uuid.uuid4()

        first = self._start_cart_payment(idempotency_key)
        second = self._start_cart_payment(
            idempotency_key,
            city="Batumi",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            second.data["code"],
            "checkout_idempotency_conflict",
        )
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    @override_settings(BOG_PAYMENTS_ENABLED=False)
    def test_disabled_feature_creates_no_payment_state(self):
        self._create_cart()

        response = self._start_cart_payment(uuid.uuid4())

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(response.data["code"], "card_payments_disabled")
        self.assertEqual(PaymentTransaction.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)
        self.assertEqual(CheckoutAttempt.objects.count(), 0)
        self.provider_factory.assert_not_called()

    @override_settings(BOG_PAYMENTS_ENABLED=False)
    def test_card_payment_availability_is_disabled_by_backend_flag(self):
        response = self.client.get(
            reverse("commerce-card-payment-availability")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["enabled"])
        self.assertEqual(response.data["payment_method"], "card")
        self.assertEqual(response.data["provider"], "bog")
        self.assertEqual(response.data["currency"], "GEL")
        self.assertEqual(response.data["capture"], "automatic")
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(BOG_PAYMENTS_ENABLED=True)
    def test_card_payment_availability_is_enabled_by_backend_flag(self):
        response = self.client.get(
            reverse("commerce-card-payment-availability")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["enabled"])


class _ThreadSafeBogClient:
    def __init__(self):
        self.calls = []
        self.lock = Lock()

    def create_order(self, **kwargs):
        with self.lock:
            self.calls.append(kwargs)
            suffix = len(self.calls)
        order_id = f"bog-concurrent-order-{suffix}"
        return BogCreateOrderResult(
            order_id=order_id,
            redirect_url=f"https://payment.bog.ge/?order_id={order_id}",
            details_url=(
                "https://api.bog.ge/payments/v1/receipt/"
                f"{order_id}"
            ),
            provider_reference={"id": order_id},
        )


@override_settings(**BOG_TEST_SETTINGS)
@skipUnlessDBFeature("has_select_for_update")
class CardPaymentConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.users = [
            get_user_model().objects.create_user(
                username="race-card-buyer-1@example.com",
                email="race-card-buyer-1@example.com",
                password="Password123!",
                is_active=True,
            ),
            get_user_model().objects.create_user(
                username="race-card-buyer-2@example.com",
                email="race-card-buyer-2@example.com",
                password="Password123!",
                is_active=True,
            ),
        ]
        self.category = Category.objects.create(
            name="Race brakes",
            slug="race-card-payment-brakes",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Last brake pad",
            slug="race-card-payment-last-brake-pad",
            sku="RACE-BP-1",
            short_description="Last item",
            description="Last item",
            price=Decimal("80.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        self.carts = []
        for user in self.users:
            cart = Cart.objects.create(user=user)
            CartItem.objects.create(
                cart=cart,
                product=self.product,
                quantity=1,
                unit_price_snapshot=self.product.price,
            )
            self.carts.append(cart)
        self.provider_client = _ThreadSafeBogClient()

    def _checkout_payload(self, *, user):
        return {
            "first_name": "Race",
            "last_name": "Buyer",
            "email": user.email,
            "phone": "555123456",
            "city": "Tbilisi",
            "address_line": "Race Street 1",
            "note": "",
            "terms_accepted": True,
            "payment_method": OrderPaymentMethod.CARD,
        }

    def _terms_acceptance(self):
        return TermsAcceptanceSnapshot(
            accepted_at=timezone.now(),
            version="test-version",
            content_hash="a" * 64,
            content_snapshot={"page": {"slug": "terms"}, "components": []},
            url="https://flexdrive.example/terms",
            ip_address="127.0.0.1",
            user_agent="card-race-test",
        )

    def _start_payment(self, *, user_id, cart_id, idempotency_key, barrier):
        close_old_connections()
        try:
            user = get_user_model().objects.get(pk=user_id)
            cart = Cart.objects.get(pk=cart_id)
            validated_data = self._checkout_payload(user=user)
            barrier.wait(timeout=10)
            result = start_cart_card_payment(
                cart=cart,
                user=user,
                validated_data=validated_data,
                terms_acceptance=self._terms_acceptance(),
                idempotency_key=idempotency_key,
                owner_fingerprint=build_checkout_owner_fingerprint(user=user),
                request_fingerprint=build_checkout_request_fingerprint(
                    source=OrderCheckoutSource.CART,
                    validated_data=validated_data,
                ),
                client=self.provider_client,
            )
            return ("success", result.payment.pk)
        except StockReservationError as error:
            issue_type = error.issues[0]["issue_type"] if error.issues else ""
            return ("stock_error", issue_type)
        except Exception as error:
            return ("error", type(error).__name__, str(error))
        finally:
            close_old_connections()

    def test_parallel_card_starts_for_last_item_create_one_payment(self):
        barrier = Barrier(2)
        operations = [
            (self.users[0].pk, self.carts[0].pk, uuid.uuid4()),
            (self.users[1].pk, self.carts[1].pk, uuid.uuid4()),
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda operation: self._start_payment(
                        user_id=operation[0],
                        cart_id=operation[1],
                        idempotency_key=operation[2],
                        barrier=barrier,
                    ),
                    operations,
                )
            )

        self.product.refresh_from_db()
        self.assertEqual(
            sorted(result[0] for result in results),
            ["stock_error", "success"],
        )
        self.assertEqual(
            [result[1] for result in results if result[0] == "stock_error"],
            ["out_of_stock"],
        )
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(
            StockReservation.objects.filter(
                status=StockReservationStatus.ACTIVE
            ).count(),
            1,
        )
        self.assertEqual(len(self.provider_client.calls), 1)
        self.assertEqual(self.product.stock_qty, 1)
        self.assertEqual(
            get_available_stock_quantity(product=self.product),
            0,
        )
