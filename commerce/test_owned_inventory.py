from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product, ProductStatus
from catalog.crossmotors_import import (
    _archive_missing_products, build_crossmotors_report,
    import_crossmotors_report, import_crossmotors_report_bulk,
)
from . import test_returns_foundation as foundation
from .accounting_reports import order_row
from .inventory import consume_order_inventory
from .models import (
    Order, OrderItem, OrderItemInventory, OrderStatus, OwnedStockLot,
    OwnedStockAllocation, ReturnDisposition, StockReservation, StockReservationItem, SupplierStockHold,
)
from .returns import prepare_order_return, receive_order_return
from .services import cancel_refunded_order_and_restore_stock, get_available_stock_quantity


class OwnedInventoryTests(TestCase):
    def setUp(self):
        foundation.ReturnFoundationTests.setUp(self)
        self.case = prepare_order_return(order=self.order, disposition=ReturnDisposition.ON_HAND, actor=self.actor)
        self.product.refresh_from_db()

    def sale(self, quantity=1, cost=Decimal("95")):
        order = Order.objects.create(
            order_number=f"SALE-{Order.objects.count()}", payment_status="paid", payment_method="card",
            subtotal=Decimal("150") * quantity, total=Decimal("150") * quantity,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name, sku=self.product.sku,
            internal_sku=self.product.internal_sku, quantity=quantity,
            unit_price=Decimal("150"), line_total=Decimal("150") * quantity,
            purchase_unit_gross=cost, purchase_cost_source="catalog_supplier_price" if cost is not None else "unavailable",
            purchase_cost_recorded_at=timezone.now(),
        )
        return order

    def report(self, qty):
        return build_crossmotors_report([{
            "code": "RETURN-1", "oem": "123", "name": "ფარი", "brand": "Subaru",
            "model": "XV", "generation": "XV 12-17", "manufacturer": "Suo Lun",
            "qty": qty, "dealer_price": 95.0, "currency": "GEL",
        }], synced_at=timezone.now().isoformat(), product_queryset=Product.objects.all())

    def test_single_owned_unit_visible_without_supplier_safety_reserve(self):
        Product.objects.filter(pk=self.product.pk).update(stock_qty=0, supplier_stock_qty=0, status="published")
        consume_order_inventory(order=self.sale())
        self.product.refresh_from_db()
        self.assertEqual(self.product.customer_available_stock_qty, 1)
        self.assertTrue(self.product.in_stock)
        response = self.client.get(reverse("catalog-product-list"), {"in_stock": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product.pk, [row["id"] for row in response.json()["results"]])
        response = self.client.get(reverse("catalog-product-list"), {"in_stock": "false"})
        self.assertNotIn(self.product.pk, [row["id"] for row in response.json()["results"]])

    def test_mixed_sale_consumes_own_first_and_only_holds_external_units(self):
        order = self.sale(3)
        consume_order_inventory(order=order)
        consume_order_inventory(order=order)
        record = order.items.get().inventory
        self.assertEqual(record.external_quantity, 1)
        self.assertEqual(record.purchase_total_gross, Decimal("255"))
        self.assertEqual(record.allocations.get().quantity, 2)
        self.assertEqual(order.items.get().supplier_stock_hold.quantity, 1)
        self.product.refresh_from_db()
        self.assertEqual((self.product.owned_stock_qty, self.product.stock_qty), (0, 11))
        amounts = order_row(order, tax_rates=lambda item: (Decimal(18), Decimal(18)))["lines"][0]["amounts"]
        self.assertEqual(amounts.purchase.gross, Decimal("255"))

    def test_owned_only_sale_does_not_create_supplier_hold(self):
        order = self.sale(2)
        consume_order_inventory(order=order)
        self.assertFalse(SupplierStockHold.objects.filter(order_item__order=order).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 12)

    def test_combined_checkout_reservation_blocks_last_owned_units_until_expiry(self):
        Product.objects.filter(pk=self.product.pk).update(stock_qty=0)
        self.product.refresh_from_db()
        reservation = StockReservation.objects.create(
            user=self.actor, source="cart", expires_at=timezone.now() + timedelta(minutes=10),
        )
        StockReservationItem.objects.create(
            reservation=reservation, product=self.product, quantity=2, unit_price_snapshot=Decimal("150"),
        )
        self.assertEqual(get_available_stock_quantity(product=self.product), 0)
        self.assertEqual(get_available_stock_quantity(product=self.product, exclude_reservation_ids=[reservation.pk]), 2)
        reservation.expires_at = timezone.now() - timedelta(seconds=1)
        reservation.save(update_fields=["expires_at"])
        self.assertEqual(get_available_stock_quantity(product=self.product), 2)

    def test_repeated_refund_restores_owned_and_external_sources_once(self):
        order = self.sale(3)
        consume_order_inventory(order=order)
        order.payment_status = "refunded"
        order.save(update_fields=["payment_status"])
        cancel_refunded_order_and_restore_stock(order)
        with self.assertRaises(ValidationError):
            cancel_refunded_order_and_restore_stock(order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 2)
        self.assertEqual(self.product.stock_qty, 12)  # supplier 14 minus original held 2
        self.assertEqual(OwnedStockAllocation.objects.filter(restored_at__isnull=False).count(), 1)

    def test_resale_then_return_keeps_original_cost_layers(self):
        order = self.sale(3)
        consume_order_inventory(order=order)
        order.status = OrderStatus.DELIVERED
        order.save(update_fields=["status"])
        case = prepare_order_return(order=order, disposition=ReturnDisposition.FROM_CUSTOMER, actor=self.actor)
        Product.objects.filter(pk=self.product.pk).update(supplier_price=Decimal("999"))
        line = case.lines.get()
        receive_order_return(return_case=case, inspection={line.pk: {"saleable": 3, "unsaleable": 0}}, actor=self.actor)
        lots = list(line.stock_lots.order_by("batch_number"))
        self.assertEqual([(lot.quantity, lot.purchase_unit_gross) for lot in lots], [(2, Decimal("80")), (1, Decimal("95"))])
        self.assertEqual(lots[0].source_lot_id, self.case.lines.get().stock_lots.get().pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 3)

    def test_unknown_owned_cost_does_not_turn_into_todays_supplier_price(self):
        # A new original sale with an unknown saved purchase price.
        unknown = self.sale(1, cost=None)
        prepare_order_return(order=unknown, disposition=ReturnDisposition.ON_HAND, actor=self.actor)
        order = self.sale(3)
        consume_order_inventory(order=order)
        self.assertIsNone(order.items.get().inventory.purchase_total_gross)
        amounts = order_row(order)["lines"][0]["amounts"]
        self.assertIsNone(amounts.purchase)

    def test_receipt_blocks_old_refund_route_before_bank_call(self):
        from .bog_refunds import can_request_bog_full_refund
        self.assertFalse(can_request_bog_full_refund(self.order))
        self.order.payment_status = "refunded"
        self.order.save(update_fields=["payment_status"])
        with self.assertRaises(ValidationError):
            cancel_refunded_order_and_restore_stock(self.order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 2)

    def test_supplier_imports_preserve_owned_balance(self):
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                importer(self.report(0))
                self.product.refresh_from_db()
                self.assertEqual(self.product.stock_qty, 0)
                self.assertEqual(self.product.owned_stock_qty, 2)
                self.assertEqual(self.product.customer_available_stock_qty, 2)

    def test_missing_supplier_keeps_owned_product_published_and_zeros_external(self):
        Product.objects.filter(pk=self.product.pk).update(status="published")
        report = build_crossmotors_report([], product_queryset=Product.objects.all())
        with transaction.atomic():
            _archive_missing_products(report)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, ProductStatus.PUBLISHED)
        self.assertEqual(self.product.customer_available_stock_qty, 2)
        self.assertEqual(self.product.supplier_stock_qty, 0)

    def test_stale_product_save_cannot_overwrite_owned_balance(self):
        stale = Product.objects.get(pk=self.product.pk)
        consume_order_inventory(order=self.sale())
        stale.name = "განახლებული ფარი"
        stale.save()
        stale.refresh_from_db()
        self.assertEqual(stale.owned_stock_qty, 1)

    def test_receipt_reopens_only_supplier_auto_archived_product(self):
        for supplier_missing, expected in [(True, "published"), (False, "archived")]:
            with self.subTest(supplier_missing=supplier_missing):
                Product.objects.filter(pk=self.product.pk).update(status="archived", supplier_missing=supplier_missing)
                prepare_order_return(order=self.sale(), disposition=ReturnDisposition.ON_HAND, actor=self.actor)
                self.product.refresh_from_db()
                self.assertEqual(self.product.status, expected)

    def test_mixed_cost_total_keeps_cents_without_rounding_unit_average(self):
        order = self.sale(3, cost=Decimal("95.01"))
        consume_order_inventory(order=order)
        amounts = order_row(order, tax_rates=lambda item: (Decimal(18), Decimal(18)))["lines"][0]["amounts"]
        self.assertEqual(amounts.purchase.gross, Decimal("255.01"))
        self.assertEqual(amounts.purchase.net, Decimal("216.11"))

    def test_overconsumption_rolls_back_without_negative_balance(self):
        Product.objects.filter(pk=self.product.pk).update(stock_qty=0)
        order = self.sale(3)
        with self.assertRaises(ValidationError):
            consume_order_inventory(order=order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 2)
        self.assertFalse(OrderItemInventory.objects.filter(order_item__order=order).exists())


@skipUnless(connection.vendor == "postgresql", "Row locking requires PostgreSQL")
class OwnedInventoryConcurrencyTests(TransactionTestCase):
    def test_two_sales_cannot_consume_the_last_owned_unit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections

        foundation.ReturnFoundationTests.setUp(self)
        self.item.quantity = 1
        self.item.save(update_fields=["quantity"])
        prepare_order_return(order=self.order, disposition=ReturnDisposition.ON_HAND, actor=self.actor)
        Product.objects.filter(pk=self.product.pk).update(stock_qty=0)
        orders = [OwnedInventoryTests.sale(self) for _ in range(2)]
        barrier = Barrier(2)

        def sell(pk):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                consume_order_inventory(order=Order.objects.get(pk=pk))
                return "sold"
            except ValidationError:
                return "unavailable"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(sell, [order.pk for order in orders]))
        self.assertCountEqual(results, ["sold", "unavailable"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 0)
        self.assertEqual(OwnedStockAllocation.objects.count(), 1)
