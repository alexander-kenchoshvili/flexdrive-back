from decimal import Decimal
from datetime import datetime, timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from catalog.models import Category, Product, ProductImage, SupplierSyncReport
from catalog.supplier_reports import create_success_report, DETAIL_LIMIT, supplier_snapshot
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

    def test_report_captures_internal_sku_at_sync_time(self):
        category = Category.objects.create(name="Parts", slug="snapshot-parts")
        product = Product.objects.create(
            name="Part", sku="CM-snapshot", internal_sku="FD-01-0123",
            slug="snapshot-part", category=category, price=10,
        )
        report = create_success_report(started_at=timezone.now(), before={}, after=supplier_snapshot())
        self.assertEqual(report.changes["new"]["items"][0]["internal_sku"], "FD-01-0123")
        product.internal_sku = None
        product.save(update_fields=["internal_sku"])
        report.refresh_from_db()
        self.assertEqual(report.changes["new"]["items"][0]["internal_sku"], "FD-01-0123")

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

    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock")
    def test_both_import_paths_report_restocks_without_images_once(self, fetch):
        category = Category.objects.create(name="Restock parts", slug="report-restock")
        product = Product.objects.create(
            name="Lamp", sku="CM-000015", internal_sku="FD-01-0123", slug="restock-lamp",
            category=category, price=150, supplier_price=100, status="published", stock_qty=5,
        )
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                Product.objects.filter(pk=product.pk).update(stock_qty=5)
                fetch.return_value = ([feed_item(qty=6)], {})
                self.run_import(commit=True, bulk=bulk)
                report = SupplierSyncReport.objects.latest("pk")
                group = report.changes["back_in_stock_without_image"]
                self.assertEqual(group["count"], 1)
                self.assertEqual(group["items"][0]["internal_sku"], "FD-01-0123")
                self.assertIn("მარაგში დაბრუნდა, სურათი არ აქვს: 1", report.summary)
                self.assertEqual(report.changes["back_in_stock"]["count"], 1)
                self.run_import(commit=True, bulk=bulk)
                self.assertEqual(SupplierSyncReport.objects.latest("pk").changes["back_in_stock_without_image"]["count"], 0)

    def test_snapshot_checks_all_image_variants_without_duplicate_products(self):
        category = Category.objects.create(name="Images", slug="report-images")
        products = []
        for index, field in enumerate(("image_original", "image_desktop", "image_tablet", "image_mobile", None)):
            product = Product.objects.create(
                name="Image part", sku=f"CM-image-{index}", slug=f"image-part-{index}",
                internal_sku=f"FD-01-{index + 1:04d}",
                category=category, price=100, supplier_price=50, status="published", stock_qty=5,
            )
            products.append(product)
            # Bulk insertion avoids actual image processing/file/network access.
            ProductImage.objects.bulk_create([
                ProductImage(product=product),
                ProductImage(product=product, **({field: "test/photo.webp"} if field else {})),
            ])
        with self.assertNumQueries(1):
            before = supplier_snapshot(lock=True)
        Product.objects.filter(pk__in=[p.pk for p in products]).update(stock_qty=6)
        after = supplier_snapshot()
        report = create_success_report(started_at=timezone.now(), before=before, after=after)
        group = report.changes["back_in_stock_without_image"]
        self.assertEqual(group["count"], 1)
        self.assertEqual(group["items"][0]["sku"], products[-1].sku)
        self.assertEqual(len(after), 5)

    def test_missing_photo_work_list_includes_restored_products_and_is_not_capped(self):
        def row(sku, *, status="published", qty=6):
            return dict(sku=sku, internal_sku=f"FD-01-{int(sku):04d}", name="No photo",
                        status=status, stock_qty=qty, supplier_price=Decimal("100"), has_image=False)
        before = {str(i): row(str(i), qty=5) for i in range(DETAIL_LIMIT + 3)}
        after = {str(i): row(str(i)) for i in range(DETAIL_LIMIT + 3)}
        # A supplier-archived product may retain its old raw stock count.
        before["0"] = row("0", status="archived")
        for sku, status in (("100", "draft"), ("101", "archived")):
            before[sku], after[sku] = row(sku, status=status, qty=0), row(sku, status=status)
        before["102"], after["102"] = row("102", qty=0), row("102", qty=5)
        report = create_success_report(started_at=timezone.now(), before=before, after=after)
        group = report.changes["back_in_stock_without_image"]
        self.assertEqual(group["count"], DETAIL_LIMIT + 3)
        self.assertEqual(len(group["items"]), DETAIL_LIMIT + 3)
        self.assertEqual(report.changes["restored"]["count"], 1)


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

    @override_settings(TIME_ZONE="UTC")
    def test_admin_uses_tbilisi_dates_without_changing_stored_times(self):
        report = self.reports[0]
        started_at = datetime(2026, 11, 15, 22, 1, tzinfo=datetime_timezone.utc)
        finished_at = datetime(2026, 11, 15, 22, 2, tzinfo=datetime_timezone.utc)
        SupplierSyncReport.objects.filter(pk=report.pk).update(
            started_at=started_at, finished_at=finished_at,
        )
        with timezone.override("Asia/Tbilisi"):
            expected_start = date_format(timezone.localtime(started_at), "DATETIME_FORMAT")
            expected_finish = date_format(timezone.localtime(finished_at), "DATETIME_FORMAT")
        with timezone.override("UTC"):
            response = self.client.get(self.url, {
                "started_at__year": "2026", "started_at__month": "11", "started_at__day": "16",
            })
            self.assertContains(response, expected_start)
            self.assertContains(response, expected_finish)
            self.assertIn(report.pk, [row.pk for row in response.context["cl"].result_list])
            response = self.client.get(reverse("admin:catalog_suppliersyncreport_change", args=[report.pk]))
            self.assertContains(response, expected_start)
            self.assertContains(response, expected_finish)
            self.assertContains(response, "2026-11-16 02:01")
            self.assertEqual(timezone.get_current_timezone_name(), "UTC")
        report.refresh_from_db()
        self.assertEqual(report.started_at, started_at)
        self.assertEqual(report.finished_at, finished_at)

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

    def test_detail_displays_saved_codes_and_legacy_fallback(self):
        self.product.internal_sku = "FD-01-0123"
        self.product.save(update_fields=["internal_sku"])
        report = self.reports[0]
        report.changes = {"new": {"count": 3, "items": [
            {"sku": "CM-saved", "internal_sku": "FD-02-0045", "name": "Saved"},
            {"sku": self.product.sku, "name": "Legacy"},
            {"sku": "CM-new", "internal_sku": "", "name": "New"},
        ]}}
        report.save()
        response = self.client.get(reverse("admin:catalog_suppliersyncreport_change", args=[report.pk]))
        self.assertContains(response, "CM-saved / FD-02-0045")
        self.assertContains(response, "CM-keep / FD-01-0123")
        self.assertContains(response, "<strong>CM-new</strong>", html=True)

    def test_detail_shows_full_photo_work_list_and_legacy_truncation_notice(self):
        report = self.reports[0]
        items = [{"sku": f"CM-photo-{i}", "internal_sku": f"FD-01-{i:04d}", "name": "No photo"}
                 for i in range(DETAIL_LIMIT + 3)]
        report.changes = {"back_in_stock_without_image": {"count": len(items), "items": items}}
        report.save()
        url = reverse("admin:catalog_suppliersyncreport_change", args=[report.pk])
        response = self.client.get(url)
        self.assertContains(response, "მარაგში დაბრუნდა, სურათი არ აქვს")
        self.assertContains(response, f"FD-01-{DETAIL_LIMIT + 2:04d}")
        self.assertNotContains(response, "ნაჩვენებია პირველი")
        report.changes = {"back_in_stock": {"count": len(items), "items": items[:DETAIL_LIMIT]}}
        report.save()
        self.assertContains(self.client.get(url), f"ნაჩვენებია პირველი {DETAIL_LIMIT} პროდუქტი.")
