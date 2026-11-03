"""Whole goods return: real cash deduction, complete goods reversal, one receipt."""
from dataclasses import replace
from datetime import timedelta
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

from . import test_bog_refunds as fixtures
from .accounting_ledger import build_ledger
from .accounting_reports import ReportPeriod, build_cash_report
from .accounting_export import export_response
from .bog_payments import BogTransportError
from .bog_refunds import request_bog_full_refund, reconcile_bog_refund_details
from .models import OrderItem, OwnedStockLot, PaymentTransaction
from .refund_terms import build_settlement
from .returns import prepare_order_return, receive_order_return
from business.reports import build_dashboard_report


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PartialRefundTests(TestCase):
    _details = fixtures.BogRefundFlowTests._details

    def setUp(self):
        fixtures.BogRefundFlowTests.setUp(self)
        self.order.status = "delivered"
        self.order.delivery_provider = "internal"
        self.order.user = self.admin_user
        self.order.save()
        item = self.order.items.get()
        # Create the fixture's immutable cost snapshot at insert time.
        item.delete(allow_hard_delete=True)
        OrderItem.objects.create(order=self.order, product=self.product, product_name=self.product.name,
            sku=self.product.sku, internal_sku=self.product.internal_sku, unit_price=100, quantity=1, line_total=100,
            purchase_unit_gross=D(60), purchase_cost_source="catalog_supplier_price", purchase_cost_recorded_at=timezone.now())
        self.case = prepare_order_return(order=self.order, disposition="from_customer", actor=self.admin_user)
        receive_order_return(return_case=self.case, actor=self.admin_user,
            inspection={line.pk: {"saleable": 1, "unsaleable": 0} for line in self.case.lines.all()})
        self.client.refund_partial.return_value = self.client.refund_full.return_value
        self.terms = build_settlement(total=100, cost=10, payer="customer", agreed=True, reason="მომხმარებელს შეეშალა")
        today = timezone.localdate()
        self.period = ReportPeriod(today - timedelta(days=1), today + timedelta(days=1))

    def request(self, terms=None):
        return request_bog_full_refund(order=self.order, client=self.client, requested_by=self.admin_user,
            disposition="from_customer", settlement=terms if terms is not None else self.terms)

    def confirm(self, **changes):
        details = self._details(status="refunded_partially", refund_amount=90, action="partial_refund", action_amount=90)
        return reconcile_bog_refund_details(self.sale, replace(details, **changes), provider_reference={"source": "verified_details"})

    def test_request_is_90_pending_and_accepted_replay_does_not_submit_again(self):
        refund = self.request()
        self.assertEqual(refund.amount, D(90))
        self.assertEqual(self.request().pk, refund.pk)
        self.client.refund_partial.assert_called_once_with(order_id=self.sale.provider_order_id,
            idempotency_key=refund.idempotency_key, amount=D(90))
        self.client.refund_full.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual((self.order.total, self.order.payment_status), (D(100), "refund_pending"))

    def test_confirmation_cancels_whole_goods_return_once_and_preserves_original_total(self):
        self.request()
        first = self.confirm()
        stamp = first.order.stock_restored_at
        self.assertEqual(first.result, "refunded_and_cancelled")
        self.assertEqual((first.order.total, first.order.payment_status, first.order.status), (D(100), "partially_refunded", "cancelled"))
        self.assertEqual(self.confirm().result, "already_refunded")
        self.order.refresh_from_db()
        self.assertEqual(self.order.stock_restored_at, stamp)
        self.assertEqual(OwnedStockLot.objects.get().quantity, 1)
        self.assertEqual(PaymentTransaction.objects.filter(action="refund").count(), 1)

    def test_merchant_pays_cost_but_refunds_the_entire_100(self):
        terms = build_settlement(total=100, cost=10, payer="merchant")
        refund = self.request(terms)
        self.client.refund_full.assert_called_once()
        self.client.refund_partial.assert_not_called()
        result = self.confirm(status="refunded", refund_amount=D(100), actions=self._details(
            status="refunded", refund_amount=100).actions)
        self.assertEqual(result.order.payment_status, "refunded")
        self.assertEqual(refund.amount, D(100))
        summary = build_dashboard_report(self.period)["summary"]
        self.assertEqual((summary["refunded"], summary["retained_return_fee"], summary["return_delivery_cost"]), ("100.00", "0.00", "10.00"))

    def test_timeout_retry_keeps_key_and_frozen_amount_changed_terms_rejected(self):
        self.client.refund_partial.side_effect = BogTransportError(code="timeout", retryable=True, outcome_unknown=True)
        with self.assertRaises(BogTransportError):
            self.request()
        refund = PaymentTransaction.objects.get(action="refund")
        changed = build_settlement(total=100, cost=20, payer="customer", agreed=True, reason="მომხმარებელს შეეშალა")
        with self.assertRaises(ValidationError):
            self.request(changed)
        self.client.refund_partial.side_effect = None
        self.assertEqual(self.request().idempotency_key, refund.idempotency_key)
        self.assertEqual([c.kwargs["amount"] for c in self.client.refund_partial.call_args_list], [D(90), D(90)])

    def test_wrong_amount_foreign_action_and_wrong_payment_do_not_finalize(self):
        self.request()
        for changes in ({"refund_amount": D(80)}, {"order_id": "another-payment"},
                        {"actions": (replace(self._details(status="refunded_partially", refund_amount=90,
                            action="partial_refund", action_amount=90).actions[0], action_id="foreign"),)}):
            with self.subTest(changes=changes):
                self.assertEqual(self.confirm(**changes).result, "refund_reconciliation_required")
                self.order.refresh_from_db()
                self.assertEqual(self.order.payment_status, "refund_pending")
                self.assertIsNone(self.order.stock_restored_at)
        self.assertEqual(self.confirm().order.payment_status, "partially_refunded")

    def test_rejected_partial_request_restores_paid_and_late_rejection_cannot_undo_confirmation(self):
        self.request()
        rejected = self._details(status="completed", refund_amount=0, action="partial_refund", action_amount=90, action_status="rejected")
        result = reconcile_bog_refund_details(self.sale, rejected, provider_reference={})
        self.assertEqual(result.result, "refund_rejected")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        # A later confirmed result for that same action remains processable.
        self.confirm()
        result = reconcile_bog_refund_details(self.sale, rejected, provider_reference={})
        self.assertEqual(result.refund.status, "refunded")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "partially_refunded")

    def test_invalid_fees_agreement_and_fractional_cents_are_rejected(self):
        for changes in ({"cost": -1}, {"cost": 100}, {"cost": "1.001"}, {"cost": "NaN"},
                        {"agreed": False}, {"reason": ""}, {"cost": 0}, {"payer": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                build_settlement(**{**dict(total=100, cost=10, payer="customer", agreed=True, reason="შეთანხმებულია"), **changes})
        self.client.refund_partial.assert_not_called()

    def test_callback_before_http_acceptance_cannot_be_undone_by_transport_error(self):
        def callback_then_timeout(**kwargs):
            self.confirm()
            raise BogTransportError(code="timeout", outcome_unknown=True, retryable=True)
        self.client.refund_partial.side_effect = callback_then_timeout
        with self.assertRaises(BogTransportError):
            self.request()
        refund = PaymentTransaction.objects.get(action="refund")
        self.order.refresh_from_db()
        self.assertEqual((refund.status, self.order.payment_status), ("refunded", "partially_refunded"))
        self.assertEqual(refund.error_code, "")
        self.assertEqual(OwnedStockLot.objects.count(), 1)

    def test_additional_external_refund_is_flagged_without_reversing_confirmed_state(self):
        self.request()
        self.confirm()
        full = self._details(status="refunded", refund_amount=100)
        result = reconcile_bog_refund_details(self.sale, full, provider_reference={"source": "verified_details"})
        self.assertEqual(result.result, "refund_reconciliation_required")
        self.assertEqual(result.refund.status, "refunded")
        self.assertEqual(result.refund.amount, D(90))
        self.assertEqual(result.refund.error_code, "bog_refund_additional_activity_requires_review")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "partially_refunded")
        self.assertEqual(OwnedStockLot.objects.count(), 1)
        self.assertEqual(self.confirm().result, "refund_reconciliation_required")

    def test_cash_ledger_excel_and_business_reverse_goods_fully_and_separate_return_fee(self):
        self.request()
        self.confirm()
        cash = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((cash["received"], cash["refunded"], cash["net_received"]), (D(100), D(90), D(10)))
        self.assertEqual((cash["product_refunded"], cash["retained_return_fee"], cash["return_delivery_cost"]), (D(100), D(10), D(10)))
        ledger = build_ledger(self.period, "all")
        self.assertEqual((ledger["totals"][4], ledger["totals"][8], ledger["totals"][10], ledger["totals"][14]), (0, D(0), D(0), D(10)))
        self.assertEqual(ledger["totals"][18:20], [D(10), None])
        self.assertEqual(ledger["return_costs"]["total"], D(10))
        refund_report = build_ledger(self.period, "refunded")
        self.assertEqual((refund_report["rows"][0][8], refund_report["rows"][0][14]), (D(100), D(90)))
        self.assertEqual(build_ledger(self.period, "paid")["rows"], [])
        self.assertEqual(build_ledger(self.period, "all", sku=self.product.internal_sku)["totals"][18:20], [None, None])
        summary = build_dashboard_report(self.period)["summary"]
        self.assertEqual((summary["net_received"], summary["product_profit_net"], summary["returned_units"],
                          summary["retained_return_fee"], summary["return_delivery_cost"]), ("10.00", "0.00", 1, "10.00", "10.00"))
        ledger["show_purchase"] = True
        with ZipFile(BytesIO(export_response(ledger).content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for cell, value in (("O9", "-90.00"), ("S9", "10.00"), ("T9", "10.00")):
                self.assertEqual(D(sheet.find(f'.//s:c[@r="{cell}"]/s:v', ns).text), D(value))
        url = reverse("accounting-report")
        response = self.admin_client.get(url, {"period_mode": "days", "start": self.period.start,
            "end": self.period.end, "status": "refunded"})
        self.assertContains(response, "უკუმიტანისთვის დაქვითული")
        self.assertIn(("დაბრუნებული თანხა", "90.00"), response.context["groups"][0]["delivery"])

    def test_customer_api_surfaces_actual_amount_and_no_private_metadata(self):
        self.request()
        api = APIClient()
        api.force_authenticate(self.admin_user)
        public_url = reverse("commerce-order-summary", args=[self.order.public_token])
        self.assertEqual(api.get(public_url).json()["refund_summary"]["status"], "refund_pending")
        self.confirm()
        urls = [public_url, reverse("commerce-order-detail", args=[self.order.public_token])]
        payloads = [api.get(url).json() for url in urls]
        payloads.append(api.get(reverse("commerce-order-list")).json()["results"][0])
        with patch("commerce.views.validate_recaptcha", return_value=True):
            payloads.append(api.post(reverse("commerce-order-lookup"), {"order_number": self.order.order_number,
                "phone": self.order.phone, "recaptcha_token": "test"}).json())
        for payload in payloads:
            self.assertEqual(payload["payment_status"], "partially_refunded")
            self.assertEqual(payload["refund_summary"], {"status": "refunded", "amount": "90.00", "retained_return_fee": "10.00"})
            self.assertNotIn("deduction_reason", str(payload))

    def test_admin_previews_then_explicitly_confirms_90_and_detects_changed_form(self):
        url = reverse("admin:commerce_order_bog_refund", args=[self.order.pk])
        fields = {"confirm": "on", "return_delivery_payer": "customer", "return_delivery_cost": "10",
            "customer_agreed": "on", "deduction_reason": "შეთანხმებულია"}
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            response = self.admin_client.post(url, fields)
            self.assertContains(response, "დადასტურება და 90.00 ₾-ის დაბრუნება")
            self.client.refund_partial.assert_not_called()
            token = response.context["preview_token"]
            changed = self.admin_client.post(url, {**fields, "return_delivery_cost": "20", "execute": "yes", "preview_token": token})
            self.assertContains(changed, "დადასტურება და 80.00 ₾-ის დაბრუნება")
            self.client.refund_partial.assert_not_called()
            done = self.admin_client.post(url, {**fields, "execute": "yes", "preview_token": token})
            self.assertEqual(done.status_code, 302)
            self.client.refund_partial.assert_called_once()
