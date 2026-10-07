from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from catalog.models import Category, Product, ProductSupplierSource
from .models import (
    Order, OrderItem, OrderPaymentMethod, OrderPaymentStatus, OrderReturn,
    OrderReturnLine, OrderStatus, OwnedStockLot, PaymentTransaction,
    ReturnDisposition, ReturnReceiptStatus,
)
from .returns import prepare_order_return, receive_order_return
from .supplier_stock import create_supplier_stock_holds_for_order


class ReturnFoundationTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(
            username="returns-staff", email="returns@example.test", is_staff=True,
        )
        self.category = Category.objects.create(name="ფარები", slug="return-lights")
        self.product = Product.objects.create(
            category=self.category, name="ფარი", sku="CM-RETURN-1",
            internal_sku="FD-01-9001", slug="return-light", price=Decimal("150"),
            supplier_price=Decimal("95"), stock_qty=12,
            supplier_source=ProductSupplierSource.CROSS_MOTORS, supplier_stock_qty=14,
        )
        self.order = Order.objects.create(
            order_number="RETURN-FOUNDATION-1", payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PAID, subtotal=Decimal("300"), total=Decimal("300"),
            first_name="Test", last_name="Customer", phone="555000000",
            city="თბილისი", address_line="სატესტო მისამართი",
        )
        self.cost_time = timezone.now()
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name="ფარი",
            sku=self.product.sku, internal_sku=self.product.internal_sku,
            quantity=2, unit_price=Decimal("150"), line_total=Decimal("300"),
            purchase_unit_gross=Decimal("80"), purchase_cost_source="catalog_supplier_price",
            purchase_cost_recorded_at=self.cost_time,
        )
        self.hold = create_supplier_stock_holds_for_order(order=self.order)[0]

    def prepare(self, disposition=ReturnDisposition.FROM_CUSTOMER):
        if disposition == ReturnDisposition.FROM_CUSTOMER:
            self.order.status = OrderStatus.DELIVERED
            self.order.save(update_fields=["status"])
        return prepare_order_return(order=self.order, disposition=disposition, actor=self.actor)

    def inspect(self, case, *, good=2, bad=0):
        return {line.pk: {"saleable": good, "unsaleable": bad} for line in case.lines.all()}

    def test_unpurchased_has_no_receipt_or_operational_side_effects(self):
        before_order = Order.objects.values().get(pk=self.order.pk)
        before_product = Product.objects.values().get(pk=self.product.pk)
        before_hold = type(self.hold).objects.values().get(pk=self.hold.pk)
        with patch("commerce.bog_payments.BogPaymentsClient.from_settings") as bank:
            case = self.prepare(ReturnDisposition.NOT_PURCHASED)
        self.assertEqual(case.receipt_status, ReturnReceiptStatus.NOT_REQUIRED)
        self.assertIsNone(case.received_at)
        self.assertEqual(case.lines.get().expected_quantity, 2)
        self.assertFalse(OwnedStockLot.objects.exists())
        self.assertFalse(PaymentTransaction.objects.exists())
        bank.assert_not_called()
        self.assertEqual(before_order, Order.objects.values().get(pk=self.order.pk))
        self.assertEqual(before_product, Product.objects.values().get(pk=self.product.pk))
        self.assertEqual(before_hold, type(self.hold).objects.values().get(pk=self.hold.pk))

    def test_on_hand_creates_receipt_directly_once_with_historical_cost(self):
        case = self.prepare(ReturnDisposition.ON_HAND)
        replay = self.prepare(ReturnDisposition.ON_HAND)
        self.assertEqual(case.pk, replay.pk)
        self.assertEqual(case.receipt_status, ReturnReceiptStatus.RECEIVED)
        self.assertEqual(case.received_by, self.actor)
        lot = OwnedStockLot.objects.get()
        self.assertEqual(lot.quantity, 2)
        self.assertEqual(lot.purchase_unit_gross, Decimal("80"))
        self.assertEqual(lot.purchase_cost_recorded_at, self.cost_time)
        self.product.refresh_from_db()
        self.hold.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 12)
        self.assertTrue(self.hold.is_active)
        self.assertEqual(self.order.payment_status, OrderPaymentStatus.PAID)
        self.assertIsNone(self.order.stock_restored_at)

    def test_waiting_creates_no_lot_until_full_inspection(self):
        case = self.prepare()
        self.assertEqual(case.receipt_status, ReturnReceiptStatus.AWAITING)
        self.assertFalse(OwnedStockLot.objects.exists())
        result = receive_order_return(return_case=case, inspection=self.inspect(case, good=1, bad=1), actor=self.actor)
        self.assertEqual(result.receipt_status, ReturnReceiptStatus.RECEIVED)
        self.assertEqual(OwnedStockLot.objects.get().quantity, 1)
        line = result.lines.get()
        self.assertEqual((line.saleable_quantity, line.unsaleable_quantity), (1, 1))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)

    def test_entirely_unsaleable_receipt_creates_no_saleable_stock(self):
        case = self.prepare()
        receive_order_return(return_case=case, inspection=self.inspect(case, good=0, bad=2), actor=self.actor)
        self.assertFalse(OwnedStockLot.objects.exists())
        case.refresh_from_db()
        self.assertIsNotNone(case.received_at)

    def test_retry_preserves_original_actor_timestamp_and_quantity(self):
        case = self.prepare()
        inspection = self.inspect(case)
        first = receive_order_return(return_case=case, inspection=inspection, actor=self.actor)
        another = get_user_model().objects.create_user(
            username="other-staff", email="other@example.test", is_staff=True,
        )
        retry = receive_order_return(return_case=case, inspection=inspection, actor=another)
        self.assertEqual(retry.received_at, first.received_at)
        self.assertEqual(retry.received_by_id, self.actor.pk)
        self.assertEqual(OwnedStockLot.objects.count(), 1)
        with self.assertRaises(ValidationError):
            receive_order_return(return_case=case, inspection=self.inspect(case, good=1, bad=1), actor=another)
        self.assertEqual(OwnedStockLot.objects.get().quantity, 2)

    def test_invalid_inspection_cannot_create_partial_receipt(self):
        case = self.prepare()
        line_id = case.lines.get().pk
        invalid = [
            {}, {line_id: {"saleable": 1, "unsaleable": 0}},
            {line_id: {"saleable": 3, "unsaleable": 0}},
            {line_id: {"saleable": -1, "unsaleable": 3}},
            {line_id: {"saleable": True, "unsaleable": 1}},
            {line_id: {"saleable": 2.0, "unsaleable": 0}},
            {line_id: {"saleable": 2}},
        ]
        for inspection in invalid:
            with self.subTest(inspection=inspection), self.assertRaises(ValidationError):
                receive_order_return(return_case=case, inspection=inspection, actor=self.actor)
        case.refresh_from_db()
        self.assertEqual(case.receipt_status, ReturnReceiptStatus.AWAITING)
        self.assertIsNone(case.lines.get().inspected_at)
        self.assertFalse(OwnedStockLot.objects.exists())

    def test_second_product_failure_rolls_back_whole_receipt(self):
        OrderItem.objects.create(
            order=self.order, product=self.product, product_name="მეორე პროდუქტი",
            sku="other", quantity=1, unit_price=Decimal("1"), line_total=Decimal("1"),
        )
        case = self.prepare()
        inspection = {line.pk: {"saleable": line.expected_quantity, "unsaleable": 0} for line in case.lines.all()}
        from .returns import _create_receipt_lot
        calls = 0

        def fail_second(line):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValidationError("Simulated second receipt failure")
            _create_receipt_lot(line)

        with patch("commerce.returns._create_receipt_lot", side_effect=fail_second):
            with self.assertRaises(ValidationError):
                receive_order_return(return_case=case, inspection=inspection, actor=self.actor)
        self.assertFalse(OwnedStockLot.objects.exists())
        self.assertFalse(case.lines.filter(inspected_at__isnull=False).exists())
        case.refresh_from_db()
        self.assertEqual(case.receipt_status, ReturnReceiptStatus.AWAITING)

    def test_unknown_legacy_cost_stays_unknown(self):
        # Create a legacy item rather than modifying protected historical facts.
        order = Order.objects.create(
            order_number="LEGACY-RETURN", payment_status="paid",
            subtotal=Decimal("150"), total=Decimal("150"),
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name="ფარი", sku="legacy",
            quantity=1, unit_price=Decimal("150"), line_total=Decimal("150"),
        )
        prepare_order_return(order=order, disposition=ReturnDisposition.ON_HAND, actor=self.actor)
        lot = OwnedStockLot.objects.get()
        self.assertIsNone(lot.purchase_unit_gross)
        self.assertIsNone(lot.purchase_cost_recorded_at)

    def test_pre_dispatch_and_post_dispatch_paths_cannot_be_swapped(self):
        with self.assertRaises(ValidationError):
            prepare_order_return(order=self.order, disposition=ReturnDisposition.FROM_CUSTOMER, actor=self.actor)
        self.order.status = OrderStatus.SHIPPED
        self.order.save(update_fields=["status"])
        for disposition in [ReturnDisposition.ON_HAND, ReturnDisposition.NOT_PURCHASED]:
            with self.subTest(disposition=disposition), self.assertRaises(ValidationError):
                prepare_order_return(order=self.order, disposition=disposition, actor=self.actor)
        self.assertFalse(OrderReturn.objects.exists())

    def test_unpaid_and_restored_orders_rejected(self):
        self.order.payment_status = OrderPaymentStatus.PENDING
        self.order.save(update_fields=["payment_status"])
        with self.assertRaises(ValidationError):
            self.prepare(ReturnDisposition.ON_HAND)
        self.order.payment_status = OrderPaymentStatus.PAID
        self.order.stock_restored_at = timezone.now()
        self.order.save(update_fields=["payment_status", "stock_restored_at"])
        with self.assertRaises(ValidationError):
            self.prepare(ReturnDisposition.ON_HAND)

    def test_existing_disposition_cannot_be_reinterpreted(self):
        self.prepare(ReturnDisposition.NOT_PURCHASED)
        with self.assertRaises(ValidationError):
            self.prepare(ReturnDisposition.ON_HAND)
        self.assertFalse(OwnedStockLot.objects.exists())

    def test_staff_required(self):
        self.actor.is_staff = False
        with self.assertRaises(ValidationError):
            self.prepare(ReturnDisposition.ON_HAND)

    def test_database_rejects_duplicate_case_and_invalid_receipt_state(self):
        self.prepare(ReturnDisposition.ON_HAND)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderReturn.objects.create(order=self.order, disposition="not_purchased", receipt_status="not_required")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderReturn.objects.update(receipt_status="awaiting")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderReturnLine.objects.update(saleable_quantity=3)

    def test_receipt_cannot_exceed_line_even_using_another_batch(self):
        case = self.prepare(ReturnDisposition.ON_HAND)
        with self.assertRaises(ValidationError):
            OwnedStockLot.objects.create(return_line=case.lines.get(), batch_number=2, product=self.product, quantity=1)
        self.assertEqual(OwnedStockLot.objects.count(), 1)

    def test_inventory_history_cannot_be_edited_or_deleted(self):
        case = self.prepare(ReturnDisposition.ON_HAND)
        lot = OwnedStockLot.objects.get()
        lot.quantity = 3
        with self.assertRaises(ValidationError):
            lot.save()
        with self.assertRaises(ValidationError):
            OwnedStockLot.objects.update(quantity=3)
        for obj in [case, case.lines.get(), lot]:
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(ValidationError):
                    obj.delete()
                with self.assertRaises(ValidationError):
                    type(obj).objects.all().delete()
        with self.assertRaises(ProtectedError):
            self.product.delete()

    def test_new_models_are_not_exposed_as_editable_admin(self):
        for model in [OrderReturn, OwnedStockLot]:
            registered = admin.site._registry[model]
            self.assertFalse(registered.has_add_permission(None))
            self.assertFalse(registered.has_change_permission(None))
            self.assertFalse(registered.has_delete_permission(None))
        self.assertFalse(admin.site.is_registered(OrderReturnLine))
        self.assertEqual(OrderReturn._meta.verbose_name_plural, "დასაბრუნებელი ნივთები")
        self.assertEqual(OwnedStockLot._meta.verbose_name_plural, "FlexDrive-ის მარაგი")
