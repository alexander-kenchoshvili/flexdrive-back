"""Carrier-panel operations stay separate from physical receipt and bank money."""
from datetime import timedelta
from decimal import Decimal as D
from io import BytesIO
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
from uuid import uuid4
from zipfile import ZipFile

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import test_bog_refunds as fixtures
from .accounting_export import export_response
from .accounting_ledger import build_ledger
from .accounting_reports import ReportPeriod, build_cash_report
from .bog_refunds import can_request_bog_full_refund, reconcile_bog_refund_details, request_bog_full_refund
from .courier_state import has_unsettled_courier_shipment
from .models import Order, OrderReturn, OwnedStockLot, PaymentTransaction, WingoShipment
from .returns import prepare_order_return, receive_order_return
from .wingo import WingoClient, WingoTransportError
from .wingo_tracking import WingoTrackingError, sync_shipment
from business.reports import build_dashboard_report


@override_settings(WINGO_MERCHANT_USER_ID="merchant-test-id", STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class WingoPlatformReturnTests(TestCase):
    _details = fixtures.BogRefundFlowTests._details

    def setUp(self):
        fixtures.BogRefundFlowTests.setUp(self)
        self.order.delivery_provider = "wingo"
        self.order.total = D(110)
        self.order.delivery_price = self.order.carrier_delivery_cost = D(10)
        self.order.save()
        self.sale.amount = D(110)
        self.sale.save(update_fields=["amount"])
        self.client.refund_partial.return_value = self.client.refund_full.return_value
        self.clock = timezone.now()
        self.payload = {"userId": "merchant-test-id", "supplierOrderId": self.order.order_number,
            "recipientName": "Nino Beridze", "recipientPhone": "+995555123456", "regionId": "region-id",
            "localityId": "locality-id", "deliveryAddress": "Tbilisi, Saburtalo 1", "pickupAddress": "Store",
            "deliveryTypeId": 1, "packageCount": 1, "weightRangeId": 1, "recipientPaymentDue": 0}
        self.shipment = WingoShipment.objects.create(order=self.order, state="created",
            provider_order_id="wingo-id", tracking_number="999-1000001", submitted_at=self.clock,
            booked_price=10, request_payload=self.payload, account_mode="test", api_base_url="https://wingo.example/api/v1")
        self.carrier = Mock(spec=WingoClient, account_mode="test", api_base_url="https://wingo.example/api/v1")
        self.order_url = reverse("admin:commerce_order_change", args=[self.order.pk])
        self.refund_url = reverse("admin:commerce_order_bog_refund", args=[self.order.pk])
        self.start_url = reverse("admin:commerce_order_return_start", args=[self.order.pk])
        self.receive_url = reverse("admin:commerce_order_return_receive", args=[self.order.pk])
        self.tracking_url = reverse("admin:commerce_order_wingo_tracking", args=[self.order.pk])
        day = timezone.localdate()
        self.period = ReportPeriod(day - timedelta(days=1), day + timedelta(days=1))

    def sync(self, status=10, seconds=0, **changes):
        self.carrier.get_order.return_value = {**self.payload, "id": "wingo-id", "orderNumber": "999-1000001",
            "orderStatusId": status, "updatedAt": (self.clock + timedelta(seconds=seconds)).isoformat(), **changes}
        result = sync_shipment(self.order.pk, client=self.carrier)
        self.order.refresh_from_db()
        self.shipment.refresh_from_db()
        return result

    def start(self):
        self.sync(9)
        response = self.admin_client.post(self.start_url, {"confirm": "on", "wingo_return_tracking_number": "999-2000001"})
        self.assertEqual(response.status_code, 302)
        return OrderReturn.objects.get(order=self.order)

    def receive(self, case):
        line = case.lines.get()
        response = self.admin_client.post(self.receive_url,
            {"confirm": "on", f"saleable_{line.pk}": 1, f"unsaleable_{line.pk}": 0})
        self.assertEqual(response.status_code, 302)

    def refund_form(self, *, payer="customer"):
        return {"confirm": "on", "return_delivery_payer": payer, "return_delivery_cost": "10.00",
            "customer_agreed": "on", "deduction_reason": "მომხმარებელს შეეშალა"}

    def test_panel_cancel_needs_canonical_confirmation_then_separate_bank_action(self):
        page = self.admin_client.get(self.refund_url)
        self.assertContains(page, "გააუქმეთ გზავნილი Wingo-ს პანელში")
        self.assertNotContains(page, "გამოიყენეთ შეკვეთაზე „RedCap გზავნილის გაუქმება“")
        self.assertFalse(can_request_bog_full_refund(self.order))
        self.sync()
        self.assertIsNotNone(self.shipment.cancellation_verified_at)
        self.assertFalse(has_unsettled_courier_shipment(self.order))
        self.assertTrue(can_request_bog_full_refund(self.order))
        self.assertEqual((self.order.status, self.order.payment_status), ("new", "paid"))
        self.assertFalse(OrderReturn.objects.exists())
        self.assertFalse(OwnedStockLot.objects.exists())
        self.client.refund_full.assert_not_called()
        page = self.admin_client.get(self.order_url)
        self.assertContains(page, self.refund_url)
        self.assertContains(page, "გაუქმება დადასტურებულია")
        self.assertNotContains(page, "სტიკერის გახსნა / ბეჭდვა")
        request_bog_full_refund(order=self.order, requested_by=self.admin_user, client=self.client,
            disposition="on_hand", not_dispatched=True)
        self.client.refund_full.assert_called_once()
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 1)
        details = self._details(status="refunded", refund_amount=110, action_amount=D(110))
        for _ in range(2):
            reconcile_bog_refund_details(self.sale, details, provider_reference={"source": "verified_details"})
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ("cancelled", "refunded"))
        self.assertEqual(OwnedStockLot.objects.count(), 1)

    def test_status_number_without_verification_unknown_and_failed_reads_still_block(self):
        WingoShipment.objects.filter(pk=self.shipment.pk).update(carrier_status=10)
        self.assertTrue(has_unsettled_courier_shipment(self.order))
        self.sync()
        self.carrier.get_order.side_effect = WingoTransportError()
        with self.assertRaises(WingoTrackingError):
            sync_shipment(self.order.pk, client=self.carrier)
        self.assertTrue(has_unsettled_courier_shipment(self.order))
        self.client.refund_full.assert_not_called()

    def test_inflight_or_pending_notification_blocks_refund_even_after_cancel(self):
        self.sync()
        for values in ({"tracking_token": uuid4()}, {"webhook_received_at": self.clock + timedelta(minutes=1)}):
            with self.subTest(values=values):
                WingoShipment.objects.filter(pk=self.shipment.pk).update(**values)
                self.assertFalse(can_request_bog_full_refund(self.order))
                with self.assertRaises(ValidationError):
                    request_bog_full_refund(order=self.order, requested_by=self.admin_user, client=self.client,
                        disposition="on_hand", not_dispatched=True)
                WingoShipment.objects.filter(pk=self.shipment.pk).update(tracking_token=None, webhook_received_at=None)
        self.assertFalse(OrderReturn.objects.exists())
        self.client.refund_full.assert_not_called()

    def test_old_or_conflicting_response_cannot_unlock_refund(self):
        self.sync(1, 10)
        self.assertEqual(self.sync(10, 1), "stale")
        self.assertTrue(has_unsettled_courier_shipment(self.order))
        self.assertEqual(self.sync(10, 10), "review")
        self.assertTrue(has_unsettled_courier_shipment(self.order))
        self.assertEqual(self.sync(10, 11), "synced")
        self.assertFalse(has_unsettled_courier_shipment(self.order))
        self.assertEqual(self.sync(1, 12), "review")
        self.assertTrue(has_unsettled_courier_shipment(self.order))

    def test_stale_observation_does_not_revoke_newer_cancellation_but_pickup_cancel_is_insufficient(self):
        self.assertEqual(self.sync(4, 1), "review")
        self.assertTrue(has_unsettled_courier_shipment(self.order))
        self.sync(10, 2)
        self.assertEqual(self.sync(1, 0), "stale")
        self.assertFalse(has_unsettled_courier_shipment(self.order))

    def test_foreign_cancellation_cannot_release_guard(self):
        with self.assertRaises(WingoTrackingError):
            self.sync(10, recipientName="Someone else")
        self.assertTrue(has_unsettled_courier_shipment(self.order))
        self.assertFalse(PaymentTransaction.objects.filter(action="refund").exists())

    def test_cancel_after_physical_dispatch_needs_receipt_not_direct_refund(self):
        self.sync(3)
        self.assertEqual(self.sync(10, 1), "review")
        self.assertIsNone(self.shipment.cancellation_verified_at)
        self.assertFalse(can_request_bog_full_refund(self.order))
        with self.assertRaises(ValidationError):
            prepare_order_return(order=self.order, disposition="on_hand", actor=self.admin_user)
        self.assertFalse(OrderReturn.objects.exists())

    def test_start_requires_new_tracking_number_and_explicit_panel_confirmation(self):
        self.sync(9)
        page = self.admin_client.get(self.start_url)
        self.assertContains(page, "Wingo-ს უკუგზავნილის ნომერი")
        self.assertFalse(OrderReturn.objects.exists())
        for data in ({"confirm": "on"}, {"wingo_return_tracking_number": "999-2000001"},
                     {"confirm": "on", "wingo_return_tracking_number": "999-1000001"}):
            self.assertEqual(self.admin_client.post(self.start_url, data).status_code, 200)
            self.assertFalse(OrderReturn.objects.exists())
        with self.assertRaises(ValidationError):
            prepare_order_return(order=self.order, disposition="from_customer", actor=self.admin_user)
        self.carrier.create_order.assert_not_called()

    def test_start_is_idempotent_and_number_cannot_be_replaced_or_reused(self):
        case = self.start()
        for _ in range(2):
            same = prepare_order_return(order=self.order, disposition="from_customer", actor=self.admin_user,
                wingo_return_tracking_number=case.wingo_return_tracking_number)
            self.assertEqual(same.pk, case.pk)
        with self.assertRaises(ValidationError):
            prepare_order_return(order=self.order, disposition="from_customer", actor=self.admin_user,
                wingo_return_tracking_number="999-2000002")
        other = Order.objects.create(order_number="OTHER-RETURN", delivery_provider="wingo", status="delivered",
            payment_status="paid", subtotal=100, total=110)
        # Product identity is checked before insertion, so create its order line.
        item = self.order.items.get()
        item.pk = None
        item.order = other
        item.save()
        with self.assertRaisesMessage(ValidationError, "უკვე სხვა შეკვეთას"):
            prepare_order_return(order=other, disposition="from_customer", actor=self.admin_user,
                wingo_return_tracking_number=case.wingo_return_tracking_number)
        self.assertEqual(OrderReturn.objects.count(), 1)
        self.assertFalse(OwnedStockLot.objects.exists())
        self.assertFalse(can_request_bog_full_refund(self.order))
        page = self.admin_client.get(self.order_url)
        self.assertContains(page, "999-2000001")
        self.assertContains(page, self.receive_url)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.order.pk), change_message__contains="999-2000001").exists())

    def test_customer_pays_110_less_both_tens_refunds_90_after_receipt(self):
        case = self.start()
        with self.assertRaises(ValidationError):
            request_bog_full_refund(order=self.order, requested_by=self.admin_user, client=self.client,
                disposition="from_customer")
        self.receive(case)
        self.receive(case)
        self.product.refresh_from_db()
        self.assertEqual(self.product.owned_stock_qty, 1)
        page = self.admin_client.get(self.refund_url)
        self.assertNotContains(page, 'name="return_delivery_cost" value="0"')
        preview = self.admin_client.post(self.refund_url, self.refund_form())
        self.assertContains(preview, "90.00 ₾")
        self.client.refund_partial.assert_not_called()
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            response = self.admin_client.post(self.refund_url, {**self.refund_form(), "execute": "yes",
                "preview_token": preview.context_data["preview_token"]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.refund_partial.call_args.kwargs["amount"], D(90))
        details = self._details(status="refunded_partially", refund_amount=90, action="partial_refund", action_amount=D(90))
        for _ in range(2):
            reconcile_bog_refund_details(self.sale, details, provider_reference={"source": "verified_details"})
        cash = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((cash["refunded"], cash["retained_delivery_fee"], cash["retained_return_fee"],
                          cash["return_delivery_cost"]), (D(90), D(10), D(10), D(10)))
        summary = build_dashboard_report(self.period)["summary"]
        self.assertEqual((summary["refunded"], summary["return_delivery_cost"]), ("90.00", "10.00"))
        ledger = build_ledger(self.period, "refunded")
        self.assertEqual((ledger["totals"][14], ledger["totals"][18], ledger["totals"][22]), (D(90), D(10), D(10)))
        ledger["show_purchase"] = True
        exported = export_response(ledger)
        with ZipFile(BytesIO(exported.content)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for cell, amount in (("O8", 90), ("S8", 10), ("T8", 10), ("W8", 10), ("W9", 10)):
                self.assertEqual(D(sheet.find(f'.//s:c[@r="{cell}"]/s:v', ns).text), D(amount))
        html = self.admin_client.get(reverse("accounting-report"), {"period_mode": "days", "status": "refunded",
            "start": self.period.start, "end": self.period.end})
        self.assertContains(html, "პირველი მიტანისთვის დაქვითული")
        self.assertIn(("დაბრუნებული თანხა", "90.00"), html.context["groups"][0]["delivery"])
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ("cancelled", "partially_refunded"))
        self.assertEqual(OrderReturn.objects.get().wingo_return_tracking_number, "999-2000001")
        self.assertEqual((OwnedStockLot.objects.count(), PaymentTransaction.objects.filter(action="refund").count()), (1, 1))
        self.carrier.create_order.assert_not_called()

    def test_merchant_pays_returns_full_110_and_keeps_return_expense(self):
        case = self.start()
        self.receive(case)
        preview = self.admin_client.post(self.refund_url, self.refund_form(payer="merchant"))
        self.assertContains(preview, "110.00 ₾")
        with patch("commerce.bog_refunds.BogPaymentsClient.from_settings", return_value=self.client):
            self.admin_client.post(self.refund_url, {**self.refund_form(payer="merchant"), "execute": "yes",
                "preview_token": preview.context_data["preview_token"]})
        self.client.refund_full.assert_called_once()
        self.client.refund_partial.assert_not_called()
        details = self._details(status="refunded", refund_amount=110, action_amount=D(110))
        reconcile_bog_refund_details(self.sale, details, provider_reference={"source": "verified_details"})
        cash = build_cash_report(self.period)["currencies"]["GEL"]
        self.assertEqual((cash["refunded"], cash["retained_delivery_fee"], cash["retained_return_fee"],
                          cash["return_delivery_cost"]), (D(110), D(0), D(0), D(10)))

    def test_actions_require_change_permission_csrf_and_safe_methods(self):
        self.sync(9)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin_user)
        self.assertEqual(strict.post(self.start_url, {"confirm": "on"}).status_code, 403)
        for url in (self.start_url, self.receive_url, self.refund_url):
            self.assertEqual(self.admin_client.put(url, data="{}", content_type="application/json").status_code, 405)
        self.admin_user.is_superuser = False
        self.admin_user.save(update_fields=["is_superuser"])
        self.admin_user.user_permissions.add(Permission.objects.get(codename="view_order", content_type__app_label="commerce"))
        for url in (self.start_url, self.receive_url, self.refund_url, self.tracking_url):
            self.assertEqual(self.admin_client.post(url, {"confirm": "on"}).status_code, 403)
        self.assertFalse(OrderReturn.objects.exists())
        self.client.refund_full.assert_not_called()


