import copy
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.services import delete_user_account
from catalog.models import Category, Product, ProductStatus
from .card_payments import start_cart_card_payment
from .checkout_snapshots import snapshot_hash
from .credo_checkout import (
    CredoCheckoutError, apply_credo_observation,
    prepare_buy_now_credo_application, prepare_cart_credo_application,
)
from .inventory import consume_order_inventory
from .legal import TermsAcceptanceSnapshot
from .models import (
    BuyNowSession, Cart, CartItem, CredoApplication, Order, OrderItemInventory,
    OrderPaymentMethod, PaymentTransaction, StockReservation,
)
from .serializers import CheckoutSerializer
from .services import (
    CheckoutIdempotencyConflict, CheckoutPaymentInProgress, StockReservationError,
    build_checkout_owner_fingerprint, build_checkout_request_fingerprint,
    can_cancel_order, can_transition_order_status, create_order_from_cart,
    create_stock_reservation_from_cart, get_reserved_stock_quantities,
)


@override_settings(BOG_PAYMENTS_ENABLED=True, CACHES={
    "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
    "throttling": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
})
class CredoCheckoutFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="credo-owner@example.test", email="credo-owner@example.test")
        category = Category.objects.create(name="Credo parts", slug="credo-parts")
        cls.product = Product.objects.create(
            category=category, name="საცდელი ავტონაწილი", slug="credo-test-part", sku="CP-1",
            internal_sku="FD-10-0001", price=Decimal("60.00"), supplier_price=Decimal("40.00"),
            stock_qty=10, status=ProductStatus.PUBLISHED,
        )

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("catalog.models.CUSTOMER_STOCK_RESERVE_QTY", 0).start()
        patch("requests.request", side_effect=AssertionError("No bank/network requests in local lifecycle tests")).start()
        self.purchase_event = patch("commerce.services.send_meta_purchase_event").start()
        self.quote = {
            "version": 3, "provider": "wingo", "service_slug": "standard", "delivery_type_id": 1,
            "weight_range_id": 1, "provider_region_id": "test-region", "provider_city_id": "test-city",
            "region_id": 1, "region_name": "Tbilisi", "city_id": 2, "city_name": "Tbilisi",
            "carrier_delivery_cost": "9.00", "delivery_margin": "0.00", "customer_delivery_price": "9.00",
            "tariff_revision": "test-reference", "measurements": {"weight": "1.00", "length": None, "width": None, "height": None},
        }
        # This boundary supplies an already validated local delivery quote.
        patch("commerce.checkout_snapshots.resolve_checkout_delivery", return_value=self.quote).start()
        self.cart = Cart.objects.create(guest_token=uuid.uuid4())
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=1, unit_price_snapshot=Decimal("60.00"))
        self.data = {
            "buyer_type": "individual", "first_name": "Test", "last_name": "Buyer",
            "personal_number": "00000000001", "phone": "555000001", "email": "buyer@example.test",
            "city": "Tbilisi", "address_line": "Test address", "payment_method": "credo",
            "delivery_region_id": 1, "delivery_city_id": 2, "terms_accepted": True,
        }
        self.terms = TermsAcceptanceSnapshot(
            timezone.now(), "test-version", "a" * 64, {"title": "Test terms"},
            "https://shop.example/terms", None, "test agent",
        )
        self.key = uuid.uuid4()

    def prepare(self, **overrides):
        options = {
            "cart": self.cart, "user": None, "validated_data": self.data,
            "terms_acceptance": self.terms, "idempotency_key": self.key,
            "requested_offer": "dayavi", "merchant_id": "999999999999",
            "reservation_ttl_seconds": 1200,
        }
        options.update(overrides)
        return prepare_cart_credo_application(**options)


