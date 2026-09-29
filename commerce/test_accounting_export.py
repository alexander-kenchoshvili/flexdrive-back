from io import BytesIO, StringIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .test_accounting_admin import AccountingAdminTests
from .models import Order, OrderItem


class AccountingExportTests(AccountingAdminTests):
    # Reuses established access/fixture behavior; only new tests run explicitly.
    def test_xlsx_filters_numeric_cells_and_safe_text(self):
        OrderItem.objects.filter(order=self.order).update(product_name='=HYPERLINK("bad")')
        self.client.force_login(self.superuser)
        response = self.get(export="xlsx")
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            self.assertEqual(len([n for n in archive.namelist() if n.startswith("xl/worksheets/")]), 1)
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertFalse(sheet.findall(".//s:f", ns))
            self.assertEqual(sheet.find('.//s:c[@r="K8"]/s:v', ns).text, "16.95")
            self.assertEqual(sheet.find('.//s:c[@r="O9"]/s:v', ns).text, "45.00")
            self.assertTrue(sheet.find('.//s:c[@r="C8"]/s:is/s:t', ns).text.startswith("=HYPERLINK"))
        empty = self.get(export="xlsx", status="refunded")
        with ZipFile(BytesIO(empty.content)) as archive:
            rows = ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).findall(".//s:row", ns)
            self.assertEqual(len(rows), 8)

    def test_export_staff_forbidden(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.get(export="xlsx").status_code, 403)

    def test_workbook_title_period_filter_freeze_and_total_styles(self):
        self.client.force_login(self.superuser)
        response = self.get(export="xlsx", sku="FD-01-0999")
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertIn("FlexDrive", sheet.find('.//s:c[@r="A1"]/s:is/s:t', ns).text)
            self.assertIn("01.09.2026 — 30.09.2026", sheet.find('.//s:c[@r="A2"]/s:is/s:t', ns).text)
            self.assertIn("FD-01-0999", sheet.find('.//s:c[@r="A3"]/s:is/s:t', ns).text)
            self.assertEqual(sheet.find("s:autoFilter", ns).get("ref"), "A7:P8")
            self.assertEqual(sheet.find(".//s:pane", ns).get("topLeftCell"), "E8")
            self.assertEqual(sheet.find('.//s:c[@r="K9"]', ns).get("s"), "8")
            self.assertEqual(sheet.find("s:pageSetup", ns).get("orientation"), "landscape")
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            self.assertIn("$1:$7", book.find('.//s:definedName[@name="_xlnm.Print_Titles"]', ns).text)

    def test_banding_changes_between_orders_not_between_products(self):
        from decimal import Decimal
        from .accounting_export import workbook_bytes
        data = workbook_bytes([("Test", ["A", "B"], [["first", Decimal(1)], ["second", Decimal(2)],
                                                    ["third", Decimal(3)], ["total", Decimal(6)]])],
                              introduction=["Title"], bands=[0, 0, 1])
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(data)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(sheet.find('.//s:c[@r="B8"]', ns).get("s"), "2")
            self.assertEqual(sheet.find('.//s:c[@r="B9"]', ns).get("s"), "2")
            self.assertEqual(sheet.find('.//s:c[@r="B10"]', ns).get("s"), "6")
            self.assertEqual(sheet.find('.//s:c[@r="B11"]', ns).get("s"), "8")

    def test_export_all_months_sku_without_percentage(self):
        self.refund()
        self.client.force_login(self.superuser)
        response = self.get(export="xlsx", period_mode="months", start_month="2026-09", end_month="2026-10",
                            status="all", sku="FD-01-0999")
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(sheet.find('.//s:c[@r="K9"]/s:v', ns).text, "-16.95")
            self.assertEqual(sheet.find('.//s:c[@r="K10"]/s:v', ns).text, "0.00")
            self.assertEqual(sheet.find('.//s:c[@r="P8"]/s:is/s:t', ns).text, "გადახდილი")
            self.assertIsNone(sheet.find('.//s:c[@r="Q7"]', ns))
            self.assertIsNone(sheet.find('.//s:c[@r="O10"]/s:v', ns))
            self.assertEqual(len(sheet.findall('.//s:row', ns)), 10)


class AccountingDemoTests(TestCase):
    def test_create_duplicate_guard_and_safe_cleanup(self):
        real = Order.objects.create(order_number="KEEP-REAL", subtotal=0, total=0)
        out = StringIO()
        call_command("accounting_demo", stdout=out)
        self.assertEqual(Order.objects.count(), 37)
        self.assertEqual(OrderItem.objects.count(), 72)
        self.assertEqual(OrderItem.objects.values("internal_sku").distinct().count(), 72)
        with self.assertRaises(CommandError):
            call_command("accounting_demo", stdout=out)
        call_command("accounting_demo", delete=True, stdout=out)
        self.assertEqual(list(Order.objects.values_list("pk", flat=True)), [real.pk])
