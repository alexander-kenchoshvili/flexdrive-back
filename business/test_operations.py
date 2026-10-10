from datetime import datetime, timedelta, timezone as utc
from decimal import Decimal as D
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Category, Product, SupplierSyncReport
from commerce.models import (
    EasywaySyncReport, Order, OrderItem, OrderItemInventory, OrderReturn, OrderReturnLine,
    OwnedStockAllocation, OwnedStockLot, PaymentTransaction, StockReservation,
)
from .operations import build_operations_report

NOW = datetime(2026, 10, 9, 9, tzinfo=utc.utc)


class OperationsTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="ფარები", slug="ops-lights")
        self.product = Product.objects.create(name="ფარი", sku="PRIVATE-SUPPLIER", internal_sku="FD-01-9001",
                                               category=self.category, slug="ops-light", price=D(118), stock_qty=100)
        self.sequence = 0

    def case(self, state="awaiting", quantity=2, cost="59"):
        self.sequence += 1
        order = Order.objects.create(order_number=f"OPS-{self.sequence}", subtotal=D(118) * quantity, total=D(118) * quantity,
                                     payment_status="paid", phone="PRIVATE-PHONE", address_line="PRIVATE-ADDRESS")
        item = OrderItem.objects.create(order=order, product=self.product, product_name=self.product.name,
                                        internal_sku=self.product.internal_sku, sku="PRIVATE-SUPPLIER", unit_price=D(118),
                                        quantity=quantity, line_total=D(118) * quantity, purchase_unit_gross=D(cost) if cost else None)
        case = OrderReturn.objects.create(order=order, disposition="not_purchased" if state == "not_required" else "from_customer",
                                          receipt_status=state, received_at=NOW - timedelta(days=10) if state == "received" else None)
        line = OrderReturnLine.objects.create(return_case=case, order_item=item, expected_quantity=quantity,
                                              saleable_quantity=quantity if state == "received" else 0,
                                              inspected_at=case.received_at)
        return case, line

    def lot(self, quantity=5, cost="59"):
        _, line = self.case("received", quantity, cost)
        return OwnedStockLot.objects.create(return_line=line, product=self.product, quantity=quantity,
                                            purchase_unit_gross=D(cost) if cost else None)

    def payment(self, status="pending", action="sale", issue="", currency="GEL"):
        case, _ = self.case()
        return PaymentTransaction.objects.create(order=case.order, status=status, action=action, amount=D(118),
                                                  currency=currency, reconciliation_issue=issue,
                                                  error_message="PRIVATE-BANK-ERROR", provider_reference={"token": "PRIVATE-TOKEN"})

    def report(self, options=None):
        with patch("business.operations.timezone.now", return_value=NOW):
            return build_operations_report(options)

    def test_empty_snapshot_has_real_zeros_and_no_invented_sync_success(self):
        report = self.report()
        self.assertEqual(report["returns"]["summary"]["awaiting"], 0)
        self.assertEqual(report["stock"]["summary"]["value_gross"], "0.00")
        self.assertEqual(report["payments"]["summary"]["attention"], 0)
        self.assertTrue(all(sync["latest"] is None and sync["last_success_at"] is None for sync in report["syncs"]))

    def test_returns_keep_receipt_and_payment_separate_and_include_old_waiting_cases(self):
        waiting, _ = self.case()
        OrderReturn.objects.filter(pk=waiting.pk).update(created_at=NOW - timedelta(days=100))
        self.case("received", 3)
        self.case("not_required", 4)
        report = self.report()
        self.assertEqual(report["returns"]["summary"], {"awaiting": 1, "received": 1, "not_required": 1, "awaiting_units": 2})
        row = report["returns"]["items"][0]
        self.assertEqual(row["waiting_days"], 100)
        self.assertEqual(row["receipt_status"], "awaiting")
        self.assertEqual(row["payment_label"], "გადახდილია")
        received = self.report({"returns": "received"})["returns"]["items"][0]
        self.assertEqual(received["saleable_units"], 3)
        self.assertEqual(received["unsaleable_units"], 0)
        self.assertEqual(self.report({"returns": "not_required"})["returns"]["total"], 1)
        self.assertEqual(self.report({"returns": "all"})["returns"]["total"], 3)

    def test_pagination_does_not_truncate_summary_and_clamps_missing_pages(self):
        for _ in range(21):
            self.case()
        report = self.report()
        self.assertEqual(report["returns"]["summary"]["awaiting"], 21)
        self.assertEqual(report["returns"]["summary"]["awaiting_units"], 42)
        self.assertEqual(len(report["returns"]["items"]), 20)
        last = self.report({"returns_page": 999})["returns"]
        self.assertEqual(last["total"], 21)
        self.assertEqual(last["page"], 2)
        self.assertEqual(len(last["items"]), 1)

    def test_lot_balance_ignores_restored_allocations_and_keeps_unknown_cost(self):
        lot = self.lot()
        _, line = self.case(quantity=3)
        inventory = OrderItemInventory.objects.create(order_item=line.order_item, external_quantity=0, external_source="", purchase_total_gross=D(177))
        OwnedStockAllocation.objects.create(lot=lot, inventory=inventory, quantity=3)
        _, another = self.case(quantity=1)
        restored = OrderItemInventory.objects.create(order_item=another.order_item, external_quantity=0, external_source="", purchase_total_gross=D(59))
        OwnedStockAllocation.objects.create(lot=lot, inventory=restored, quantity=1, restored_at=NOW)
        self.lot(quantity=2, cost=None)
        report = self.report()["stock"]
        self.assertEqual(report["summary"]["units"], 4)
        self.assertEqual(report["summary"]["products"], 1)
        self.assertEqual(report["summary"]["known_value_gross"], "118.00")
        self.assertEqual(report["summary"]["unknown_cost_units"], 2)
        self.assertIsNone(report["summary"]["value_gross"])
        self.assertEqual(next(row for row in report["items"] if row["id"] == lot.pk)["remaining_units"], 2)

    def test_lot_cost_is_historical_and_age_uses_tbilisi_receipt_date(self):
        lot = self.lot(quantity=2)
        # Change timestamps only in the disposable test database.
        with connection.cursor() as cursor:
            cursor.execute("UPDATE commerce_ownedstocklot SET created_at = %s WHERE id = %s", ["2026-10-08 20:00:00", lot.pk])
        Product.objects.filter(pk=self.product.pk).update(supplier_price=D(999))
        row = self.report()["stock"]["items"][0]
        self.assertEqual(row["age_days"], 0)
        self.assertEqual(row["value_gross"], "118.00")
        self.assertEqual(row["unit_cost_gross"], "59.00")

    def test_negative_lot_balance_is_flagged_not_valued_as_a_valid_total(self):
        lot = self.lot(quantity=1)
        _, line = self.case(quantity=2)
        inventory = OrderItemInventory.objects.create(order_item=line.order_item, external_quantity=0, external_source="", purchase_total_gross=D(118))
        OwnedStockAllocation.objects.create(lot=lot, inventory=inventory, quantity=2)
        summary = self.report()["stock"]["summary"]
        self.assertEqual(summary["invalid_lots"], 1)
        self.assertIsNone(summary["value_gross"])

    def test_payment_filters_count_attempts_not_lost_orders_and_preserve_currency(self):
        for status in ("pending", "authorized", "refund_pending", "failed", "cancelled", "paid"):
            self.payment(status)
        monitored = self.payment("paid", issue="bank_request_failed", currency="USD")
        report = self.report()["payments"]
        self.assertEqual(report["summary"], {"pending": 3, "failed": 1, "issues": 1, "attention": 5})
        self.assertEqual(self.report({"payments": "pending"})["payments"]["total"], 3)
        self.assertEqual(self.report({"payments": "failed"})["payments"]["total"], 1)
        row = self.report({"payments": "issues"})["payments"]["items"][0]
        self.assertEqual(row["id"], monitored.pk)
        self.assertEqual(row["currency"], "USD")
        self.assertIsNone(row["checked_at"])

    def test_paid_without_order_is_visible_without_exposing_checkout_snapshot(self):
        reservation = StockReservation.objects.create(guest_token=uuid4(), expires_at=NOW + timedelta(days=1))
        payment = PaymentTransaction.objects.create(reservation=reservation, status="paid", action="sale", amount=D(118),
                                                    checkout_snapshot={"email": "PRIVATE-EMAIL"})
        report = self.report()["payments"]
        self.assertEqual(report["summary"]["issues"], 1)
        self.assertEqual(report["items"][0]["id"], payment.pk)
        self.assertIsNone(report["items"][0]["order_number"])
        self.assertIn("შეკვეთა", report["items"][0]["issue"])
        self.assertNotIn("PRIVATE-EMAIL", str(report))

    def test_sync_last_failed_and_prior_success_are_distinct_and_payload_is_sanitized(self):
        SupplierSyncReport.objects.create(started_at=NOW - timedelta(days=2), finished_at=NOW - timedelta(days=2), status="success", summary="PRIVATE-TOKEN", changes={"new": {"count": 2, "items": [{"sku": "PRIVATE-SUPPLIER"}]}})
        SupplierSyncReport.objects.create(started_at=NOW - timedelta(days=1), finished_at=NOW - timedelta(days=1), status="failed", summary="PRIVATE-TOKEN", changes={"new": {"count": "unknown"}, "archived": {"count": True}})
        EasywaySyncReport.objects.create(started_at=NOW, finished_at=NOW, status="review", source="scheduled", summary="PRIVATE-TOKEN", details={"counts": {"checked": 4, "changed": 1, "review": 1, "failed": 0, "skipped": 2}, "run_error": "PRIVATE-TOKEN"})
        report = self.report()
        supplier, carrier = report["syncs"]
        self.assertEqual(supplier["latest"]["status"], "failed")
        self.assertEqual(supplier["last_success_at"], (NOW - timedelta(days=2)).isoformat())
        self.assertTrue(all(row["value"] is None for row in supplier["latest"]["counts"]))
        self.assertEqual(carrier["latest"]["counts"][0]["value"], 4)
        self.assertIsNone(carrier["last_success_at"])
        self.assertNotIn("PRIVATE", str(report))

    def test_snapshot_only_selects_with_bounded_queries_no_sockets_and_no_sensitive_details(self):
        self.lot()
        self.payment("failed", issue="unknown-private-value")

        def read_only(execute, sql, params, many, context):
            self.assertEqual(sql.lstrip().split()[0].upper(), "SELECT")
            return execute(sql, params, many, context)

        with connection.execute_wrapper(read_only), CaptureQueriesContext(connection) as queries, \
                patch("socket.create_connection", side_effect=AssertionError("outbound connection")), \
                patch("socket.socket.connect", side_effect=AssertionError("outbound connection")), \
                patch("socket.getaddrinfo", side_effect=AssertionError("outbound DNS")):
            report = self.report({"returns": "all"})
        self.assertLessEqual(len(queries), 17)
        self.assertNotIn("PRIVATE", str(report))
        self.assertNotIn("unknown-private-value", str(report))

    def test_endpoint_is_permission_checked_read_only_no_store_and_validates_filters(self):
        caches["throttling"].clear()
        client = APIClient()
        url = reverse("business:operations")
        self.assertEqual(client.get(url).status_code, 401)
        owner = get_user_model().objects.create_superuser("ops-owner", "ops@example.test", "Ops-test-password")
        with patch("business.views.validate_recaptcha", return_value=True):
            client.post(reverse("business:login"), {"username": owner.username, "password": "Ops-test-password", "recaptcha_token": "test"}, format="json")
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        for query in ({"returns": "bad"}, {"payments": "bad"}, {"stock_page": 0}, {"returns_page": "oops"}, {"payments_page": 1000001}):
            self.assertEqual(client.get(url, query).status_code, 400)
        self.assertEqual(client.post(url, {}, format="json").status_code, 405)
        owner.is_superuser = False
        owner.save(update_fields=["is_superuser"])
        self.assertEqual(client.get(url).status_code, 403)
