from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class InventoryMigrationTests(TransactionTestCase):
    def test_new_balance_comes_only_from_receipts_and_preserves_external_stock(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        prior = [("catalog", "0026_individual_product_pricing"), ("commerce", "0035_return_inventory_foundation")]
        try:
            executor.migrate(prior)
            apps = executor.loader.project_state(prior).apps
            category = apps.get_model("catalog", "Category").objects.create(name="Migration", slug="migration-inventory")
            product = apps.get_model("catalog", "Product").objects.create(
                category=category, name="ფარი", slug="migration-light", sku="CM-MIGRATION",
                price=Decimal("150"), stock_qty=17, supplier_stock_qty=19,
                supplier_source="cross_motors",
            )
            order = apps.get_model("commerce", "Order").objects.create(
                order_number="MIGRATION-INVENTORY", subtotal=Decimal("450"), total=Decimal("450"),
            )
            item = apps.get_model("commerce", "OrderItem").objects.create(
                order=order, product=product, product_name="ფარი", sku="CM-MIGRATION",
                quantity=3, unit_price=Decimal("150"), line_total=Decimal("450"),
            )
            case = apps.get_model("commerce", "OrderReturn").objects.create(
                order=order, disposition="on_hand", receipt_status="received", received_at=timezone.now(),
            )
            line = apps.get_model("commerce", "OrderReturnLine").objects.create(
                return_case=case, order_item=item, expected_quantity=3, saleable_quantity=3, inspected_at=timezone.now(),
            )
            apps.get_model("commerce", "OwnedStockLot").objects.create(
                return_line=line, product=product, quantity=3, purchase_unit_gross=Decimal("80"),
            )
            before = apps.get_model("catalog", "Product").objects.values().get(pk=product.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after_apps = executor.loader.project_state(latest).apps
            after = after_apps.get_model("catalog", "Product").objects.values().get(pk=product.pk)
            self.assertEqual(after.pop("owned_stock_qty"), 3)
            self.assertEqual(after, before)
            self.assertFalse(after_apps.get_model("commerce", "OrderItemInventory").objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
