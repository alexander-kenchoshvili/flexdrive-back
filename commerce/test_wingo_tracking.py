import copy
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Order, OrderReturn, PaymentTransaction, WingoShipment
from .test_wingo_shipments import WingoShipmentFixture
from .wingo import WingoError, WingoTransportError
from .wingo_tracking import WingoTrackingBusy, WingoTrackingError, sync_shipment
from .wingo_webhook_urls import build_webhook_url, webhook_token
from .wingo_webhooks import MAX_WEBHOOK_BYTES, parse_notification


class WingoTrackingFixture(WingoShipmentFixture):
    def setUp(self):
        super().setUp()
        self.shipment = self.submit()
        self.clock = timezone.now()

    def result_at(self, status=3, seconds=0, **changes):
        return self.result(self.shipment.request_payload, orderStatusId=status,
                           updatedAt=(self.clock + timedelta(seconds=seconds)).isoformat(), **changes)

    def sync(self, status=3, seconds=0, **changes):
        self.carrier.get_order.return_value = self.result_at(status, seconds, **changes)
        result = sync_shipment(self.order.pk, client=self.carrier)
        self.order.refresh_from_db()
        self.shipment.refresh_from_db()
        return result

    def callback_url(self, token=None):
        return reverse("commerce-wingo-webhook", args=[self.order.public_token, token or webhook_token(self.order)])

    def notification(self, status=3, **changes):
        return {"event": "order.status_changed", "timestamp": self.clock.isoformat(), "order": {
            "id": self.shipment.provider_order_id or "internal-wingo-id",
            "orderNumber": self.shipment.tracking_number or "999-1000001",
            "supplierOrderId": self.order.order_number, "orderStatusId": status, **changes}}

    def callback(self, body=None, **kwargs):
        raw = json.dumps(body or self.notification()).encode()
        with patch("commerce.wingo_tracking.WingoClient.from_settings", return_value=self.carrier):
            return self.client.post(self.callback_url(), data=raw, content_type="application/json", **kwargs)


