"""Paid outbound delivery and return shipping remain separate frozen amounts."""
from datetime import date, datetime, timezone as utc
from decimal import Decimal as D
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from . import test_partial_refunds as fixtures
from .accounting_export import export_response
from .accounting_ledger import build_ledger
from .accounting_reports import ReportPeriod, build_cash_report
from .bog_payments import BogTransportError, BogResponseError
from .bog_refunds import reconcile_bog_refund_details
from .models import OwnedStockLot, PaymentTransaction, RedcapShipment
from .refund_terms import build_settlement, settlement_for_refund, validate_settlement
from .return_costs import return_cost_report
from business.operations import build_operations_report
from business.reports import build_dashboard_report


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class DeliveryDeductionTests(TestCase):
    _details = fixtures.PartialRefundTests._details
    request = fixtures.PartialRefundTests.request

    def setUp(self):
        fixtures.PartialRefundTests.setUp(self)
        self.set_delivery(10)
        self.shipment = RedcapShipment.objects.create(order=self.order, service_slug="same_day", state="created",
            carrier_status="delivered", tracking_number="OUTBOUND-1", booked_price=10, submitted_at=timezone.now())
        self.terms = self.terms_for()

    def set_delivery(self, amount, *, buffer=0):
        self.order.delivery_provider = "redcap"
        self.order.delivery_price = D(amount)
        self.order.carrier_delivery_cost = D(amount) - D(buffer)
        self.order.delivery_margin = D(buffer)
        self.order.total = D(100) + D(amount)
        self.order.save()
        self.sale.amount = self.order.total
        self.sale.save(update_fields=["amount"])

    def terms_for(self, **changes):
        return build_settlement(**{**dict(total=self.order.total, outbound_delivery=self.order.delivery_price,
            cost=10, payer="customer", agreed=True, reason="შეთანხმებულია"), **changes})

    def confirm(self, amount=90):
        details = self._details(status="refunded" if D(amount) == self.sale.amount else "refunded_partially",
            refund_amount=amount, action="refund" if D(amount) == self.sale.amount else "partial_refund", action_amount=amount)
        return reconcile_bog_refund_details(self.sale, details, provider_reference={"source": "verified_details"})

    def test_110_less_both_tens_submits_90_and_preserves_outbound_and_original_payment(self):
        refund = self.request()
        self.assertEqual((refund.amount, self.terms["retained_delivery_fee"], self.terms["retained_return_fee"]),
                         (D(90), "10.00", "10.00"))
        self.client.refund_partial.assert_called_once_with(order_id=self.sale.provider_order_id,
            idempotency_key=refund.idempotency_key, amount=D(90))
        self.client.refund_full.assert_not_called()
        self.assertEqual(self.confirm().result, "refunded_and_cancelled")
        self.assertEqual(self.confirm().result, "already_refunded")
        self.order.refresh_from_db()
        self.shipment.refresh_from_db()
        self.assertEqual((self.order.total, self.order.delivery_price, self.sale.amount), (D(110), D(10), D(110)))
        self.assertEqual((self.shipment.tracking_number, self.shipment.carrier_status), ("OUTBOUND-1", "delivered"))
        self.assertEqual(OwnedStockLot.objects.count(), 1)

    def test_merchant_pays_refunds_110_and_retains_no_delivery_fees(self):
        refund = self.request(self.terms_for(payer="merchant"))
        self.assertEqual(refund.amount, D(110))
        self.client.refund_full.assert_called_once()
        self.client.refund_partial.assert_not_called()
        self.confirm(110)
        report = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((report["refunded"], report["retained_delivery_fee"], report["retained_return_fee"],
                          report["return_delivery_cost"], report["delivery_refunded"]), (D(110), D(0), D(0), D(10), D(10)))

    def test_zero_return_cost_still_submits_partial_for_paid_outbound_delivery(self):
        refund = self.request(self.terms_for(cost=0))
        self.assertEqual(refund.amount, D(100))
        self.client.refund_full.assert_not_called()
        self.assertEqual(self.client.refund_partial.call_args.kwargs["amount"], D(100))
        self.confirm(100)
        report = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((report["retained_delivery_fee"], report["retained_return_fee"], report["return_delivery_cost"]),
                         (D(10), D(0), D(0)))

    def test_free_delivery_deducts_only_real_return_fee(self):
        self.set_delivery(0)
        refund = self.request(self.terms_for())
        self.assertEqual(refund.amount, D(90))
        self.confirm()
        report = build_dashboard_report(self.period)["summary"]
        self.assertEqual((report["retained_delivery_fee"], report["retained_return_fee"], report["net_delivery_received"]),
                         ("0.00", "10.00", "0.00"))

    def test_paid_delivery_including_buffer_is_frozen_not_replaced_by_booked_price(self):
        self.set_delivery(13, buffer=3)
        RedcapShipment.objects.filter(pk=self.shipment.pk).update(booked_price=15)
        self.request(self.terms_for())
        self.confirm(90)
        report = build_dashboard_report(self.period)["summary"]
        self.assertEqual((report["retained_delivery_fee"], report["net_delivery_received"], report["net_buffer"],
                          report["courier_payable"]), ("13.00", "13.00", "3.00", "15.00"))
        row = build_ledger(self.period, "refunded")["rows"][0]
        self.assertEqual((row[12], row[13], row[18], row[22]), (D(0), D(0), D(10), D(13)))

    def test_customer_deductions_require_valid_agreement_money_and_positive_refund(self):
        for changes in ({"outbound_delivery": -1}, {"outbound_delivery": "NaN"},
                        {"outbound_delivery": "10.001"}, {"outbound_delivery": 111},
                        {"cost": 100}, {"agreed": False}, {"reason": ""},
                        {"outbound_delivery": 0, "cost": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.terms_for(**changes)
        self.client.refund_partial.assert_not_called()

    def test_forged_paid_delivery_or_unknown_version_never_reaches_bank(self):
        for terms in (self.terms_for(outbound_delivery=20), {**self.terms, "version": 3},
                      {**self.terms, "retained_delivery_fee": "20.00"},
                      {key: value for key, value in self.terms.items() if key != "outbound_delivery_price"}):
            with self.subTest(terms=terms), self.assertRaises(ValidationError):
                self.request(terms)
        self.assertFalse(PaymentTransaction.objects.filter(action="refund").exists())
        self.client.refund_partial.assert_not_called()

    def test_legacy_frozen_terms_remain_100_and_unsupported_versions_reject(self):
        legacy = build_settlement(total=110, cost=10, payer="customer", agreed=True, reason="შეთანხმებულია")
        refund = self.request(legacy)
        self.assertEqual(refund.amount, D(100))
        self.assertEqual(settlement_for_refund(refund, total=110), legacy)
        for changed in ({**legacy, "version": True}, {**legacy, "version": 9}):
            with self.assertRaises(ValidationError):
                validate_settlement(changed, total=110)
        self.confirm(100)
        report = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((report["retained_delivery_fee"], report["delivery_refunded"]), (D(0), D(10)))

    def test_unknown_retry_freezes_both_deductions_and_cannot_change_payer(self):
        self.client.refund_partial.side_effect = BogTransportError(code="timeout", retryable=True, outcome_unknown=True)
        with self.assertRaises(BogTransportError):
            self.request()
        original = PaymentTransaction.objects.get(action="refund")
        for changed in (self.terms_for(payer="merchant"), self.terms_for(cost=11)):
            with self.assertRaises(ValidationError):
                self.request(changed)
        self.client.refund_partial.side_effect = None
        replay = self.request()
        self.assertEqual((replay.pk, replay.idempotency_key, replay.amount), (original.pk, original.idempotency_key, D(90)))
        self.assertEqual([call.kwargs["amount"] for call in self.client.refund_partial.call_args_list], [D(90), D(90)])
        self.assertEqual(return_cost_report(self.period)["total"], D(10))

    def test_wrong_bank_amount_does_not_confirm_both_deduction_settlement(self):
        self.request()
        self.assertEqual(self.confirm(100).result, "refund_reconciliation_required")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "refund_pending")
        self.assertEqual(self.confirm().result, "refunded_and_cancelled")

    def test_cash_business_operations_accountant_and_excel_reconcile_without_double_count(self):
        self.request()
        self.confirm()
        cash = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((cash["received"], cash["refunded"], cash["net_received"]), (D(110), D(90), D(20)))
        self.assertEqual((cash["product_refunded"], cash["delivery_refunded"], cash["net_delivery"],
                          cash["retained_delivery_fee"], cash["retained_return_fee"], cash["return_delivery_cost"]),
                         (D(100), D(0), D(10), D(10), D(10), D(10)))
        # Outbound retention is already within net delivery: do not add it twice.
        self.assertEqual(cash["net_received"], cash["product_received"] - cash["product_refunded"]
                         + cash["net_delivery"] + cash["retained_return_fee"])
        summary = build_dashboard_report(self.period)["summary"]
        self.assertEqual((summary["net_received"], summary["product_profit_net"], summary["net_delivery_received"],
            summary["retained_delivery_fee"], summary["retained_return_fee"], summary["return_delivery_cost"]),
            ("20.00", "0.00", "10.00", "10.00", "10.00", "10.00"))
        operation = build_operations_report({"returns": "received"})["returns"]["items"][0]
        self.assertEqual((operation["refunded_amount"], operation["retained_delivery_fee"], operation["retained_return_fee"]),
                         ("90.00", "10.00", "10.00"))
        ledger = build_ledger(self.period, "all")
        self.assertEqual((ledger["totals"][12], ledger["totals"][14], ledger["totals"][18], ledger["totals"][22]),
                         (D(10), D(20), D(10), D(10)))
        self.assertEqual(len(ledger["headers"]), len(ledger["totals"]))
        self.assertEqual(ledger["return_costs"]["total"], D(10))
        self.assertEqual(ledger["courier_bookings"]["total"], D(10))
        ledger["show_purchase"] = True
        with ZipFile(BytesIO(export_response(ledger).content)) as archive:
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            for cell, amount in (("O9", -90), ("M9", 0), ("S9", 10), ("T9", 10), ("W9", 10), ("W10", 10)):
                self.assertEqual(D(sheet.find(f'.//s:c[@r="{cell}"]/s:v', ns).text), D(amount))
        html = self.admin_client.get(reverse("accounting-report"), {"period_mode": "days", "status": "refunded",
            "start": self.period.start, "end": self.period.end})
        self.assertContains(html, "პირველი მიტანისთვის დაქვითული")
        self.assertIn(("დაბრუნებული თანხა", "90.00"), html.context["groups"][0]["delivery"])
        sku = build_ledger(self.period, "all", sku=self.product.internal_sku)
        self.assertIsNone(sku["totals"][22])
        self.assertTrue(all(row[22] is None for row in sku["rows"]))

    def test_fee_retention_uses_bank_refund_month_and_expense_keeps_first_attempt_month(self):
        september = ReportPeriod(date(2026, 9, 1), date(2026, 9, 30))
        october = ReportPeriod(date(2026, 10, 1), date(2026, 10, 31))
        PaymentTransaction.objects.filter(pk=self.sale.pk).update(captured_at=datetime(2026, 9, 1, tzinfo=utc.utc))
        self.client.refund_partial.side_effect = BogResponseError(code="rejected", retryable=False, outcome_unknown=False)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 20, tzinfo=utc.utc)):
            with self.assertRaises(BogResponseError):
                self.request()
        self.client.refund_partial.side_effect = None
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 2, tzinfo=utc.utc)):
            self.request()
            self.confirm()
        before = build_dashboard_report(september)["summary"]
        after = build_dashboard_report(october)["summary"]
        self.assertEqual((before["return_delivery_cost"], before["retained_delivery_fee"]), ("10.00", "0.00"))
        self.assertEqual((after["return_delivery_cost"], after["retained_delivery_fee"], after["retained_return_fee"]),
                         ("0.00", "10.00", "10.00"))

    def test_admin_calculates_both_fees_and_requires_exact_fresh_preview(self):
        url = reverse("admin:commerce_order_bog_refund", args=[self.order.pk])
        fields = dict(confirm="on", return_delivery_payer="customer", return_delivery_cost="10",
                      customer_agreed="on", deduction_reason="შეთანხმებულია")
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            preview = self.admin_client.post(url, fields)
            self.assertContains(preview, "დადასტურება და 90.00 ₾-ის დაბრუნება")
            self.assertEqual(preview.context["settlement"]["outbound_delivery_price"], "10.00")
            token = preview.context["preview_token"]
            changed = self.admin_client.post(url, {**fields, "return_delivery_cost": "12", "execute": "yes", "preview_token": token})
            self.assertContains(changed, "დადასტურება და 88.00 ₾-ის დაბრუნება")
            self.client.refund_partial.assert_not_called()
            done = self.admin_client.post(url, {**fields, "execute": "yes", "preview_token": token})
            self.assertEqual(done.status_code, 302)
            self.assertEqual(self.client.refund_partial.call_args.kwargs["amount"], D(90))

    def test_legacy_pending_admin_retry_keeps_old_amount_and_version(self):
        legacy = build_settlement(total=110, cost=10, payer="customer", agreed=True, reason="შეთანხმებულია")
        self.client.refund_partial.side_effect = BogTransportError(code="timeout", retryable=True, outcome_unknown=True)
        with self.assertRaises(BogTransportError):
            self.request(legacy)
        self.client.refund_partial.side_effect = None
        url = reverse("admin:commerce_order_bog_refund", args=[self.order.pk])
        fields = dict(confirm="on")
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            preview = self.admin_client.post(url, fields)
            self.assertContains(preview, "დადასტურება და 100.00 ₾-ის დაბრუნება")
            self.assertEqual(preview.context["settlement"], legacy)
            done = self.admin_client.post(url, {**fields, "execute": "yes", "preview_token": preview.context["preview_token"]})
            self.assertEqual(done.status_code, 302)
        self.assertEqual(PaymentTransaction.objects.get(action="refund").amount, D(100))

    def test_customer_apis_keep_existing_contract_and_report_actual_90_without_extra_instructions(self):
        self.request()
        self.confirm()
        api = APIClient()
        api.force_authenticate(self.admin_user)
        urls = [reverse("commerce-order-summary", args=[self.order.public_token]),
                reverse("commerce-order-detail", args=[self.order.public_token])]
        payloads = [api.get(url).json() for url in urls]
        payloads.append(api.get(reverse("commerce-order-list")).json()["results"][0])
        with patch("commerce.views.validate_recaptcha", return_value=True):
            payloads.append(api.post(reverse("commerce-order-lookup"), {"order_number": self.order.order_number,
                "phone": self.order.phone, "recaptcha_token": "test"}).json())
        for payload in payloads:
            self.assertEqual(payload["refund_summary"], {"status": "refunded", "amount": "90.00", "retained_return_fee": "10.00"})
            self.assertNotIn("retained_delivery_fee", str(payload))
            self.assertNotIn("deduction_reason", str(payload))
