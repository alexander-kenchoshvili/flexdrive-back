from io import StringIO
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .admin import ProductAdmin
from .crossmotors_import import (
    build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk,
)
from .models import Category, Product, ProductSpec, SupplierSyncReport
from .supplier_reports import DETAIL_LIMIT, create_success_report, supplier_snapshot
from .test_supplier_sync import feed_item


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class OemAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("oem-admin", "oem@example.test", "password")
        self.client.force_login(self.user)
        self.category = Category.objects.create(name="Parts", slug="parts")
        self.product = Product.objects.create(
            category=self.category, name="Part", sku="CM-000015", slug="part",
            price=10, supplier_price=10, manufacturer_part_number="OLD",
        )
        self.spec = ProductSpec.objects.create(product=self.product, key="OEM", value="OLD", sort_order=1)
        self.url = reverse("admin:catalog_product_change", args=[self.product.pk])

    def data(self, product=None, **changes):
        product = product or self.product
        data = {
            "name": product.name, "sku": product.sku, "slug": product.slug,
            "category": product.category_id, "status": product.status,
            "supplier_price": str(product.supplier_price), "price": str(product.price),
            "markup_percent_override": "0", "side": product.side,
            "stock_qty": product.stock_qty,
            "manufacturer_part_number": product.manufacturer_part_number,
        }
        for prefix in ("images", "fitments", "supplier_stock_holds"):
            data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
        data.update({
            "specs-TOTAL_FORMS": "1", "specs-INITIAL_FORMS": "1",
            "specs-0-id": self.spec.pk or "", "specs-0-product": self.product.pk,
            "specs-0-key": "OEM", "specs-0-value": self.spec.value, "specs-0-sort_order": "1",
        })
        data.update(changes)
        return data

    def save(self, **changes):
        response = self.client.post(self.url, self.data(**changes))
        self.assertEqual(response.status_code, 302, response.context and response.context["adminform"].form.errors)
        self.product.refresh_from_db()
        return response

    def assert_oem(self, value):
        self.assertEqual(self.product.manufacturer_part_number, value)
        self.assertTrue(self.product.preserve_manual_oem)
        values = list(self.product.specs.filter(key="OEM").values_list("value", flat=True))
        self.assertEqual(values, [value] if value else [])

    def test_upper_field_edit_syncs_spec_and_protects_without_checkbox(self):
        self.save(manufacturer_part_number="MANUAL")
        self.assert_oem("MANUAL")
        response = self.client.get(self.url)
        self.assertContains(response, "field-preserve_manual_oem")
        self.assertNotContains(response, 'name="preserve_manual_oem"')
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            item = feed_item(qty=20)
            item["oem"] = "SUPPLIER"
            importer(build_crossmotors_report([item]))
            self.product.refresh_from_db()
            self.assert_oem("MANUAL")
            self.assertEqual(self.product.stock_qty, 20)

    def test_top_field_edit_creates_missing_oem_spec(self):
        self.spec.delete()
        response = self.client.post(self.url, self.data(
            manufacturer_part_number="ADDED",
            **{"specs-TOTAL_FORMS": "0", "specs-INITIAL_FORMS": "0"},
        ))
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assert_oem("ADDED")

    def test_inline_edit_syncs_upper_field_and_protects(self):
        self.save(**{"specs-0-value": "INLINE"})
        self.assert_oem("INLINE")

    def test_both_fields_same_edit_is_accepted(self):
        self.save(manufacturer_part_number="SAME", **{"specs-0-value": "SAME"})
        self.assert_oem("SAME")

    def test_conflicting_edits_are_rejected_without_writes(self):
        response = self.client.post(self.url, self.data(
            manufacturer_part_number="TOP", **{"specs-0-value": "INLINE"}
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manufacturer part number და OEM სპეციფიკაცია ერთნაირი უნდა იყოს.")
        self.product.refresh_from_db()
        self.spec.refresh_from_db()
        self.assertEqual(self.product.manufacturer_part_number, "OLD")
        self.assertFalse(self.product.preserve_manual_oem)
        self.assertEqual(self.spec.value, "OLD")

    def test_unrelated_save_does_not_enable_protection(self):
        self.save(name="New name")
        self.assertFalse(self.product.preserve_manual_oem)
        self.assertEqual(self.product.manufacturer_part_number, "OLD")

    def test_clearing_upper_field_removes_spec_and_preserves_manual_empty_value(self):
        self.save(manufacturer_part_number="")
        self.assert_oem("")

    def test_deleting_inline_clears_upper_field_and_protects(self):
        self.save(**{"specs-0-DELETE": "on"})
        self.assert_oem("")

    def test_adding_oem_inline_to_blank_product_syncs_and_protects(self):
        self.spec.delete()
        self.product.manufacturer_part_number = ""
        self.product.save(update_fields=["manufacturer_part_number"])
        response = self.client.post(self.url, self.data(**{
            "specs-INITIAL_FORMS": "0", "specs-0-id": "", "specs-0-key": "oem",
            "specs-0-value": "ADDED",
        }))
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assert_oem("ADDED")

    def test_inline_oem_over_part_number_limit_is_rejected(self):
        response = self.client.post(self.url, self.data(**{"specs-0-value": "X" * 121}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OEM უნდა შეიცავდეს მაქსიმუმ 120 სიმბოლოს.")
        self.product.refresh_from_db()
        self.assertEqual(self.product.manufacturer_part_number, "OLD")

    def test_stale_unrelated_save_retains_latest_oem_and_protection(self):
        admin = ProductAdmin(Product, AdminSite())
        request = RequestFactory().post("/")
        request.user = self.user
        form = admin.get_form(request, self.product)(data=self.data(), instance=self.product)
        self.assertTrue(form.is_valid(), form.errors)
        Product.objects.filter(pk=self.product.pk).update(
            manufacturer_part_number="LATEST", preserve_manual_oem=True,
        )
        obj = form.save(commit=False)
        admin.save_model(request, obj, form, True)
        admin.save_related(request, form, [], True)
        self.product.refresh_from_db()
        self.assert_oem("LATEST")


class OemImportTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Parts", slug="parts")

    def product(self, **extra):
        return Product.objects.create(
            category=self.category, sku="CM-000015", slug="part", name="Part",
            price=10, supplier_price=10, stock_qty=1, **extra,
        )

    def sync(self, importer, oem):
        item = feed_item(qty=20)
        item["oem"] = oem
        return importer(build_crossmotors_report([item]))

    def test_manual_oem_and_manual_empty_survive_both_import_paths(self):
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            for value in ("MANUAL", ""):
                with self.subTest(importer=importer.__name__, value=value):
                    product = self.product(manufacturer_part_number=value, preserve_manual_oem=True)
                    self.sync(importer, "SUPPLIER")
                    product.refresh_from_db()
                    self.assertEqual(product.manufacturer_part_number, value)
                    self.assertTrue(product.preserve_manual_oem)
                    self.assertEqual(product.stock_qty, 20)
                    self.assertEqual(str(product.supplier_price), "100.00")
                    self.assertEqual(list(product.specs.filter(key="OEM").values_list("value", flat=True)), [value] if value else [])
                    product.delete()

    def test_unprotected_oem_add_change_and_clear_sync_both_fields(self):
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                product = self.product()
                for value in ("ADDED", "CHANGED", ""):
                    self.sync(importer, value)
                    product.refresh_from_db()
                    self.assertEqual(product.manufacturer_part_number, value)
                    self.assertFalse(product.preserve_manual_oem)
                    self.assertEqual(list(product.specs.filter(key="OEM").values_list("value", flat=True)), [value] if value else [])
                product.delete()

    def test_legacy_content_lock_preserves_other_specs_while_oem_follows_canonical_value(self):
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                product = self.product(preserve_manual_fitment_content=True)
                spec = ProductSpec.objects.create(product=product, key="მხარე", value="ჩემი მხარე")
                self.sync(importer, "SUPPLIER")
                spec.refresh_from_db()
                self.assertEqual(spec.value, "ჩემი მხარე")
                self.assertEqual(product.specs.get(key="OEM").value, "SUPPLIER")
                product.delete()

    def test_oem_spec_sync_is_bounded_for_bulk_import(self):
        from .oem import sync_oem_specs
        products = [Product.objects.create(
            category=self.category, sku=f"OEM-{i}", slug=f"part-{i}", name="Part", price=10,
            manufacturer_part_number=f"CODE-{i}",
        ) for i in range(30)]
        with CaptureQueriesContext(connection) as queries:
            sync_oem_specs(products)
        self.assertLessEqual(len(queries), 3)
        self.assertEqual(ProductSpec.objects.filter(product__in=products, key="OEM").count(), 30)


class OemReportTests(TestCase):
    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock")
    def test_committed_report_records_real_oem_changes_for_both_paths(self, fetch):
        category = Category.objects.create(name="Parts", slug="parts")
        product = Product.objects.create(category=category, sku="CM-000015", slug="part", name="Part", price=10)
        for bulk in (False, True):
            for value, key in (("ADDED", "oem_added"), ("CHANGED", "oem_changed"), ("", "oem_removed")):
                with self.subTest(bulk=bulk, key=key):
                    item = feed_item()
                    item["oem"] = value
                    fetch.return_value = ([item], {})
                    call_command("import_crossmotors_products", token="test", sample_size=0,
                                 commit=True, bulk=bulk, stdout=StringIO())
                    report = SupplierSyncReport.objects.latest("pk")
                    self.assertEqual(report.changes[key]["count"], 1)
                    self.assertEqual(report.changes[key]["items"][0]["after"], value or "—")
            Product.objects.filter(pk=product.pk).update(preserve_manual_oem=True, manufacturer_part_number="MANUAL")
            fetch.return_value = ([feed_item()], {})
            call_command("import_crossmotors_products", token="test", sample_size=0,
                         commit=True, bulk=bulk, stdout=StringIO())
            report = SupplierSyncReport.objects.latest("pk")
            self.assertTrue(all(report.changes[key]["count"] == 0 for key in ("oem_added", "oem_changed", "oem_removed")))
            Product.objects.filter(pk=product.pk).update(preserve_manual_oem=False, manufacturer_part_number="")

    def test_oem_reports_are_bounded_and_do_not_double_count_new_products(self):
        category = Category.objects.create(name="Parts", slug="parts")
        for i in range(DETAIL_LIMIT + 2):
            Product.objects.create(category=category, sku=f"CM-{i}", slug=f"part-{i}", name="Part", price=10)
        before = supplier_snapshot()
        Product.objects.update(manufacturer_part_number="OEM-CODE")
        Product.objects.create(category=category, sku="CM-new", slug="new", name="New", price=10, manufacturer_part_number="NEW")
        after = supplier_snapshot()
        from django.utils import timezone
        report = create_success_report(started_at=timezone.now(), before=before, after=after)
        self.assertEqual(report.changes["oem_added"]["count"], DETAIL_LIMIT + 2)
        self.assertEqual(len(report.changes["oem_added"]["items"]), DETAIL_LIMIT)
        self.assertEqual(report.changes["new"]["count"], 1)

    def test_oem_report_admin_displays_old_new_values_without_currency_and_escapes_text(self):
        from django.utils import timezone
        from .admin import SupplierSyncReportAdmin
        report = SupplierSyncReport.objects.create(started_at=timezone.now(), finished_at=timezone.now(), status="success", changes={
            "oem_changed": {"count": 1, "items": [{"sku": "CM-1", "internal_sku": "FD-01-0001",
                "name": "Part", "before": "<script>old</script>", "after": "NEW"}]},
            "supplier_price": {"count": 1, "items": [{"sku": "CM-1", "internal_sku": "FD-01-0001",
                "name": "Part", "before": "10", "after": "20"}]},
        })
        html = str(SupplierSyncReportAdmin(SupplierSyncReport, AdminSite()).change_details(report))
        self.assertIn("OEM შეიცვალა", html)
        self.assertIn("&lt;script&gt;old&lt;/script&gt; → NEW)", html)
        self.assertNotIn("NEW GEL", html)
        self.assertIn("10 → 20 GEL", html)
