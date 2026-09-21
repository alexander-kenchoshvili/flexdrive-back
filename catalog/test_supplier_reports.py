from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, SupplierSyncReport
from catalog.supplier_reports import create_success_report, DETAIL_LIMIT
from catalog.test_supplier_sync import feed_item


class SupplierReportTests(TestCase):
    def run_import(self, **kwargs):
        call_command("import_crossmotors_products", token="test", sample_size=0, stdout=StringIO(), **kwargs)

    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock")
    def test_dry_run_no_history_success_and_no_change_history(self, fetch):
        fetch.return_value = ([feed_item()], {})
        self.run_import()
        self.assertFalse(SupplierSyncReport.objects.exists())
        for bulk in (True, False):
            self.run_import(commit=True, bulk=bulk)
        reports = list(SupplierSyncReport.objects.order_by("pk"))
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0].changes["new"]["count"], 1)
        self.assertTrue(all(group["count"] == 0 for group in reports[1].changes.values()))

    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock", side_effect=ValueError("secret-api-token"))
    def test_failure_persisted_without_raw_error_or_credentials(self, fetch):
        with self.assertRaises(CommandError):
            self.run_import(commit=True)
        report = SupplierSyncReport.objects.get()
        self.assertEqual(report.status, "failed")
        self.assertNotIn("secret-api-token", report.summary)
        self.assertFalse(Product.objects.exists())

    @patch("catalog.management.commands.import_crossmotors_products.create_success_report", side_effect=ValueError("report failure"))
    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock")
    def test_transaction_rollback_still_records_failure(self, fetch, save):
        fetch.return_value = ([feed_item()], {})
        with self.assertRaises(CommandError):
            self.run_import(commit=True, bulk=True)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(SupplierSyncReport.objects.get().status, "failed")

    def test_meaningful_changes_only_and_bounded_details(self):
        def row(sku, qty=10, status="published", price="100"):
            return dict(sku=sku, name="Part", stock_qty=qty, status=status, supplier_price=Decimal(price))
        before = {key: row(key) for key in ("out", "small", "archive", "price")}
        before["back"] = row("back", qty=5)
        before["restore"] = row("restore", status="archived")
        before["draft"] = row("draft", status="draft")
        after = {key: dict(value) for key, value in before.items()}
        after["out"]["stock_qty"] = 5  # Sellable reserve threshold, not raw zero.
        after["small"]["stock_qty"] = 8
        after["archive"]["status"] = "archived"
        after["price"]["supplier_price"] = Decimal("110")
        after["back"]["stock_qty"] = 6
        after["restore"]["status"] = "published"
        after["draft"]["stock_qty"] = 0
        for i in range(DETAIL_LIMIT + 3):
            after[f"new{i}"] = row(f"new{i}", status="draft")
        report = create_success_report(started_at=timezone.now(), before=before, after=after)
        for key in ("out_of_stock", "back_in_stock", "archived", "restored", "supplier_price"):
            self.assertEqual(report.changes[key]["count"], 1)
        self.assertEqual(report.changes["new"]["count"], DETAIL_LIMIT + 3)
        self.assertEqual(len(report.changes["new"]["items"]), DETAIL_LIMIT)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SupplierReportAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="reports-admin", email="reports@example.test", password="test-pass",
        )
        self.client.force_login(self.user)
        category = Category.objects.create(name="Parts", slug="report-parts")
        self.product = Product.objects.create(name="Keep", sku="CM-keep", slug="keep", category=category, price=10)
        self.reports = [create_success_report(started_at=timezone.now(), before={}, after={}) for _ in range(3)]
        self.url = reverse("admin:catalog_suppliersyncreport_changelist")

    def test_bulk_delete_selected_then_all_does_not_delete_products(self):
        response = self.client.get(self.url)
        self.assertContains(response, "delete_selected")
        selected = self.reports[0]
        response = self.client.post(self.url, {"action": "delete_selected", "_selected_action": [selected.pk]})
        self.assertEqual(response.status_code, 200)  # Built-in confirmation page.
        self.assertEqual(SupplierSyncReport.objects.count(), 3)
        self.client.post(self.url, {"action": "delete_selected", "_selected_action": [selected.pk], "post": "yes"})
        self.assertEqual(SupplierSyncReport.objects.count(), 2)
        self.client.post(self.url, {
            "action": "delete_selected", "_selected_action": [self.reports[1].pk],
            "select_across": "1", "post": "yes",
        })
        self.assertFalse(SupplierSyncReport.objects.exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_read_only_detail_escapes_supplier_text_and_single_delete(self):
        report = self.reports[0]
        report.changes = {"new": {"count": 1, "items": [{"sku": "CM-1", "name": "<script>alert(1)</script>"}]}}
        report.save()
        response = self.client.get(reverse("admin:catalog_suppliersyncreport_change", args=[report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.get(reverse("admin:catalog_suppliersyncreport_add")).status_code, 403)
        response = self.client.post(reverse("admin:catalog_suppliersyncreport_delete", args=[report.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupplierSyncReport.objects.filter(pk=report.pk).exists())

    def test_staff_without_permissions_cannot_read_or_delete_reports(self):
        user = get_user_model().objects.create_user(username="limited", password="test-pass", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:catalog_suppliersyncreport_delete", args=[self.reports[0].pk]), {"post": "yes"}).status_code, 403)
        self.assertEqual(SupplierSyncReport.objects.count(), 3)
