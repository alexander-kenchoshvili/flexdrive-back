from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.crossmotors_import import (
    build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk,
)
from catalog.internal_skus import import_sku_pairs, read_sku_pairs
from catalog.models import Category, Product


def workbook(rows, *, formula=False):
    result = BytesIO()
    with ZipFile(result, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Parts" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        data = [("SKU / კოდი", "ჩვენი კოდი"), *rows]
        xml_rows = []
        for number, values in enumerate(data, 1):
            cells = []
            for column, value in zip(("B", "C"), values):
                f = '<f>"FD-001"</f>' if formula and number == 2 and column == "C" else ""
                cells.append(f'<c r="{column}{number}" t="inlineStr">{f}<is><t>{escape(value)}</t></is></c>')
            xml_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + '</sheetData></worksheet>')
    result.seek(0)
    return result


class InternalSkuTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="SKU parts", slug="sku-parts")
        self.product = Product.objects.create(
            category=category, name="Headlight", sku="CM-000015", slug="sku-headlight",
            price=100, stock_qty=8, status="draft",
        )
        self.other = Product.objects.create(
            category=category, name="Other", sku="CM-000016", slug="sku-other", price=50,
        )

    def test_dry_run_and_idempotent_import_only_change_internal_code(self):
        before = Product.objects.filter(pk=self.product.pk).values().get()
        pairs = {self.product.sku: "FD-03-0001"}
        self.assertEqual(import_sku_pairs(pairs)["would_update"], 1)
        self.assertEqual(Product.objects.filter(pk=self.product.pk).values().get(), before)
        self.assertEqual(import_sku_pairs(pairs, commit=True)["updated"], 1)
        self.assertEqual(import_sku_pairs(pairs, commit=True)["updated"], 0)
        after = Product.objects.filter(pk=self.product.pk).values().get()
        self.assertEqual(after.pop("internal_sku"), "FD-03-0001")
        before.pop("internal_sku")
        self.assertEqual(before, after)

    def test_invalid_batch_never_partially_updates(self):
        for pairs in (
            {self.product.sku: "FD-001", "CM-MISSING": "FD-002"},
            {self.product.sku: "FD-001", self.other.sku: "FD-001"},
            {self.product.sku: self.other.sku},
            {self.product.sku: "FD-001", self.other.sku: "bad code"},
        ):
            with self.subTest(pairs=pairs), self.assertRaises((ValueError, ValidationError)):
                import_sku_pairs(pairs, commit=True)
            self.product.refresh_from_db()
            self.assertIsNone(self.product.internal_sku)

    def test_existing_assignment_cannot_be_overwritten_or_stolen(self):
        import_sku_pairs({self.product.sku: "FD-001"}, commit=True)
        for pairs in ({self.product.sku: "FD-002"}, {self.other.sku: "FD-001"}):
            with self.assertRaises(ValueError):
                import_sku_pairs(pairs, commit=True)

    def test_database_enforces_unique_internal_codes(self):
        self.product.internal_sku = "FD-001"
        self.product.save(update_fields=["internal_sku"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=self.other.pk).update(internal_sku="FD-001")

    def test_workbook_rejects_duplicate_missing_and_formula_codes(self):
        self.assertEqual(read_sku_pairs(workbook([("CM-000015", "FD-001")])), {"CM-000015": "FD-001"})
        for rows, formula in (
            ([("CM-000015", "FD-001"), ("CM-000015", "FD-002")], False),
            ([("CM-000015", "FD-001"), ("CM-000016", "fd-001")], False),
            ([("CM-000015", "")], False),
            ([("CM-000015", "FD-001")], True),
        ):
            with self.assertRaises(ValueError):
                read_sku_pairs(workbook(rows, formula=formula))

    def test_command_is_dry_by_default(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.xlsx"
            path.write_bytes(workbook([("CM-000015", "FD-001")]).getvalue())
            call_command("import_internal_skus", input=str(path), stdout=StringIO())
            self.product.refresh_from_db()
            self.assertIsNone(self.product.internal_sku)
            call_command("import_internal_skus", input=str(path), commit=True, stdout=StringIO())
            self.product.refresh_from_db()
            self.assertEqual(self.product.internal_sku, "FD-001")

    def test_catalog_only_exposes_and_searches_internal_code(self):
        import_sku_pairs({self.product.sku: "FD-03-0001"}, commit=True)
        Product.objects.filter(pk=self.product.pk).update(status="published")
        client = APIClient()
        detail = client.get(reverse("catalog-product-detail", args=[self.product.slug]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["sku"], "FD-03-0001")
        self.assertEqual(detail.data["display_sku"], "FD-03-0001")
        for query in ("FD-03-0001", "fd-03-0001"):
            for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
                response = client.get(reverse(endpoint), {"q": query})
                self.assertEqual(response.status_code, 200)
                rows = response.data["results"] if isinstance(response.data, dict) else response.data
                self.assertEqual(rows[0]["id"], self.product.pk)
                self.assertEqual(rows[0]["display_sku"], "FD-03-0001")
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            response = client.get(reverse(endpoint), {"q": self.product.sku})
            rows = response.data["results"] if isinstance(response.data, dict) else response.data
            self.assertEqual(len(rows), 0)

    def test_unassigned_product_never_displays_supplier_code(self):
        self.assertEqual(self.product.display_sku, "")

    def test_both_supplier_import_paths_preserve_internal_code(self):
        import_sku_pairs({self.product.sku: "FD-03-0001"}, commit=True)
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                report = build_crossmotors_report([{
                    "code": "000015", "name": "წინა ფარი (RH)", "oem": "OEM-1",
                    "brand": "Subaru", "model": "XV", "generation": "XV 12-17",
                    "manufacturer": "Suo Lun", "qty": 6, "dealer_price": 250, "currency": "GEL",
                }])
                importer(report)
                self.product.refresh_from_db()
                self.assertEqual(self.product.internal_sku, "FD-03-0001")
                self.assertEqual(self.product.sku, "CM-000015")
                self.assertEqual(self.product.stock_qty, 6)
