from io import BytesIO, StringIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .test_accounting_admin import AccountingAdminTests
from .models import Order, OrderItem


class AccountingExportTests(AccountingAdminTests):
    def test_private_buyer_details_and_text_ids_export_once_per_order(self):
        from .accounting_buyers import BUYER_COLUMNS
        Order.objects.filter(pk=self.order.pk).update(first_name="Nino <Buyer>", last_name="Beridze",
            personal_number="00000000001", city="თბილისი", address_line='=HYPERLINK("private")', phone="555000001")
        self.refund()
        self.client.force_login(self.superuser)
        params = {"status": "all", "end": "2026-10-31"}
        page = self.get(**params)
        self.assertContains(page, "Nino &lt;Buyer&gt;")
        self.assertNotContains(page, "Nino <Buyer>")
        self.assertContains(page, "00000000001")
        self.assertEqual(page.context["totals"][14], "0.00")
        response = self.get(export="xlsx", **params)
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet_id = next(sheet.get("sheetId") for sheet in book.findall("s:sheets/s:sheet", ns)
                            if sheet.get("name") == "მყიდველები")
            sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_id}.xml"))
            self.assertEqual(len(sheet.findall('.//s:row', ns)), 8)
            headers = [cell.find("s:is/s:t", ns).text for cell in sheet.findall('.//s:row[@r="7"]/s:c', ns)]
            self.assertEqual(headers, [label for _, label, _ in BUYER_COLUMNS])
            cells = sheet.findall('.//s:row[@r="8"]/s:c', ns)
            self.assertEqual(cells[6].get("t"), "inlineStr")
            self.assertEqual(cells[6].find("s:is/s:t", ns).text, "00000000001")
            styles = ET.fromstring(archive.read("xl/styles.xml"))
            self.assertEqual(styles.find("s:cellXfs", ns)[int(cells[6].get("s"))].get("numFmtId"), "49")
            self.assertEqual(cells[7].find("s:is/s:t", ns).text, 'თბილისი, =HYPERLINK("private")')
            self.assertEqual(sheet.find("s:autoFilter", ns).get("ref"), "A7:I8")
            self.assertFalse(sheet.findall(".//s:f", ns))
            self.assertNotEqual(cells[6].get("s"), "7")  # Last buyer is data, never a financial total.

    def test_legal_buyer_exports_contact_and_company_id_without_personal_number(self):
        Order.objects.filter(pk=self.order.pk).update(buyer_type="legal_entity", company_name="Test LLC",
            company_identification_code="012345678", personal_number="00000000001", first_name="Contact",
            last_name="Person", city="თბილისი", address_line="Street 1")
        self.client.force_login(self.superuser)
        page = self.get()
        self.assertContains(page, "Test LLC")
        self.assertContains(page, "012345678")
        self.assertNotContains(page, "00000000001")
        response = self.get(export="xlsx")
        with ZipFile(BytesIO(response.content)) as archive:
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet3.xml"))
            self.assertEqual(sheet.find('.//s:c[@r="D8"]/s:is/s:t', ns).text, "012345678")
            self.assertIsNone(sheet.find('.//s:c[@r="G8"]/s:is', ns))
        # An old individual order with no number remains reportable and printable.
        Order.objects.filter(pk=self.order.pk).update(buyer_type="individual", personal_number="")
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.get(export="xlsx").status_code, 200)

    def test_purchase_visibility_matches_html_and_export(self):
        from .accounting_ledger import HEADERS
        self.client.force_login(self.superuser)
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for enabled in (False, True):
            params = {"show_purchase": "on"} if enabled else {}
            page = self.get(**params)
            for header in (HEADERS[5], HEADERS[7]):
                self.assertEqual(header in page.context["product_headers"], enabled)
                if not enabled:
                    self.assertNotContains(page, header)
            self.assertEqual(HEADERS[7] in page.context["total_headers"], enabled)
            self.assertIn(HEADERS[9], page.context["product_headers"])
            self.assertIn(HEADERS[10], page.context["product_headers"])
            exported = self.client.get(self.url + page.context["export_url"])
            with ZipFile(BytesIO(exported.content)) as archive:
                sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                headers = [c.find("s:is/s:t", ns).text for c in sheet.findall('.//s:row[@r="7"]/s:c', ns)]
                values = sheet.findall('.//s:row[@r="8"]/s:c', ns)
                totals = sheet.findall('.//s:row[@r="9"]/s:c', ns)
                self.assertEqual(len(headers), 23 if enabled else 21)
                self.assertEqual(len(values), len(headers))
                self.assertEqual(len(totals), len(headers))
                for header in (HEADERS[5], HEADERS[7]):
                    self.assertEqual(header in headers, enabled)
                self.assertEqual(values[headers.index(HEADERS[10])].find("s:v", ns).text, "16.95")
                self.assertEqual(totals[headers.index(HEADERS[14])].find("s:v", ns).text, "45.00")

    def test_buyer_information_uses_saved_order_and_exports_for_refunds_too(self):
        self.client.force_login(self.superuser)
        self.refund()
        for buyer_type, vat, label in (("individual", None, "—"), ("legal_entity", True, "კი"),
                                       ("legal_entity", False, "არა"), ("legal_entity", None, "არ არის მითითებული")):
            Order.objects.filter(pk=self.order.pk).update(buyer_type=buyer_type, company_is_vat_registered=vat)
            params = {"status": "all", "end": "2026-10-31"}
            page = self.get(**params)
            for group in page.context["groups"]:
                self.assertEqual(group["buyer_vat"], label)
                self.assertEqual(group["is_company"], buyer_type == "legal_entity")
            exported = self.get(export="xlsx", **params)
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            with ZipFile(BytesIO(exported.content)) as archive:
                sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                for row in (8, 9):
                    self.assertEqual(sheet.find(f'.//s:c[@r="P{row}"]/s:is/s:t', ns).text, label)

    # Reuses established access/fixture behavior; only new tests run explicitly.
    def test_xlsx_filters_numeric_cells_and_safe_text(self):
        OrderItem.objects.filter(order=self.order).update(product_name='=HYPERLINK("bad")')
        self.client.force_login(self.superuser)
        response = self.get(show_purchase="on", export="xlsx")
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            self.assertEqual(len([n for n in archive.namelist() if n.startswith("xl/worksheets/")]), 3)
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertFalse(sheet.findall(".//s:f", ns))
            self.assertEqual(sheet.find('.//s:c[@r="K8"]/s:v', ns).text, "16.95")
            self.assertEqual(sheet.find('.//s:c[@r="O9"]/s:v', ns).text, "45.00")
            self.assertTrue(sheet.find('.//s:c[@r="C8"]/s:is/s:t', ns).text.startswith("=HYPERLINK"))
        empty = self.get(show_purchase="on", export="xlsx", status="refunded")
        with ZipFile(BytesIO(empty.content)) as archive:
            rows = ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).findall(".//s:row", ns)
            self.assertEqual(len(rows), 8)

    def test_export_staff_forbidden(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.get(show_purchase="on", export="xlsx").status_code, 403)

    def test_workbook_title_period_filter_freeze_and_total_styles(self):
        self.client.force_login(self.superuser)
        response = self.get(show_purchase="on", export="xlsx", sku="FD-01-0999")
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertIn("FlexDrive", sheet.find('.//s:c[@r="A1"]/s:is/s:t', ns).text)
            self.assertIn("01.09.2026 — 30.09.2026", sheet.find('.//s:c[@r="A2"]/s:is/s:t', ns).text)
            self.assertIn("FD-01-0999", sheet.find('.//s:c[@r="A3"]/s:is/s:t', ns).text)
            self.assertEqual(sheet.find("s:autoFilter", ns).get("ref"), "A7:W8")
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
        response = self.get(show_purchase="on", export="xlsx", period_mode="months", start_month="2026-09", end_month="2026-10",
                            status="all", sku="FD-01-0999")
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(sheet.find('.//s:c[@r="K9"]/s:v', ns).text, "-16.95")
            self.assertEqual(sheet.find('.//s:c[@r="K10"]/s:v', ns).text, "0.00")
            self.assertEqual(sheet.find('.//s:c[@r="P8"]/s:is/s:t', ns).text, "გადახდილი")
            self.assertIsNone(sheet.find('.//s:c[@r="X7"]', ns))
            self.assertIsNone(sheet.find('.//s:c[@r="O10"]/s:v', ns))
            self.assertEqual(len(sheet.findall('.//s:row', ns)), 10)


