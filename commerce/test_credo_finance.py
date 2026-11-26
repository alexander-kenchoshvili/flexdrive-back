from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings, RequestFactory
from django.http import HttpResponse
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone

from .accounting_calculations import calculate_product_line
from .accounting_export import export_response
from .accounting_ledger import build_ledger
from .accounting_reports import ReportPeriod, build_cash_report
from .credo_checkout import apply_credo_observation
from .credo_finance import confirm_credo_statement, expected_credo_amounts, is_credo_purchase_eligible, TBILISI
from .models import CredoApplication, CredoStatementSettlement, Order, PaymentTransaction
from .serializers import PublicOrderSummarySerializer
from .test_credo_checkout import CredoCheckoutFixture


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class CredoFinanceTests(CredoCheckoutFixture):
    def setUp(self):
        super().setUp()
        patch("requests.post", side_effect=AssertionError("No real marketing or bank requests")).start()
        self.user.is_staff = True; self.user.save(update_fields=["is_staff"])
        self.user.user_permissions.add(Permission.objects.get(codename="add_credostatementsettlement", content_type__app_label="commerce"))
        self.application = self.prepare().application
        today = timezone.localdate(timezone=TBILISI)
        self.period = ReportPeriod(today-timedelta(days=1), today+timedelta(days=1))
        self.statement_data = dict(application_id=self.application.pk, fee_amount="2.07", net_amount="66.93",
            received_on=today, statement_reference="statement-line-test", actor=self.user, confirmed=True)

    def complete(self):
        self.application = apply_credo_observation(self.application.pk, 12)
        self.application = apply_credo_observation(self.application.pk, 5)
        return self.application

    def settle(self, **overrides):
        return confirm_credo_statement(**{**self.statement_data, **overrides})

    def test_customer_total_and_bank_basket_unchanged_for_both_offers(self):
        amounts = expected_credo_amounts(self.application)
        self.assertEqual(amounts, {"gross": Decimal("69.00"), "fee": Decimal("2.07"), "net": Decimal("66.93")})
        financing = self.application.checkout_snapshot["financing"]
        self.assertEqual(financing["fee_payer"], "merchant")
        self.assertEqual(financing["customer_surcharge"], "0.00")
        self.complete()
        self.assertEqual(self.application.order.total, Decimal("69.00"))
        self.assertEqual(self.application.order.subtotal, Decimal("60.00"))
        self.assertEqual(self.application.order.delivery_price, Decimal("9.00"))

    def test_completed_status_is_not_cash_receipt_or_paid_order(self):
        self.complete()
        self.assertEqual(self.application.order.payment_status, "pending")
        self.assertFalse(PaymentTransaction.objects.exists())
        self.assertFalse(CredoStatementSettlement.objects.exists())
        self.assertEqual(build_cash_report(self.period)["events"], [])
        report = build_ledger(self.period, "paid")
        self.assertEqual(report["rows"], [])
        row = report["credo_financing"]["rows"][0]
        self.assertTrue(row["bank_completed"])
        self.assertIsNone(row["actual_fee"])
        self.assertIsNone(row["actual_net"])

    def test_receipt_confirmation_is_idempotent_and_records_gross_fee_net_once(self):
        self.complete()
        first, repeated = self.settle(), self.settle()
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(first.payment.amount, Decimal("69.00"))
        self.assertEqual(first.fee_amount+first.net_amount, first.gross_amount)
        self.application.order.refresh_from_db()
        self.assertEqual(self.application.order.payment_status, "paid")
        self.assertEqual(first.payment.captured_at.astimezone(TBILISI).date(), first.received_on)
        self.assertEqual(first.payment.provider_reference["date_precision"], "date")
        with self.assertRaises(ValidationError): self.settle(statement_reference="different")

    def test_cash_report_counts_actual_net_and_exposes_fee_separately(self):
        self.complete(); self.settle()
        report = build_cash_report(self.period)
        totals = report["currencies"]["GEL"]
        self.assertEqual(totals["received"], Decimal("66.93"))
        self.assertEqual(totals["gross_received"], Decimal("69.00"))
        self.assertEqual(totals["merchant_fee"], Decimal("2.07"))
        self.assertEqual(report["events"][0]["date_precision"], "date")

    def test_ledger_subtracts_fee_once_without_changing_product_revenue_or_purchase_cost(self):
        self.complete(); self.settle()
        report = build_ledger(self.period, "paid")
        row = report["rows"][0]
        self.assertEqual(row[8], Decimal("60.00"))
        self.assertEqual(row[7], Decimal("40.00"))
        self.assertEqual(row[14], Decimal("69.00"))
        self.assertEqual(row[23:25], [Decimal("2.07"), Decimal("66.93")])
        self.assertEqual(row[25], row[10]-Decimal("2.07"))
        self.assertEqual(report["totals"][23:25], row[23:25])
        filtered = build_ledger(self.period, "paid", sku="FD-10")
        self.assertIsNone(filtered["rows"][0][23])
        self.assertIsNone(filtered["totals"][25])

    def test_permission_explicit_confirmation_and_balancing_are_required(self):
        self.complete()
        for invalid in (dict(confirmed=False), dict(fee_amount="3.00"), dict(net_amount="0.00"),
                        dict(received_on=date.max), dict(statement_reference=""), dict(fee_amount=2.07)):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError): self.settle(**invalid)
        with self.assertRaises(PermissionDenied): self.settle(actor=None)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_only_funded_real_unambiguous_orders_can_confirm_cash(self):
        self.application = apply_credo_observation(self.application.pk, 12)
        with self.assertRaises(ValidationError): self.settle()
        self.complete()
        for values in ({"is_test": True}, {"needs_review": True}):
            CredoApplication.objects.filter(pk=self.application.pk).update(**values)
            with self.assertRaises(ValidationError): self.settle()
            CredoApplication.objects.filter(pk=self.application.pk).update(is_test=False, needs_review=False)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_actual_fee_can_differ_from_forecast_but_still_reconcile_to_full_total(self):
        self.complete()
        settlement = self.settle(fee_amount="2.06", net_amount="66.94")
        self.assertEqual(settlement.fee_amount, Decimal("2.06"))
        self.assertEqual(expected_credo_amounts(self.application)["fee"], Decimal("2.07"))

    def test_confirmed_allocations_are_immutable_and_protected_from_bulk_edits(self):
        self.complete(); settlement = self.settle()
        for action in (lambda: settlement.save(), lambda: settlement.delete(),
                       lambda: CredoStatementSettlement.objects.filter(pk=settlement.pk).update(net_amount="1.00"),
                       lambda: CredoStatementSettlement.objects.all().delete()):
            with self.assertRaises(ValidationError): action()

    def test_purchase_flag_requires_bank_completion_and_excludes_test_or_review(self):
        application = apply_credo_observation(self.application.pk, 12)
        self.assertFalse(is_credo_purchase_eligible(application.order))
        self.assertFalse(PublicOrderSummarySerializer(application.order).data["purchase_eligible"])
        application = apply_credo_observation(application.pk, 5)
        self.assertTrue(is_credo_purchase_eligible(application.order))
        self.assertTrue(PublicOrderSummarySerializer(application.order).data["purchase_eligible"])
        CredoApplication.objects.filter(pk=application.pk).update(is_test=True)
        self.assertFalse(is_credo_purchase_eligible(application.order))

    @override_settings(META_CAPI_ENABLED=True, META_PIXEL_ID="test-pixel", META_CAPI_ACCESS_TOKEN="fake-for-tests")
    def test_consented_purchase_is_queued_after_completion_once_with_original_gross_value(self):
        application = apply_credo_observation(self.application.pk, 12)
        Order.objects.filter(pk=application.order_id).update(marketing_consent=True)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            apply_credo_observation(application.pk, 5)
        self.assertEqual(len(callbacks), 1)
        self.purchase_event.assert_called_once()
        self.assertEqual(self.purchase_event.call_args.kwargs["order"].total, Decimal("69.00"))
        with self.captureOnCommitCallbacks(execute=True) as repeated:
            apply_credo_observation(application.pk, 5)
        self.assertEqual(repeated, [])

    def test_excel_has_numeric_expected_and_actual_columns_without_inventing_unknown_zeroes(self):
        self.complete()
        report = build_ledger(self.period, "paid")
        data = export_response(report).content
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(data)) as archive:
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = book.findall("s:sheets/s:sheet", ns)
            index = next(i+1 for i, sheet in enumerate(sheets) if sheet.attrib["name"] == "კრედოს დაფინანსება")
            sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
            values = {cell.attrib["r"]: cell.find("s:v", ns) for cell in sheet.findall(".//s:c", ns)}
            self.assertEqual(values["D8"].text, "69.00")
            self.assertEqual(values["E8"].text, "2.07")
            self.assertIsNone(values.get("H8"))

    def test_admin_statement_get_is_read_only_and_post_requires_permission_and_confirmation(self):
        self.complete()
        self.user.user_permissions.add(Permission.objects.get(codename="view_credoapplication", content_type__app_label="commerce"))
        self.client.force_login(self.user)
        url = reverse("admin:commerce_credoapplication_statement", args=[self.application.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CredoStatementSettlement.objects.exists())
        data = {key: value for key, value in self.statement_data.items() if key not in {"application_id", "actor"}}
        self.assertEqual(self.client.post(url, {**data, "confirmed": ""}).status_code, 200)
        self.assertFalse(CredoStatementSettlement.objects.exists())
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(CredoStatementSettlement.objects.count(), 1)

    @override_settings(ORDER_RECEIPTS_ENABLED=True)
    def test_credos_scoped_signed_cookie_grants_only_its_confirmed_receipt(self):
        from .credo_access import credo_access_cookie_name, ACCESS_MAX_AGE
        from .receipts import get_or_create_order_receipt, authorize_receipt_request, has_order_receipt_access, ReceiptAccessError, ReceiptUnavailableError
        self.complete()
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        response = HttpResponse()
        name = credo_access_cookie_name(self.application.public_token)
        response.set_signed_cookie(name, str(self.application.public_token), salt="credo-application", max_age=ACCESS_MAX_AGE)
        request.COOKIES[name] = response.cookies[name].value
        self.assertFalse(has_order_receipt_access(self.application.order, request))
        with self.assertRaises(ReceiptUnavailableError): get_or_create_order_receipt(self.application.order)
        self.settle()
        self.application.order.refresh_from_db()
        self.assertTrue(has_order_receipt_access(self.application.order, request))
        receipt = get_or_create_order_receipt(self.application.order)
        authorize_receipt_request(request, receipt)
        self.assertEqual(receipt.document_snapshot["payment"]["method"], "credo")
        self.assertEqual(receipt.document_snapshot["payment"]["amount"], "69.00")
        request.COOKIES[name] = str(self.application.public_token)
        with self.assertRaises(ReceiptAccessError): authorize_receipt_request(request, receipt)

    def test_accountant_can_read_expected_financing_without_a_paid_cash_row(self):
        self.complete()
        self.user.user_permissions.add(Permission.objects.get(codename="view_accounting_report", content_type__app_label="commerce"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounting-report"), {"start": self.period.start.isoformat(), "end": self.period.end.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "66.93")
        self.assertContains(response, "მოსალოდნელი")
        self.assertFalse(PaymentTransaction.objects.exists())
