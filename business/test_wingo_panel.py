"""Cross-report Wingo money and operations regressions, with no live providers."""
from datetime import date, datetime, timezone as utc
from decimal import Decimal as D
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from commerce import test_partial_refunds as fixtures
from commerce.accounting_export import export_response
from commerce.accounting_ledger import build_ledger
from commerce.accounting_reports import ReportPeriod, build_cash_report
from commerce.bog_payments import BogResponseError, BogTransportError
from commerce.models import Order, OrderItem, OrderReturn, PaymentTransaction, WingoShipment
from commerce.refund_terms import build_settlement
from commerce.return_costs import return_cost_report
from commerce.courier_reporting import booking_report, shipment_report
from commerce.test_courier_fixtures import create_shipment
from .operations import build_operations_report
from .reports import build_dashboard_report


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=utc.utc)


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class WingoBusinessPanelTests(TestCase):
    _details = fixtures.PartialRefundTests._details
    request = fixtures.PartialRefundTests.request
    confirm = fixtures.PartialRefundTests.confirm

    def setUp(self):
        fixtures.PartialRefundTests.setUp(self)
        self.september = ReportPeriod(date(2026, 9, 1), date(2026, 9, 30))
        self.october = ReportPeriod(date(2026, 10, 1), date(2026, 10, 31))
        OrderReturn.objects.filter(pk=self.case.pk).update(received_at=stamp("2026-09-18T10:00"))
        PaymentTransaction.objects.filter(pk=self.sale.pk).update(captured_at=stamp("2026-09-01T10:00"))

    def paid_order(self, number, *, state=None, price=D(12), when="2026-09-15T10:00", buffer=D(0)):
        order = Order.objects.create(order_number=number, delivery_provider="wingo", payment_status="paid",
            payment_method="card", subtotal=100, total=112+buffer, delivery_price=12+buffer,
            carrier_delivery_cost=12, delivery_margin=buffer, phone="PRIVATE-PHONE", address_line="PRIVATE-ADDRESS")
        OrderItem.objects.create(order=order, product=self.product, product_name="სატესტო ნაწილი", internal_sku=number,
            sku="PRIVATE-SUPPLIER", unit_price=100, quantity=1, line_total=100, purchase_unit_gross=60)
        PaymentTransaction.objects.create(order=order, provider="bog", action="sale", status="paid", amount=order.total,
            captured_at=stamp("2026-09-01T10:00"))
        if state:
            create_shipment(order=order, state=state, booked_price=price,
                tracking_number=number if state not in {"unknown", "submitting"} else None,
                submitted_at=stamp(when) if state not in {"unknown", "submitting", "failed"} else None,
                last_error="PRIVATE-PROVIDER-ERROR" if state == "unknown" else "")
        return order

    def record_expense(self, *, error=None):
        if error:
            self.client.refund_partial.side_effect = error
        with patch("django.utils.timezone.now", return_value=stamp("2026-09-20T10:00")):
            if error:
                with self.assertRaises(type(error)):
                    self.request()
                return PaymentTransaction.objects.get(order=self.order, action="refund")
            return self.request()

    def test_not_booked_and_cancelled_are_not_booked_price_but_remain_visible(self):
        self.paid_order("NOT-BOOKED")
        self.paid_order("CANCELLED", state="cancelled")
        self.paid_order("CREATED", state="created")
        report = build_dashboard_report(self.september)
        self.assertEqual(report["summary"]["courier_payable"], "12.00")
        self.assertEqual((report["summary"]["courier_booked_orders"], report["summary"]["courier_cancelled_orders"]), (1, 1))
        self.assertEqual(report["delivery_rows_total"], 2)
        self.assertEqual(shipment_report({"shipments": "not_sent"})["items"][0]["order_number"], "NOT-BOOKED")
        self.assertEqual(shipment_report({"shipments": "cancelled"})["total"], 1)

    def test_quote_booked_price_and_buffer_are_separate_and_missing_price_is_unknown(self):
        self.paid_order("DIFFERENT", state="created", price=D(15), buffer=D(3))
        report = booking_report(self.september)
        row = report["rows"][0]
        self.assertEqual((row["customer_delivery"], row["quoted_price"], row["booked_price"], row["buffer"], row["difference"]),
            ("15.00", "12.00", "15.00", "3.00", "3.00"))
        self.assertEqual((report["total"], report["mismatches"]), (D(15), 1))
        self.assertEqual(shipment_report({"shipments": "review"})["total"], 1)
        ledger = build_ledger(self.september, "all")
        line = next(row for row in ledger["rows"] if row[1] == "DIFFERENT")
        self.assertEqual((line[12], line[13], *line[20:22]), (D(12), D(3), D(15), D(3)))
        self.assertEqual(ledger["courier_bookings"]["total"], D(15))
        with ZipFile(BytesIO(export_response(ledger).content)) as archive:
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet3.xml"))
            for cell, value in (("D8", 15), ("E8", 12), ("F8", 15), ("G8", 3), ("H8", 3)):
                self.assertEqual(D(sheet.find(f'.//s:c[@r="{cell}"]/s:v', ns).text), D(value))
        self.paid_order("NO-PRICE", state="created", price=None)
        report = booking_report(self.september)
        self.assertIsNone(report["total"])
        self.assertEqual((report["known_price"], report["unknown"]), (D(15), 1))
        self.assertIsNone(build_dashboard_report(self.september)["summary"]["courier_payable"])

    def test_booking_uses_submission_month_and_unknown_request_does_not_invent_a_booking(self):
        self.paid_order("OCTOBER-BOOKING", state="created", when="2026-10-01T01:00")
        self.paid_order("UNKNOWN", state="unknown")
        self.assertEqual(booking_report(self.september)["total"], D(0))
        self.assertEqual(booking_report(self.october)["total"], D(12))
        review = shipment_report({"shipments": "review"})
        self.assertEqual(review["total"], 1)
        self.assertEqual(review["items"][0]["stage"], "uncertain")
        self.assertNotIn("PRIVATE", str(review))

    def test_shipment_filters_pagination_and_counts_are_global(self):
        for index in range(23):
            self.paid_order(f"PANEL-{index}", state="created")
        orders = Order.objects.filter(delivery_provider="wingo").order_by("pk")
        first = orders.first()
        WingoShipment.objects.filter(order=first).update(carrier_status=3)
        delivered = orders[1]
        WingoShipment.objects.filter(order=delivered).update(carrier_status=9)
        with connection.execute_wrapper(self.read_only), CaptureQueriesContext(connection) as queries:
            page = shipment_report({"shipments_page": 2})
        self.assertLessEqual(len(queries), 3)
        self.assertEqual((page["total"], page["pages"], len(page["items"])), (23, 2, 3))
        self.assertEqual((page["summary"]["shipped"], page["summary"]["delivered"]), (1, 1))
        self.assertEqual(shipment_report({"shipments": "shipped"})["items"][0]["order_number"], first.order_number)
        self.assertNotIn("PRIVATE", str(page))

    def test_numeric_statuses_and_unverified_webhook_are_reported_from_stored_facts_only(self):
        order = self.paid_order("CANONICAL", state="created")
        for status, stage in ((1, "created"), (2, "created"), (3, "shipped"), (5, "shipped"),
                              (6, "shipped"), (7, "shipped"), (9, "delivered"), (10, "cancelled")):
            with self.subTest(status=status):
                WingoShipment.objects.filter(order=order).update(carrier_status=status)
                report = shipment_report({"shipments": stage})
                self.assertEqual((report["total"], report["items"][0]["stage"]), (1, stage))
                self.assertEqual(report["summary"][stage], 1)
        WingoShipment.objects.filter(order=order).update(carrier_status=1, webhook_received_at=stamp("2026-09-15T12:00"))
        report = shipment_report({"shipments": "review"})
        self.assertEqual(report["total"], 1)
        self.assertIn("ჯერ არ გადამოწმებულა", str(report["items"][0]["issues"]))
        case = OrderReturn.objects.create(order=order, disposition="from_customer", receipt_status="awaiting",
            wingo_return_tracking_number="999-RETURN-1")
        report = shipment_report({"shipments": "returning"})
        self.assertEqual(report["items"][0]["return_tracking_number"], case.wingo_return_tracking_number)
        self.assertNotIn("PRIVATE", str(report))

    @staticmethod
    def read_only(execute, sql, params, many, context):
        if sql.lstrip().split()[0].upper() != "SELECT":
            raise AssertionError("Business reports must only select stored facts")
        return execute(sql, params, many, context)

    def test_return_cost_survives_bank_rejection_and_retry_does_not_duplicate_or_move_month(self):
        self.record_expense(error=BogResponseError(code="rejected", retryable=False, outcome_unknown=False))
        self.assertEqual(return_cost_report(self.september)["total"], D(10))
        self.assertEqual(build_cash_report(self.september)["currencies"]["GEL"]["refunded"], D(0))
        self.order.refresh_from_db()
        self.client.refund_partial.side_effect = None
        with patch("django.utils.timezone.now", return_value=stamp("2026-10-02T10:00")):
            self.request()
            self.confirm()
        self.assertEqual((return_cost_report(self.september)["total"], return_cost_report(self.october)["total"]), (D(10), D(0)))
        september = build_dashboard_report(self.september)["summary"]
        october = build_dashboard_report(self.october)["summary"]
        self.assertEqual((september["return_delivery_cost"], september["refunded"]), ("10.00", "0.00"))
        self.assertEqual((october["return_delivery_cost"], october["refunded"], october["retained_return_fee"]), ("0.00", "90.00", "10.00"))
        ledger = build_ledger(self.september, "all")
        self.assertEqual(ledger["return_costs"]["total"], D(10))
        self.assertEqual(build_ledger(self.october, "all")["return_costs"]["total"], D(0))
        self.assertIsNone(build_ledger(self.september, "all", sku=self.product.internal_sku)["return_costs"])

    def test_unknown_bank_result_keeps_cost_and_rejects_changed_recorded_cost(self):
        self.record_expense(error=BogTransportError(code="timeout", retryable=True, outcome_unknown=True))
        changed = build_settlement(total=100, cost=20, payer="customer", agreed=True, reason="შეთანხმებულია")
        with self.assertRaises(ValidationError):
            self.request(changed)
        self.assertEqual(return_cost_report(self.september)["total"], D(10))
        rows = build_operations_report({"returns": "received"})["returns"]["items"]
        row = rows[0]
        self.assertEqual((row["refunded_amount"], row["requested_refund"], row["return_delivery_cost"], row["refund_confirmed"]),
            ("0.00", "90.00", "10.00", False))

    def test_completed_refund_review_error_is_in_attention_without_private_error_content(self):
        refund = self.record_expense()
        self.confirm()
        PaymentTransaction.objects.filter(pk=refund.pk).update(error_code="bog_refund_additional_activity_requires_review", error_message="PRIVATE-BANK-ERROR")
        report = build_operations_report({"payments": "issues"})
        self.assertEqual(report["payments"]["summary"]["issues"], 1)
        self.assertEqual(report["payments"]["items"][0]["id"], refund.pk)
        self.assertNotIn("PRIVATE", str(report))

    def test_unknown_cost_is_not_free_and_expense_excel_matches_accountant_and_business(self):
        self.assertIsNone(return_cost_report(self.september)["total"])
        self.assertEqual(return_cost_report(self.september)["unknown"], 1)
        self.record_expense()
        ledger = build_ledger(self.september, "all")
        html = self.admin_client.get(reverse("accounting-report"), {"period_mode": "days", "status": "all", "start": "2026-09-01", "end": "2026-09-30"})
        self.assertContains(html, "უკუმიტანის ხარჯი — დაფიქსირების თარიღით")
        self.assertEqual(html.context["return_costs"]["total"], D(10))
        self.assertEqual(build_dashboard_report(self.september)["summary"]["return_delivery_cost"], "10.00")
        self.assertEqual(build_cash_report(self.september)["currencies"]["GEL"]["return_delivery_cost"], D(10))
        with ZipFile(BytesIO(export_response(ledger).content)) as archive:
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            cost_sheet = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
            self.assertEqual(D(cost_sheet.find('.//s:c[@r="C8"]/s:v', ns).text), D(10))
            self.assertEqual(D(cost_sheet.find('.//s:c[@r="C9"]/s:v', ns).text), D(10))
            self.assertIn("ბანკის დაბრუნების შედეგისგან დამოუკიდებლად", " ".join(cost_sheet.itertext()))