class WingoTrackingTests(WingoTrackingFixture):
    def test_authenticated_statuses_advance_the_existing_order_progress(self):
        for i, (status, expected) in enumerate(((1, "confirmed"), (2, "processing"), (3, "shipped"),
                                                (5, "shipped"), (6, "shipped"), (7, "shipped"), (9, "delivered"))):
            with self.subTest(status=status):
                self.assertEqual(self.sync(status, i), "synced")
                self.assertEqual((self.order.status, self.shipment.carrier_status), (expected, status))
        self.assertEqual(len(self.shipment.tracking_history), 7)
        self.assertEqual(self.shipment.booked_price, 46)
        self.carrier.create_order.assert_called_once()

    def test_duplicate_status_has_one_history_entry_and_no_second_order_write(self):
        self.sync()
        original_order_time = self.order.updated_at
        self.sync()
        self.assertEqual(len(self.shipment.tracking_history), 1)
        self.assertEqual(self.order.updated_at, original_order_time)
        self.assertIsNone(self.shipment.tracking_token)
        self.assertIsNone(self.shipment.tracking_lock_until)

    def test_old_canonical_response_cannot_overwrite_later_progress(self):
        self.sync(9, 10)
        self.assertEqual(self.sync(3, 1), "stale")
        self.assertEqual((self.order.status, self.shipment.carrier_status), ("delivered", 9))
        self.assertEqual(self.shipment.carrier_updated_at, self.clock + timedelta(seconds=10))

    def test_equal_provider_time_with_conflicting_status_needs_review(self):
        self.sync(3)
        self.assertEqual(self.sync(9), "review")
        self.assertEqual((self.order.status, self.shipment.carrier_status), ("shipped", 3))
        self.assertTrue(self.shipment.tracking_error)

    def test_delivered_cannot_revert_even_with_newer_provider_time(self):
        self.sync(9)
        self.assertEqual(self.sync(3, 1), "review")
        self.assertEqual((self.order.status, self.shipment.carrier_status), ("delivered", 9))

    def test_delays_cancel_and_return_never_refund_restock_or_cancel_order(self):
        before = Order.objects.values().get(pk=self.order.pk)
        for i, status in enumerate((8, 4, 10, 11)):
            self.assertEqual(self.sync(status, i), "review")
            self.assertEqual(before, Order.objects.values().get(pk=self.order.pk))
            self.assertEqual(self.shipment.state, "created")
        self.assertFalse(OrderReturn.objects.exists())
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_return_after_delivery_is_visible_without_undoing_delivery_or_money(self):
        self.sync(9)
        self.assertEqual(self.sync(11, 1), "review")
        self.assertEqual((self.order.status, self.order.payment_status, self.order.total), ("delivered", "paid", 146))
        self.assertEqual(self.shipment.carrier_status, 11)
        self.assertFalse(OrderReturn.objects.exists())

    def test_canonical_regression_keeps_customer_progress_forward(self):
        self.sync(3)
        self.assertEqual(self.sync(2, 1), "review")
        self.assertEqual(self.order.status, "shipped")
        self.assertEqual(self.shipment.carrier_status, 2)

    def test_unpaid_cancelled_or_returning_orders_do_not_advance(self):
        for changes in ({"payment_status": "refund_pending"}, {"status": "cancelled"}):
            old = {key: getattr(self.order, key) for key in changes}
            self.change_order(**changes)
            self.assertEqual(self.sync(9), "review")
            for key, expected in changes.items():
                self.assertEqual(getattr(self.order, key), expected)
            self.change_order(**old)
        OrderReturn.objects.create(order=self.order, disposition="not_purchased", receipt_status="not_required")
        self.assertEqual(self.sync(9), "review")
        self.assertEqual(self.order.status, "confirmed")

    def test_bad_current_response_preserves_last_good_status_and_sanitizes_errors(self):
        self.sync(3)
        for changes in ({"id": "different"}, {"userId": "foreign"}, {"supplierOrderId": "other"},
                        {"orderNumber": "999-2000000"}, {"recipientPaymentDue": 9},
                        {"orderStatusId": 999}, {"orderStatusId": True}, {"updatedAt": "bad"},
                        {"updatedAt": "2026-11-10T01:00:00"}):
            self.carrier.get_order.return_value = {**self.result_at(9, 1), **changes}
            with self.subTest(changes=changes), self.assertRaises(WingoTrackingError):
                sync_shipment(self.order.pk, client=self.carrier)
            self.shipment.refresh_from_db()
            self.assertEqual(self.shipment.carrier_status, 3)
            self.assertNotIn("foreign", self.shipment.tracking_error)
            self.assertIsNone(self.shipment.tracking_token)

    def test_timeout_and_unknown_exception_keep_last_state_and_release_lease(self):
        self.sync(3)
        for error in (WingoTransportError(), RuntimeError("private-key recipient-phone")):
            self.carrier.get_order.side_effect = error
            with self.assertRaises(WingoTrackingError) as caught:
                sync_shipment(self.order.pk, client=self.carrier)
            self.shipment.refresh_from_db()
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(self.shipment.carrier_status, 3)
            self.assertIsNone(self.shipment.tracking_token)

    def test_account_change_blocks_get_before_network(self):
        with override_settings(WINGO_MERCHANT_USER_ID="another-account"), self.assertRaises(WingoTrackingError):
            sync_shipment(self.order.pk, client=self.carrier)
        self.carrier.get_order.assert_not_called()

    def test_parallel_check_is_busy_without_another_provider_call(self):
        WingoShipment.objects.filter(pk=self.shipment.pk).update(
            tracking_token=uuid4(), tracking_lock_until=timezone.now() + timedelta(seconds=30))
        with self.assertRaises(WingoTrackingBusy):
            sync_shipment(self.order.pk, client=self.carrier)
        self.carrier.get_order.assert_not_called()

    def test_expired_lease_can_be_reclaimed(self):
        WingoShipment.objects.filter(pk=self.shipment.pk).update(
            tracking_token=uuid4(), tracking_lock_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.sync(), "synced")
        self.assertIsNone(self.shipment.tracking_token)

    def test_late_response_cannot_overwrite_newer_lease_or_its_result(self):
        winner = uuid4()
        def late(_):
            WingoShipment.objects.filter(pk=self.shipment.pk).update(tracking_token=winner,
                carrier_status=9, carrier_updated_at=self.clock + timedelta(seconds=5))
            return self.result_at(3)
        self.carrier.get_order.side_effect = late
        self.assertEqual(sync_shipment(self.order.pk, client=self.carrier), "skipped")
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.carrier_status, 9)
        self.assertEqual(self.shipment.tracking_token, winner)

    def test_tracking_retains_price_and_private_frozen_request(self):
        before = copy.deepcopy(self.shipment.request_payload)
        self.sync(3, serviceFee=99)
        self.assertEqual(self.shipment.booked_price, 46)
        self.assertEqual(self.shipment.request_payload, before)
        self.assertEqual((self.order.delivery_price, self.order.total), (46, 146))

    def test_pending_notification_is_not_cleared_by_an_older_inflight_check(self):
        def during_get(_):
            WingoShipment.objects.filter(pk=self.shipment.pk).update(webhook_received_at=timezone.now())
            return self.result_at(3)
        self.carrier.get_order.side_effect = during_get
        sync_shipment(self.order.pk, client=self.carrier)
        self.shipment.refresh_from_db()
        self.assertIsNotNone(self.shipment.webhook_received_at)
        self.assertIsNone(self.shipment.webhook_checked_at)
        self.carrier.get_order.side_effect = None
        self.assertEqual(self.sync(3), "synced")
        self.assertEqual(self.shipment.webhook_checked_at, self.shipment.webhook_received_at)

    def test_history_has_a_bounded_size(self):
        WingoShipment.objects.filter(pk=self.shipment.pk).update(tracking_history=[
            {"status": 1, "observed_at": f"old-{i}"} for i in range(1000)])
        self.sync(3)
        self.assertEqual(len(self.shipment.tracking_history), 1000)
        self.assertEqual(self.shipment.tracking_history[-1]["status"], 3)