class WingoPlatformMigrationTests(TransactionTestCase):
    def test_old_cancellations_are_not_implicitly_verified_and_returns_survive(self):
        name = str(connection.settings_dict["NAME"])
        assert connection.vendor == "sqlite" and (name == ":memory:" or (name.startswith("file:memorydb_") and "mode=memory" in name))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([("commerce", "0043_wingo_tracking")])
            apps = executor.loader.project_state([("commerce", "0043_wingo_tracking")]).apps
            order = apps.get_model("commerce", "Order").objects.create(order_number="HISTORICAL-RETURN", subtotal=100, total=110)
            OldShipment = apps.get_model("commerce", "WingoShipment")
            OldReturn = apps.get_model("commerce", "OrderReturn")
            shipment = OldShipment.objects.create(order=order, state="created", provider_order_id="old-id",
                tracking_number="999-OLD", submitted_at=timezone.now(), carrier_status=10,
                tracking_history=[{"status": 10, "result": "review"}], request_payload={"supplierOrderId": order.order_number})
            case = OldReturn.objects.create(order=order, disposition="from_customer", receipt_status="awaiting")
            before_shipment = OldShipment.objects.values().get(pk=shipment.pk)
            before_case = OldReturn.objects.values().get(pk=case.pk)
            MigrationExecutor(connection).migrate([("commerce", "0044_wingo_platform_returns")])
            after_shipment = WingoShipment.objects.values().get(pk=shipment.pk)
            after_case = OrderReturn.objects.values().get(pk=case.pk)
            self.assertEqual(before_shipment, {key: after_shipment[key] for key in before_shipment})
            self.assertEqual(before_case, {key: after_case[key] for key in before_case})
            self.assertIsNone(after_shipment["cancellation_verified_at"])
            self.assertIsNone(after_case["wingo_return_tracking_number"])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
