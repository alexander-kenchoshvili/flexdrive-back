from contextlib import nullcontext
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase

from catalog.admin import ProductAdmin
from catalog.crossmotors_import import (
    build_crossmotors_report, fetch_crossmotors_stock,
    import_crossmotors_report, import_crossmotors_report_bulk,
)
from catalog.models import Category, Product, ProductStatus, SupplierProductBlock
from catalog.supplier_sync import crossmotors_sync_lock


def feed_item(code="000015", qty=9):
    return {
        "code": code, "oem": "OEM-15", "name": "Front lamp (RH)",
        "brand": "Subaru", "model": "XV", "generation": "XV 12-17",
        "manufacturer": "Suo Lun", "qty": qty, "dealer_price": 100,
        "currency": "GEL",
    }


class SupplierPublicationTests(TestCase):
    importer = staticmethod(import_crossmotors_report)

    def setUp(self):
        self.category = Category.objects.create(name="Test", slug="sync-test")

    def product(self, code, status=ProductStatus.PUBLISHED, **extra):
        return Product.objects.create(
            name=code, sku=f"CM-{code}", slug=f"sync-{code}",
            internal_sku=f"FD-01-{Product.objects.count() + 1:04d}",
            category=self.category, price=50, stock_qty=4, status=status, **extra,
        )

    def sync(self, items, **options):
        return self.importer(build_crossmotors_report(items), **options)

    def test_new_product_stays_draft_until_admin_publication(self):
        self.sync([feed_item()])
        product = Product.objects.get(sku="CM-000015")
        self.assertEqual(product.status, ProductStatus.DRAFT)
        self.sync([feed_item(qty=20)])
        product.refresh_from_db()
        self.assertEqual(product.status, ProductStatus.DRAFT)
        self.assertEqual(product.stock_qty, 20)
        product.internal_sku = "FD-01-0001"
        product.save(update_fields=["internal_sku"])
        ProductAdmin(Product, AdminSite()).action_publish(None, Product.objects.filter(pk=product.pk))
        self.sync([feed_item(qty=8)])
        product.refresh_from_db()
        self.assertEqual(product.status, ProductStatus.PUBLISHED)
        self.assertEqual(product.stock_qty, 8)

    def test_missing_archive_return_and_manual_hidden_states(self):
        missing = self.product("missing")
        draft = self.product("draft", ProductStatus.DRAFT)
        manual = self.product("manual", ProductStatus.ARCHIVED)
        zero = self.product("000015", markup_percent_override=25)
        result = self.sync([feed_item(qty=0)], archive_missing=True, max_missing_percent=100)
        missing.refresh_from_db()
        draft.refresh_from_db()
        zero.refresh_from_db()
        self.assertEqual(result.archived_missing_products, 1)
        self.assertEqual(missing.status, ProductStatus.ARCHIVED)
        self.assertTrue(missing.supplier_missing)
        self.assertEqual(draft.status, ProductStatus.DRAFT)
        self.assertEqual(zero.status, ProductStatus.PUBLISHED)
        self.assertEqual(zero.stock_qty, 0)
        self.assertEqual(zero.price, 125)
        self.sync([feed_item(c) for c in ("missing", "draft", "manual", "000015")])
        missing.refresh_from_db()
        draft.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(missing.status, ProductStatus.PUBLISHED)
        self.assertFalse(missing.supplier_missing)
        self.assertEqual(draft.status, ProductStatus.DRAFT)
        self.assertEqual(manual.status, ProductStatus.ARCHIVED)

    def test_blocked_product_cannot_return(self):
        product = self.product("000015", ProductStatus.ARCHIVED, supplier_missing=True)
        SupplierProductBlock.objects.create(source_name="Cross Motors", supplier_sku=product.sku)
        self.sync([feed_item()])
        product.refresh_from_db()
        self.assertEqual(product.status, ProductStatus.ARCHIVED)
        self.assertEqual(product.stock_qty, 4)

    def test_empty_duplicate_and_large_drop_abort_without_updates(self):
        product = self.product("000015")
        self.product("missing")
        for items in ([], [feed_item(), feed_item()], [feed_item()]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.sync(items, archive_missing=True)
            product.refresh_from_db()
            self.assertEqual(product.stock_qty, 4)
            self.assertEqual(Product.objects.filter(status=ProductStatus.PUBLISHED).count(), 2)

    def test_without_archive_missing_existing_missing_is_untouched(self):
        product = self.product("missing")
        self.sync([feed_item()])
        product.refresh_from_db()
        self.assertEqual(product.status, ProductStatus.PUBLISHED)

    def test_manual_draft_action_cancels_automatic_return(self):
        product = self.product("000015", ProductStatus.ARCHIVED, supplier_missing=True)
        ProductAdmin(Product, AdminSite()).action_unpublish(None, Product.objects.filter(pk=product.pk))
        self.sync([feed_item()])
        product.refresh_from_db()
        self.assertEqual(product.status, ProductStatus.DRAFT)
        self.assertFalse(product.supplier_missing)

    def test_cache_invalidation_after_successful_commit(self):
        with patch("catalog.crossmotors_import._invalidate_import_caches") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                self.sync([feed_item()])
            invalidate.assert_called_once()

    def test_validation_error_rolls_back_whole_import(self):
        product = self.product("000015")
        invalid = feed_item("bad")
        invalid["currency"] = "USD"
        with self.assertRaises(ValueError):
            self.sync([feed_item(), invalid], archive_missing=True)
        product.refresh_from_db()
        self.assertEqual(product.stock_qty, 4)
        self.assertEqual(Product.objects.count(), 1)

    def test_admin_status_edit_clears_automatic_archive_marker(self):
        product = self.product("000015", ProductStatus.ARCHIVED, supplier_missing=True)
        product.status = ProductStatus.DRAFT
        form = Mock(changed_data=["status"])
        ProductAdmin(Product, AdminSite()).save_model(None, product, form, True)
        product.refresh_from_db()
        self.assertFalse(product.supplier_missing)


class BulkSupplierPublicationTests(SupplierPublicationTests):
    importer = staticmethod(import_crossmotors_report_bulk)


class SupplierCommandTests(TestCase):
    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock")
    @patch("catalog.management.commands.import_crossmotors_products.crossmotors_sync_lock", side_effect=ValueError("Another import"))
    def test_lock_rejection_happens_before_fetch(self, lock, fetch):
        with self.assertRaises(CommandError):
            call_command("import_crossmotors_products", token="test", commit=True, stdout=StringIO())
        fetch.assert_not_called()

    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock")
    def test_dry_run_and_commit(self, fetch):
        fetch.return_value = ([feed_item()], {"page_sizes": [1]})
        call_command("import_crossmotors_products", token="test", archive_missing=True, stdout=StringIO())
        self.assertFalse(Product.objects.exists())
        call_command("import_crossmotors_products", token="test", archive_missing=True, bulk=True, commit=True, stdout=StringIO())
        self.assertEqual(Product.objects.get().status, ProductStatus.DRAFT)
        self.assertFalse(fetch.call_args.kwargs["in_stock_only"])

    @patch("catalog.management.commands.import_crossmotors_products.fetch_crossmotors_stock", side_effect=ValueError("API failure"))
    def test_failed_fetch_does_not_change_catalog(self, fetch):
        category = Category.objects.create(name="Keep", slug="keep")
        product = Product.objects.create(
            category=category, name="Keep", slug="keep", sku="CM-000015",
            internal_sku="FD-01-0001",
            price=50, stock_qty=4, status=ProductStatus.PUBLISHED,
        )
        with self.assertRaises(CommandError):
            call_command("import_crossmotors_products", token="test", commit=True, archive_missing=True, stdout=StringIO())
        product.refresh_from_db()
        self.assertEqual(product.status, ProductStatus.PUBLISHED)
        self.assertEqual(product.stock_qty, 4)


class SupplierFetchAndLockTests(SimpleTestCase):
    @patch("catalog.crossmotors_import.requests.get")
    def test_changed_snapshot_and_page_limit_fail(self, get):
        def response(timestamp, items):
            value = Mock(status_code=200)
            value.json.return_value = {"items": items, "synced_at": timestamp}
            return value
        get.side_effect = [response("a", [feed_item()]), response("b", [])]
        with self.assertRaisesMessage(ValueError, "snapshot changed"):
            fetch_crossmotors_stock(token="test", page_size=1)
        get.side_effect = [response("a", [feed_item()])]
        with self.assertRaisesMessage(ValueError, "Stopped after"):
            fetch_crossmotors_stock(token="test", page_size=1, max_pages=1)

    @patch("catalog.supplier_sync.transaction.atomic", return_value=nullcontext())
    @patch("catalog.supplier_sync.connection")
    def test_postgres_lock_rejects_overlap(self, db, atomic):
        db.vendor = "postgresql"
        cursor = db.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (False,)
        with self.assertRaisesMessage(ValueError, "Another Cross Motors import"):
            with crossmotors_sync_lock():
                self.fail("Overlapping import was allowed")
        cursor.execute.assert_called_once_with("SELECT pg_try_advisory_xact_lock(%s)", [627390221])

    @patch("catalog.supplier_sync.transaction.atomic", return_value=nullcontext())
    @patch("catalog.supplier_sync.connection")
    def test_postgres_lock_allows_owner(self, db, atomic):
        db.vendor = "postgresql"
        db.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
        with crossmotors_sync_lock():
            pass