class WingoWebhookTests(WingoTrackingFixture):
    def test_private_post_requires_no_browser_login_or_csrf_but_verifies_current_api(self):
        self.client = Client(enforce_csrf_checks=True)
        self.carrier.get_order.return_value = self.result_at(3)
        response = self.callback()
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")
        self.carrier.get_order.assert_called_once_with("internal-wingo-id")
        self.carrier.create_order.assert_called_once()  # fixture booking, no callback POST

    def test_payload_status_is_a_hint_not_an_authority(self):
        self.carrier.get_order.return_value = self.result_at(2)
        self.assertEqual(self.callback(self.notification(status=9)).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "processing")

    def test_repeated_notifications_have_one_effect(self):
        self.carrier.get_order.return_value = self.result_at(9)
        for _ in range(2):
            self.assertEqual(self.callback().status_code, 200)
        self.shipment.refresh_from_db()
        self.assertEqual(len(self.shipment.tracking_history), 1)

    def test_wrong_or_public_only_token_never_queries_provider(self):
        raw = json.dumps(self.notification())
        for token in ("wrong", str(self.order.public_token), "a" * 64):
            response = self.client.post(self.callback_url(token), data=raw, content_type="application/json")
            self.assertEqual(response.status_code, 404)
        self.carrier.get_order.assert_not_called()
        self.shipment.refresh_from_db()
        self.assertIsNone(self.shipment.webhook_received_at)

    def test_signing_key_rotation_accepts_explicit_fallback_only(self):
        old_url = self.callback_url()
        from django.conf import settings
        old_key = settings.SECRET_KEY
        self.carrier.get_order.return_value = self.result_at(3)
        raw = json.dumps(self.notification())
        with override_settings(SECRET_KEY="new-key", SECRET_KEY_FALLBACKS=[]):
            self.assertEqual(self.client.post(old_url, data=raw, content_type="application/json").status_code, 404)
        with override_settings(SECRET_KEY="new-key", SECRET_KEY_FALLBACKS=[old_key]), \
                patch("commerce.wingo_tracking.WingoClient.from_settings", return_value=self.carrier):
            self.assertEqual(self.client.post(old_url, data=raw, content_type="application/json").status_code, 200)

    def test_foreign_notification_cannot_pick_a_different_api_record(self):
        for changes in ({"id": "other-id"}, {"supplierOrderId": "OTHER"}, {"orderNumber": "999-9999999"}):
            self.assertEqual(self.callback(self.notification(**changes)).status_code, 503)
        self.carrier.get_order.assert_not_called()

    def test_error_returns_retry_instead_of_acknowledging_lost_update(self):
        self.carrier.get_order.side_effect = WingoTransportError()
        response = self.callback()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "3")
        self.shipment.refresh_from_db()
        self.assertIsNotNone(self.shipment.webhook_received_at)
        self.assertIsNone(self.shipment.webhook_checked_at)
        self.assertTrue(self.shipment.tracking_error)
        self.carrier.get_order.side_effect = None
        self.carrier.get_order.return_value = self.result_at(9)
        self.assertEqual(self.callback().status_code, 200)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.webhook_received_at, self.shipment.webhook_checked_at)

    def test_busy_notification_stays_pending_and_is_retryable(self):
        WingoShipment.objects.filter(pk=self.shipment.pk).update(
            tracking_token=uuid4(), tracking_lock_until=timezone.now() + timedelta(seconds=30))
        self.assertEqual(self.callback().status_code, 503)
        self.shipment.refresh_from_db()
        self.assertIsNotNone(self.shipment.webhook_received_at)
        self.assertIsNone(self.shipment.webhook_checked_at)
        self.carrier.get_order.assert_not_called()

    def test_creation_callback_can_recover_a_timed_out_submission_without_new_post(self):
        self.shipment.delete()
        self.unknown()
        self.shipment = WingoShipment.objects.get(order=self.order)
        self.carrier.get_order.return_value = self.result_at(3)
        self.assertEqual(self.callback().status_code, 200)
        self.shipment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.shipment.state, self.order.status), ("created", "shipped"))
        self.assertEqual(self.shipment.provider_order_id, "internal-wingo-id")
        self.assertEqual(self.carrier.create_order.call_count, 2)  # setup success + one uncertain POST

    @override_settings(WINGO_WEBHOOK_SECRET="agreed-hook-secret")
    def test_optional_hmac_is_checked_on_raw_bytes_when_configured(self):
        raw = json.dumps(self.notification()).encode()
        self.carrier.get_order.return_value = self.result_at(3)
        for signature in ("", "sha256=wrong"):
            response = self.client.post(self.callback_url(), data=raw, content_type="application/json",
                                        HTTP_X_WINGO_SIGNATURE=signature)
            self.assertEqual(response.status_code, 403)
        self.carrier.get_order.assert_not_called()
        signature = "sha256=" + hmac.new(b"agreed-hook-secret", raw, hashlib.sha256).hexdigest()
        with patch("commerce.wingo_tracking.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.callback_url(), data=raw, content_type="application/json",
                                        HTTP_X_WINGO_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)

    def test_bad_body_content_type_header_and_oversize_never_query_provider(self):
        for raw in (b"not json", b"[]", b"{}", b'{"event":"a","event":"b"}', b"{" + b" " * MAX_WEBHOOK_BYTES):
            response = self.client.post(self.callback_url(), data=raw, content_type="application/json")
            self.assertIn(response.status_code, {400, 413})
        response = self.callback(HTTP_X_WINGO_EVENT="order.created")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(self.callback_url(), data="{}", content_type="text/plain").status_code, 415)
        self.assertEqual(self.client.get(self.callback_url()).status_code, 405)
        self.carrier.get_order.assert_not_called()

    def test_malformed_dates_duplicate_keys_and_boolean_status_are_rejected(self):
        for timestamp in (None, "bad", "2026-11-10T01:00:00"):
            body = self.notification()
            body["timestamp"] = timestamp
            with self.assertRaises(ValueError):
                parse_notification(json.dumps(body))
        body = self.notification(orderStatusId=True)
        with self.assertRaises(ValueError):
            parse_notification(json.dumps(body))
        with self.assertRaises(ValueError):
            parse_notification('{"event":"order.created","event":"order.status_changed"}')
        with self.assertRaises(ValueError):
            parse_notification('{"event":"order.created","value":NaN}')

    @override_settings(WINGO_WEBHOOK_PUBLIC_URL="https://backend.example/api/commerce/wingo/webhook/")
    def test_booking_supplies_private_callback_url_without_provider_profile_edit(self):
        payload = self.payload()
        self.assertEqual(payload["callback_url"], "https://backend.example" + self.callback_url())
        self.assertNotIn(str(self.order.public_token), payload["supplierOrderId"])

    def test_bad_public_url_fails_before_booking(self):
        for value in ("http://backend.example/api/commerce/wingo/webhook", "https://user:pass@backend.example/api/commerce/wingo/webhook",
                      "https://backend.example/wrong", "https://backend.example/api/commerce/wingo/webhook?secret=1"):
            with self.subTest(value=value), override_settings(WINGO_WEBHOOK_PUBLIC_URL=value), self.assertRaises(WingoError):
                build_webhook_url(self.order)

    @override_settings(WINGO_WEBHOOK_PUBLIC_URL="", WINGO_ACCOUNT_MODE="production")
    def test_production_cannot_silently_create_orders_without_callbacks(self):
        with self.assertRaises(WingoError):
            build_webhook_url(self.order)

    def test_short_verification_timeouts_are_separate_from_booking_timeouts(self):
        self.carrier.get_order.return_value = self.result_at(3)
        with patch("commerce.wingo_tracking.WingoClient.from_settings", return_value=self.carrier) as factory:
            sync_shipment(self.order.pk)
        factory.assert_called_once_with(connect_timeout=2, read_timeout=4)

    def test_profiles_guest_lookup_and_public_summary_show_updated_order_status(self):
        self.carrier.get_order.return_value = self.result_at(9)
        self.assertEqual(self.callback().status_code, 200)
        summary = self.client.get(reverse("commerce-order-summary", args=[self.order.public_token]))
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["status"], "delivered")
        with patch("commerce.views.validate_recaptcha", return_value=True):
            lookup = self.client.post(reverse("commerce-order-lookup"), data=json.dumps({
                "order_number": self.order.order_number, "phone": self.order.phone,
                "recaptcha_token": "test-lookup-token"}), content_type="application/json")
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json()["status"], "delivered")
        owner = get_user_model().objects.create_user(username="wingo-owner", email="owner@example.com", password="password")
        self.change_order(user=owner)
        authenticated = APIClient()
        authenticated.force_authenticate(user=owner)
        detail = authenticated.get(reverse("commerce-order-detail", args=[self.order.public_token]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["status"], "delivered")
        listing = authenticated.get(reverse("commerce-order-list"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"][0]["status"], "delivered")
        for body in (summary.json(), lookup.json(), detail.json()):
            for value in ("tracking_history", "callback_url", "merchant-test-id", "internal-wingo-id"):
                self.assertNotIn(value, str(body))

    def test_neighboring_courier_paths_and_guest_lookup_still_require_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        for path in ("/api/commerce/wingo/webhook/unregistered/", "/api/commerce/wingo/other/",
                     reverse("commerce-order-lookup")):
            self.assertEqual(strict.post(path, data="{}", content_type="application/json").status_code, 403)


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class WingoTrackingAdminTests(WingoTrackingFixture):
    def setUp(self):
        super().setUp()
        self.operator = get_user_model().objects.create_superuser(username="tracking-admin", email="admin@example.com", password="password")
        self.client.force_login(self.operator)
        self.url = reverse("admin:commerce_order_wingo_tracking", args=[self.order.pk])

    def test_georgian_button_and_get_confirmation_make_no_provider_calls(self):
        page = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertContains(page, "Wingo-ს სტატუსის განახლება")
        page = self.client.get(self.url)
        self.assertContains(page, "მიმდინარე სტატუსის შემოწმება")
        self.assertNotContains(page, "Wingo-ში გაგზავნის დადასტურება")
        self.carrier.get_order.assert_not_called()

    def test_post_checks_status_and_overview_shows_history_and_time(self):
        self.carrier.get_order.return_value = self.result_at(3)
        with patch("commerce.wingo_tracking.WingoClient.from_settings", return_value=self.carrier):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, "აღებულია")
        self.assertContains(response, "ბოლო წარმატებული შემოწმება")
        self.assertContains(response, "ბოლო 20 დაკვირვება")
        self.carrier.get_order.assert_called_once()

    def test_unprocessed_notification_is_visible_to_operator(self):
        WingoShipment.objects.filter(pk=self.shipment.pk).update(webhook_received_at=timezone.now())
        page = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertContains(page, "მიღებული შეტყობინება ჯერ ვერ გადამოწმდა")

    def test_csrf_view_only_and_http_methods_cannot_change_status(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.operator)
        self.assertEqual(strict.post(self.url).status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        viewer = get_user_model().objects.create_user(username="tracking-viewer", email="viewer@example.com", password="password", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_order", content_type__app_label="commerce"))
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.carrier.get_order.assert_not_called()


class WingoTrackingMigrationTests(TransactionTestCase):
    def test_new_tracking_fields_preserve_frozen_booking_and_start_empty(self):
        name = str(connection.settings_dict["NAME"])
        assert connection.vendor == "sqlite" and (name == ":memory:" or (name.startswith("file:memorydb_") and "mode=memory" in name))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([("commerce", "0042_wingo_outbound_shipment")])
            apps = executor.loader.project_state([("commerce", "0042_wingo_outbound_shipment")]).apps
            OldOrder = apps.get_model("commerce", "Order")
            OldShipment = apps.get_model("commerce", "WingoShipment")
            order = OldOrder.objects.create(order_number="MIGRATION-WINGO", subtotal=100, total=146)
            payload = {"supplierOrderId": order.order_number, "userId": "test-merchant", "recipientPaymentDue": 0}
            shipment = OldShipment.objects.create(order=order, state="unknown", parcel_count=2,
                booked_price=46, request_payload=payload, operation_token=uuid4(), attempted_at=timezone.now())
            before = OldShipment.objects.values().get(pk=shipment.pk)
            MigrationExecutor(connection).migrate([("commerce", "0043_wingo_tracking")])
            after = WingoShipment.objects.values().get(pk=shipment.pk)
            self.assertEqual(before, {key: after[key] for key in before})
            self.assertEqual(after["tracking_history"], [])
            self.assertEqual(after["tracking_error"], "")
            self.assertIsNone(after["carrier_updated_at"])
            self.assertIsNone(after["webhook_received_at"])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