class AccountingDemoTests(TestCase):
    def test_remote_demo_requires_explicit_staging_and_exact_database(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from commerce.management.commands.accounting_demo import STAGING_HOST
        for host, name, staging in [(STAGING_HOST, 'neondb', False),
                                     ('production.example.invalid', 'neondb', True),
                                     (STAGING_HOST, 'other_database', True)]:
            remote = SimpleNamespace(vendor='postgresql', settings_dict={'HOST': host, 'NAME': name})
            with patch('commerce.management.commands.accounting_demo.connection', remote):
                with self.assertRaises(CommandError):
                    call_command('accounting_demo', staging=staging, stdout=StringIO())
        self.assertEqual(Order.objects.count(), 0)

    def test_explicit_staging_can_seed_and_clean_marked_examples(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from commerce.management.commands.accounting_demo import STAGING_HOST
        remote = SimpleNamespace(vendor='postgresql', settings_dict={'HOST': STAGING_HOST, 'NAME': 'neondb'})
        with patch('commerce.management.commands.accounting_demo.connection', remote):
            call_command('accounting_demo', staging=True, stdout=StringIO())
            self.assertEqual(Order.objects.count(), 36)
            call_command('accounting_demo', staging=True, delete=True, stdout=StringIO())
            self.assertEqual(Order.objects.count(), 0)

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
