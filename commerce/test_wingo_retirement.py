"""Retirement cannot silently discard existing courier shipment history."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from .models import WingoShipment


class RetiredCourierMigrationTests(TransactionTestCase):
    def test_guard_blocks_old_shipments_then_removes_only_retired_tables_and_permissions(self):
        name = str(connection.settings_dict["NAME"])
        assert connection.vendor == "sqlite" and (name == ":memory:" or (name.startswith("file:memorydb_") and "mode=memory" in name))
        old_shipments = None
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([("commerce", "0044_wingo_platform_returns")])
            apps = executor.loader.project_state([("commerce", "0044_wingo_platform_returns")]).apps
            order = apps.get_model("commerce", "Order").objects.create(order_number="RETIREMENT-WINGO", subtotal=100, total=110)
            shipment = apps.get_model("commerce", "WingoShipment").objects.create(order=order, state="created",
                provider_order_id="keep-provider-id", tracking_number="999-KEEP", submitted_at=timezone.now(),
                booked_price=10, carrier_status=9, request_payload={"supplierOrderId": order.order_number},
                tracking_history=[{"status": 9, "result": "synced"}])
            before = WingoShipment.objects.values().get(pk=shipment.pk)
            old_shipments = apps.get_model("commerce", "RedcapShipment")
            old = old_shipments.objects.create(order=order, state="unknown", service_slug="same_day")
            with self.assertRaisesMessage(RuntimeError, "Old courier shipments exist"):
                MigrationExecutor(connection).migrate([("commerce", "0045_remove_retired_courier")])
            self.assertTrue(old_shipments.objects.filter(pk=old.pk).exists())
            self.assertIn("commerce_redcapshipment", connection.introspection.table_names())
            old_shipments.objects.all().delete()
            ContentType = apps.get_model("contenttypes", "ContentType")
            old_type = ContentType.objects.create(app_label="commerce", model="redcapshipment")
            Permission = apps.get_model("auth", "Permission")
            Permission.objects.create(content_type=old_type, codename="view_redcapshipment", name="Retired permission")
            MigrationExecutor(connection).migrate([("commerce", "0045_remove_retired_courier")])
            tables = connection.introspection.table_names()
            for table in ("commerce_redcapshipment", "commerce_redcapreferencedata", "commerce_redcapsyncreport"):
                self.assertNotIn(table, tables)
            self.assertFalse(ContentType.objects.filter(pk=old_type.pk).exists())
            self.assertFalse(Permission.objects.filter(codename="view_redcapshipment").exists())
            self.assertEqual(WingoShipment.objects.values().get(pk=shipment.pk), before)
        finally:
            if old_shipments is not None and "commerce_redcapshipment" in connection.introspection.table_names():
                old_shipments.objects.all().delete()
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