class CredoCheckoutTests(CredoCheckoutFixture):
    def test_preparation_reserves_and_freezes_one_total_without_charging_or_creating_order(self):
        first = self.prepare()
        second = self.prepare()
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.application.pk, second.application.pk)
        self.assertEqual(CredoApplication.objects.count(), 1)
        self.assertEqual(StockReservation.objects.count(), 1)
        self.assertEqual(first.application.requested_amount, Decimal("69.00"))
        self.assertIsNone(first.application.checkout_snapshot["provider_order_expires_at"])
        self.assertEqual(get_reserved_stock_quantities(product_ids=[self.product.pk]), {self.product.pk: 1})
        self.assertFalse(Order.objects.exists())
        self.assertFalse(PaymentTransaction.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 10)

    def test_same_key_cannot_change_offer_buyer_destination_or_bank_account(self):
        self.prepare()
        for options in (
            {"requested_offer": "installment"}, {"merchant_id": "888888888888"},
            {"validated_data": {**self.data, "personal_number": "00000000002"}},
            {"validated_data": {**self.data, "delivery_city_id": 3}}, {"is_test": True},
        ):
            with self.subTest(options=options), self.assertRaises(CheckoutIdempotencyConflict):
                self.prepare(**options)
        self.assertEqual(CredoApplication.objects.count(), 1)

    def test_second_credo_and_cod_attempt_are_blocked_in_the_same_checkout(self):
        application = self.prepare().application
        with self.assertRaises(CheckoutPaymentInProgress):
            self.prepare(idempotency_key=uuid.uuid4())
        with self.assertRaises(CheckoutPaymentInProgress):
            create_order_from_cart(cart=self.cart, user=None, validated_data={**self.data, "payment_method": "cash_on_delivery"},
                                   terms_acceptance=self.terms)
        application.reservation.refresh_from_db()
        self.assertEqual(application.reservation.status, "active")

    def test_bog_start_cannot_replace_a_credo_reservation(self):
        self.prepare()
        bank = Mock()
        data = {**self.data, "payment_method": "card"}
        with self.assertRaises(CheckoutPaymentInProgress):
            start_cart_card_payment(
                cart=self.cart, user=None, validated_data=data, terms_acceptance=self.terms,
                idempotency_key=uuid.uuid4(), owner_fingerprint=build_checkout_owner_fingerprint(guest_token=self.cart.guest_token),
                request_fingerprint=build_checkout_request_fingerprint(source="cart", validated_data=data),
                marketing_consent=False, marketing_context={}, client=bank,
            )
        bank.create_order.assert_not_called()
        self.assertEqual(CredoApplication.objects.count(), 1)
        self.assertEqual(StockReservation.objects.count(), 1)

    def test_pending_bog_attempt_blocks_credo_preparation(self):
        reservation = create_stock_reservation_from_cart(cart=self.cart, guest_token=self.cart.guest_token)
        PaymentTransaction.objects.create(reservation=reservation, provider="bog", action="sale", status="pending", amount=Decimal("69.00"))
        with self.assertRaises(CheckoutPaymentInProgress):
            self.prepare()
        self.assertFalse(CredoApplication.objects.exists())

    def test_processing_and_unsigned_approval_do_not_create_an_order(self):
        application = self.prepare().application
        for status in (11, 10, 2, 9, 13, 14, 3, 4):
            with self.subTest(status=status):
                application = apply_credo_observation(application.pk, status)
                self.assertFalse(application.needs_review)
                self.assertIsNone(application.order_id)
        self.assertFalse(Order.objects.exists())

    def test_signature_creates_exactly_one_fulfillable_order_without_a_cash_receipt(self):
        application = self.prepare().application
        first = apply_credo_observation(application.pk, 12)
        second = apply_credo_observation(application.pk, 12)
        self.assertEqual(first.order_id, second.order_id)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItemInventory.objects.count(), 1)
        self.assertEqual(first.order.total, Decimal("69.00"))
        self.assertEqual(first.order.payment_method, OrderPaymentMethod.CREDO)
        self.assertEqual(first.order.payment_status, "pending")
        self.assertTrue(can_transition_order_status(first.order, "processing"))
        self.assertFalse(can_cancel_order(first.order))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 9)
        self.assertFalse(self.cart.items.exists())
        self.assertFalse(PaymentTransaction.objects.exists())
        self.purchase_event.assert_not_called()

    def test_skipped_signature_and_duplicate_completion_do_not_duplicate_stock_or_cash(self):
        application = self.prepare().application
        first = apply_credo_observation(application.pk, 5)
        again = apply_credo_observation(application.pk, 5)
        self.assertEqual(first.order_id, again.order_id)
        self.assertIsNotNone(first.funding_completed_at)
        self.assertIsNone(first.signed_at)  # Exact historical signature time is unknown.
        self.assertEqual(first.order.payment_status, "pending")  # Settlement is a later stage.
        self.assertEqual(OrderItemInventory.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 9)
        self.assertFalse(PaymentTransaction.objects.exists())
        self.purchase_event.assert_not_called()

    def test_rejected_or_cancelled_unsigned_application_releases_only_the_hold(self):
        for status in (6, 7):
            application = self.prepare(idempotency_key=uuid.uuid4()).application
            result = apply_credo_observation(application.pk, status)
            result.reservation.refresh_from_db()
            self.assertEqual(result.reservation.status, "released")
            self.assertFalse(result.needs_review)
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 10)

    def test_cancel_after_signature_is_review_not_inventory_restoration(self):
        application = apply_credo_observation(self.prepare().application.pk, 12)
        conflict = apply_credo_observation(application.pk, 7)
        again = apply_credo_observation(application.pk, 12)
        self.assertTrue(conflict.needs_review)
        self.assertTrue(again.needs_review)
        self.assertEqual(again.bank_status, 12)
        self.assertFalse(can_transition_order_status(again.order, "processing"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 9)

    def test_expired_local_hold_does_not_allow_another_payment(self):
        application = self.prepare().application
        StockReservation.objects.filter(pk=application.reservation_id).update(expires_at=timezone.now()-timedelta(seconds=1), status="expired")
        with self.assertRaises(CheckoutPaymentInProgress):
            self.prepare(idempotency_key=uuid.uuid4())
        result = apply_credo_observation(application.pk, 12)
        self.assertFalse(result.needs_review)
        self.assertIsNotNone(result.order_id)

    def test_late_signature_cannot_take_stock_reserved_by_another_checkout(self):
        Product.objects.filter(pk=self.product.pk).update(stock_qty=1)
        application = self.prepare().application
        StockReservation.objects.filter(pk=application.reservation_id).update(expires_at=timezone.now()-timedelta(seconds=1), status="expired")
        other = Cart.objects.create(guest_token=uuid.uuid4())
        CartItem.objects.create(cart=other, product=self.product, quantity=1, unit_price_snapshot=Decimal("60.00"))
        create_stock_reservation_from_cart(cart=other, guest_token=other.guest_token)
        result = apply_credo_observation(application.pk, 12)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.last_issue, "credo_stock_unavailable")
        self.assertIsNone(result.order_id)
        self.assertFalse(Order.objects.exists())

    def test_frozen_price_and_cost_survive_catalog_changes(self):
        application = self.prepare().application
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("80.00"), supplier_price=Decimal("50.00"))
        result = apply_credo_observation(application.pk, 12)
        item = result.order.items.get()
        self.assertEqual(item.unit_price, Decimal("60.00"))
        self.assertEqual(item.purchase_unit_gross, Decimal("40.00"))
        self.assertEqual(result.order.total, Decimal("69.00"))

    def test_corrupt_snapshot_or_changed_reservation_cannot_create_order(self):
        application = self.prepare().application
        application.checkout_snapshot["buyer"]["first_name"] = "Altered"
        application.save(update_fields=["checkout_snapshot"])
        result = apply_credo_observation(application.pk, 12)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.last_issue, "credo_snapshot_integrity_failed")
        self.assertFalse(Order.objects.exists())

    def test_partial_inventory_failure_rolls_back_order_items_stock_and_source_cleanup(self):
        application = self.prepare().application
        def fail_after_consumption(**kwargs):
            consume_order_inventory(**kwargs)
            raise DjangoValidationError("Simulated inventory failure")
        with patch("commerce.credo_checkout.consume_order_inventory", side_effect=fail_after_consumption):
            result = apply_credo_observation(application.pk, 12)
        self.assertTrue(result.needs_review)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItemInventory.objects.exists())
        self.assertTrue(self.cart.items.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 10)

    def test_buy_now_consumption_and_replay_are_idempotent(self):
        session = BuyNowSession.objects.create(guest_token=uuid.uuid4(), product=self.product, quantity=2, unit_price_snapshot=Decimal("60.00"))
        options = dict(session=session, user=None, validated_data=self.data, terms_acceptance=self.terms,
                       idempotency_key=self.key, requested_offer="installment", merchant_id="999999999999", reservation_ttl_seconds=1200)
        application = prepare_buy_now_credo_application(**options).application
        self.assertEqual(application.requested_amount, Decimal("129.00"))
        result = apply_credo_observation(application.pk, 12)
        self.assertFalse(BuyNowSession.objects.filter(pk=session.pk).exists())
        replay = prepare_buy_now_credo_application(**options)
        self.assertFalse(replay.created)
        self.assertEqual(replay.application.order_id, result.order_id)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 8)

    def test_test_application_never_retains_marketing_identifiers(self):
        application = self.prepare(is_test=True, marketing_consent=True, marketing_context={"fbp": "test-browser"}).application
        self.assertEqual(application.checkout_snapshot["marketing"], {"consent": False, "context": {}})
        result = apply_credo_observation(application.pk, 12)
        self.assertFalse(result.order.marketing_consent)
        self.assertEqual(result.order.marketing_context, {})

    def test_deleted_account_cannot_be_reconstructed_from_later_bank_success(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price_snapshot=Decimal("60.00"))
        application = self.prepare(cart=cart, user=self.user).application
        delete_user_account(self.user)
        application.refresh_from_db()
        self.assertEqual(application.checkout_snapshot, {})
        self.assertTrue(application.needs_review)
        result = apply_credo_observation(application.pk, 12)
        self.assertIsNone(result.order_id)
        self.assertFalse(Order.objects.exists())

    def test_regular_checkout_cannot_bypass_financing_start(self):
        with self.assertRaises(ValidationError):
            CheckoutSerializer().validate_payment_method(OrderPaymentMethod.CREDO)

    def test_invalid_preparation_never_leaves_a_hold(self):
        for options in ({"idempotency_key": uuid.uuid1()}, {"requested_offer": "bog"}, {"reservation_ttl_seconds": 0}):
            with self.subTest(options=options), self.assertRaises((ValidationError, CredoCheckoutError)):
                self.prepare(**options)
        self.assertFalse(StockReservation.objects.exists())

    def test_another_guest_context_is_not_mistaken_for_the_same_checkout(self):
        first = self.prepare().application
        cart = Cart.objects.create(guest_token=uuid.uuid4())
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price_snapshot=Decimal("60.00"))
        second = self.prepare(cart=cart, idempotency_key=uuid.uuid4()).application
        self.assertNotEqual(first.reservation.guest_token, second.reservation.guest_token)
        self.assertEqual(CredoApplication.objects.count(), 2)

    def test_a_new_purchase_after_order_creation_is_not_blocked_by_funding_wait(self):
        apply_credo_observation(self.prepare().application.pk, 12)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1, unit_price_snapshot=Decimal("60.00"))
        next_purchase = self.prepare(idempotency_key=uuid.uuid4())
        self.assertTrue(next_purchase.created)
        self.assertEqual(CredoApplication.objects.count(), 2)

    def test_reservation_helper_cannot_reuse_the_last_unit_held_by_financing(self):
        Product.objects.filter(pk=self.product.pk).update(stock_qty=1)
        application = self.prepare().application
        with self.assertRaises(StockReservationError):
            create_stock_reservation_from_cart(cart=self.cart, guest_token=self.cart.guest_token)
        application.reservation.refresh_from_db()
        self.assertEqual(application.reservation.status, "active")
        self.assertEqual(StockReservation.objects.count(), 1)

    def test_unknown_bank_status_is_an_incident_and_keeps_the_hold(self):
        application = self.prepare().application
        unknown = apply_credo_observation(application.pk, 999)
        self.assertIsNone(unknown.bank_status)
        self.assertEqual(unknown.last_observed_status, 999)
        self.assertTrue(unknown.needs_review)
        later = apply_credo_observation(application.pk, 12)
        self.assertTrue(later.needs_review)
        self.assertIsNone(later.order_id)
        with self.assertRaises(CheckoutPaymentInProgress):
            self.prepare(idempotency_key=uuid.uuid4())

    def test_modified_hold_cannot_change_the_signed_purchase(self):
        application = self.prepare().application
        application.reservation.items.update(quantity=2)
        result = apply_credo_observation(application.pk, 12)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.last_issue, "credo_reservation_snapshot_mismatch")
        self.assertFalse(Order.objects.exists())

    def test_malformed_but_rehashed_snapshot_remains_reviewable_without_an_order(self):
        application = self.prepare().application
        snapshot = copy.deepcopy(application.checkout_snapshot)
        del snapshot["totals"]["delivery"]
        snapshot.pop("integrity_hash")
        snapshot["integrity_hash"] = snapshot_hash(snapshot)
        application.checkout_snapshot, application.snapshot_digest = snapshot, snapshot["integrity_hash"]
        application.save()
        result = apply_credo_observation(application.pk, 12)
        self.assertTrue(result.needs_review)
        self.assertEqual(result.last_issue, "credo_snapshot_invalid")
        self.assertFalse(Order.objects.exists())

    def test_account_erasure_failure_rolls_back_the_new_snapshot_erasure_too(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price_snapshot=Decimal("60.00"))
        application = self.prepare(cart=cart, user=self.user).application
        original = copy.deepcopy(application.checkout_snapshot)
        with patch.object(type(self.user), "delete", side_effect=RuntimeError("delete failed")):
            with self.assertRaises(RuntimeError):
                delete_user_account(self.user)
        application.refresh_from_db()
        self.assertEqual(application.checkout_snapshot, original)
        self.assertFalse(application.needs_review)

    def test_cart_changes_while_bank_is_open_leave_unpurchased_quantity_intact(self):
        application = self.prepare().application
        self.item.quantity = 3
        self.item.save(update_fields=["quantity"])
        result = apply_credo_observation(application.pk, 12)
        self.assertEqual(result.order.items.get().quantity, 1)
        self.assertEqual(self.cart.items.get().quantity, 2)
