"""The actual accountant ledger, HTML and XLSX use frozen RedCap order amounts."""

from datetime import date, datetime, timezone
from decimal import Decimal as D
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .accounting_ledger import build_ledger
from .accounting_reports import ReportPeriod
from .models import Order, OrderItem, PaymentTransaction


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class RedcapAccountingTests(TestCase):
    def setUp(self):
        self.period = ReportPeriod(date(2026, 11, 1), date(2026, 11, 30))
        self.params = {"start": "2026-11-01", "end": "2026-11-30"}
        self.url = reverse("accounting-report")
        self.user = get_user_model().objects.create_superuser("redcap-accounting", "accounting@example.test", "Test-only-123")
        self.client.force_login(self.user)

    def sale(self, number="RC-ACC-1", *, city="თბილისი", carrier="10", provider="redcap", margin="0"):
        delivery = D(carrier) + D(margin) if provider != "internal" else D(5)
        order = Order.objects.create(order_number=number, city=city, subtotal=200,
            total=D(200) + delivery, delivery_provider=provider, delivery_price=delivery,
            carrier_delivery_cost=D(carrier) if provider != "internal" else 0,
            delivery_margin=D(margin), payment_status="paid", payment_method="card")
        for index in (1, 2):
            OrderItem.objects.create(order=order, product_name=f"Part {index}", sku=f"PRIVATE-{index}",
                internal_sku=f"FD-03-000{index}", unit_price=100, quantity=1, line_total=100,
                purchase_unit_gross=40, purchase_cost_source="catalog_supplier_price")
        payment = PaymentTransaction.objects.create(order=order, provider="bog", action="sale", status="paid",
            amount=order.total, captured_at=datetime(2026, 11, 3, 10, tzinfo=timezone.utc))
        return order, payment

    def test_tbilisi_and_region_count_carrier_fee_once_per_order_without_http(self):
        self.sale()
        self.sale("RC-ACC-2", city="ბათუმი", carrier="12")
        with patch("commerce.redcap.RedcapClient.from_settings", side_effect=AssertionError("Accounting must stay local")):
            report = build_ledger(self.period, "paid")
        self.assertEqual([row[12] for row in report["rows"]], [D(10), None, D(12), None])
        self.assertEqual(report["totals"][11:15], [D(0), D(22), D(0), D(422)])
        self.assertEqual([group["delivery_provider"] for group in report["groups"]], ["redcap", "redcap"])

    def test_html_names_redcap_and_does_not_display_a_second_tbilisi_charge(self):
        self.sale()
        response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["groups"][0]["delivery"], [
            ("ჩექაუთის საკურიერო ტარიფი", "10.00"), ("ბუფერი", "0.00"), ("შეკვეთის სრული თანხა", "210.00"),
            ("RedCap-ის ფასი — საინფორმაციო", "—"), ("ფასთა სხვაობა", "—")])
        self.assertNotContains(response, "რეგიონის მიტანა")
        self.assertNotContains(response, "თბილისის მიტანა")
        self.assertContains(response, "ჩექაუთის საკურიერო ტარიფი ₾")
        self.assertIn("no-store", response["Cache-Control"])

    def test_xlsx_has_same_fee_once_and_general_courier_header(self):
        self.sale()
        response = self.client.get(self.url, {**self.params, "export": "xlsx"})
        self.assertEqual(response.status_code, 200)
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(response.content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        headers = [cell.find("s:is/s:t", ns).text for cell in sheet.findall('.//s:row[@r="7"]/s:c', ns)]
        column = headers.index("ჩექაუთის საკურიერო ტარიფი ₾")
        self.assertNotIn("რეგიონის მიტანა ₾", headers)
        values = []
        for row in (8, 9, 10):
            cell = sheet.findall(f'.//s:row[@r="{row}"]/s:c', ns)[column]
            value = cell.find("s:v", ns)
            values.append(None if value is None else D(value.text))
        self.assertEqual(values, [D(10), None, D(10)])

    def test_full_refund_uses_saved_delivery_and_net_report_cancels_it_once(self):
        order, sale = self.sale()
        PaymentTransaction.objects.create(order=order, provider="bog", action="refund", status="refunded",
            amount=order.total, refunded_at=datetime(2026, 11, 4, 10, tzinfo=timezone.utc),
            provider_reference={"refund_request": {"sale_payment_id": sale.pk}})
        Order.objects.filter(pk=order.pk).update(payment_status="refunded")
        self.assertEqual(build_ledger(self.period, "paid")["rows"], [])
        refunded = build_ledger(self.period, "refunded")
        self.assertEqual(refunded["totals"][12:15], [D(10), D(0), D(210)])
        combined = build_ledger(self.period, "all")
        self.assertEqual([row[12] for row in combined["rows"]], [D(10), None, D(-10), None])
        self.assertEqual(combined["totals"][11:15], [D(0), D(0), D(0), D(0)])

    def test_legacy_internal_and_easyway_amounts_remain_readable(self):
        self.sale(provider="internal")
        self.sale("LEGACY-EW", provider="easyway", carrier="12", margin="2")
        report = build_ledger(self.period, "paid")
        self.assertEqual(report["totals"][11:15], [D(5), D(12), D(2), D(419)])

    def test_product_search_does_not_allocate_order_delivery_to_one_product(self):
        self.sale()
        report = build_ledger(self.period, "paid", sku="FD-03-0001")
        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0][11:15], [None] * 4)
        self.assertEqual(report["totals"][11:15], [None] * 4)
