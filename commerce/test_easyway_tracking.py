from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.management import call_command, CommandError
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .easyway import EasywayClient, EasywayTransportError
from .easyway_tracking import TrackingError, parse_tracking, sync_easyway_tracking
from .models import Order
from .serializers import OrderSummarySerializer


# Actual response shape observed from the user's cancelled test shipment.
OBSERVED_HISTORY = [
    {"status": "new", "created_at": "2026-07-15T14:39:35.000000Z"},
    {"status": "canceled", "created_at": "2026-07-15T15:15:53.000000Z"},
]


def event(status, minute=0):
    return {"status": status, "created_at": f"2026-07-16T12:{minute:02d}:00Z"}


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class TrackingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        static_root = cls.enterClassContext(TemporaryDirectory())
        cls.enterClassContext(override_settings(STATIC_ROOT=static_root))

    def setUp(self):
        self.order = Order.objects.create(
            order_number="ORD-TRACKING-1", subtotal=100, total=110,
            payment_method="card", payment_status="paid", status="confirmed",
            delivery_provider="easyway", easyway_order_id=123,
            easyway_shipment_state="created",
        )
        self.carrier = Mock(spec=EasywayClient)

    def sync(self, events):
        self.carrier.get_tracking.return_value = events
        result = sync_easyway_tracking(self.order.pk, client=self.carrier)
        self.order.refresh_from_db()
        return result

    def test_full_cycle_preserves_confirmation_then_advances_public_status(self):
        expected = [
            ("new", "confirmed"), ("taking", "processing"), ("taken", "shipped"),
            ("in_store", "shipped"), ("taken_store", "shipped"), ("delivered", "delivered"),
        ]
        history = []
        for minute, (carrier_status, public_status) in enumerate(expected):
            history.insert(0, event(carrier_status, minute))
            with self.subTest(carrier_status=carrier_status):
                self.assertEqual(self.sync(history), "synced")
                self.assertEqual(self.order.status, public_status)
                data = OrderSummarySerializer(self.order).data
                self.assertEqual(data["status"], public_status)
                self.assertFalse(any(k.startswith("easyway_tracking") for k in data))
        self.assertEqual(len(self.order.easyway_tracking_history), 6)

    def test_real_cancelled_response_never_cancels_order_or_refunds(self):
        self.assertEqual(self.sync(OBSERVED_HISTORY), "synced")
        self.assertEqual(self.order.easyway_tracking_status, "canceled")
        self.assertEqual(self.order.status, "confirmed")
        self.assertEqual(self.order.payment_status, "paid")
        self.assertIsNone(self.order.stock_restored_at)
        self.assertEqual(self.order.payment_transactions.count(), 0)

    def test_missed_intermediate_steps_can_reach_delivered(self):
        self.sync([event("delivered")])
        self.assertEqual(self.order.status, "delivered")

    def test_repeated_and_stale_history_cannot_regress(self):
        self.sync([event("taken", 5)])
        self.sync([event("new")])
        self.sync([event("taken", 5)])
        self.assertEqual(self.order.status, "shipped")
        self.assertEqual(self.order.easyway_tracking_status, "taken")
        self.assertEqual(len(self.order.easyway_tracking_history), 2)

    def test_newer_taking_cannot_regress_order(self):
        self.sync([event("taken")])
        self.sync([event("taking", 5)])
        self.assertEqual(self.order.status, "shipped")

    def test_unknown_latest_event_is_preserved_without_guessing(self):
        self.assertEqual(self.sync([event("taken"), event("returning", 5)]), "review")
        self.assertEqual(self.order.status, "confirmed")
        self.assertEqual(self.order.easyway_tracking_status, "returning")

    def test_ambiguous_latest_timestamp_does_not_choose_arbitrary_status(self):
        self.assertEqual(self.sync([event("delivered"), event("canceled")]), "review")
        self.assertEqual(self.order.status, "confirmed")
        self.assertEqual(self.order.easyway_tracking_status, "")

    def test_invalid_history_preserves_previous_success_and_releases_lease(self):
        self.sync([event("taken")])
        checked = self.order.easyway_tracking_checked_at
        for payload in ([], {}, [event("new"), {"status": "delivered"}],
                        [{"status": "delivered", "created_at": "2026-07-16T12:00:00"}]):
            with self.subTest(payload=payload), self.assertRaises(TrackingError):
                self.sync(payload)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, "shipped")
            self.assertEqual(self.order.easyway_tracking_checked_at, checked)
            self.assertIsNone(self.order.easyway_tracking_token)

    def test_transport_error_is_safe_and_retryable(self):
        self.carrier.get_tracking.side_effect = EasywayTransportError("secret private data")
        with self.assertRaises(TrackingError):
            sync_easyway_tracking(self.order.pk, client=self.carrier)
        self.order.refresh_from_db()
        self.assertNotIn("secret", self.order.easyway_tracking_error)
        self.assertIsNone(self.order.easyway_tracking_lock_until)

    def test_cancelled_order_and_refund_states_are_not_reactivated(self):
        for status, payment in [("cancelled", "paid"), ("processing", "refunded"),
                                ("processing", "refund_pending"), ("new", "pending")]:
            Order.objects.filter(pk=self.order.pk).update(status=status, payment_status=payment)
            with self.subTest(status=status, payment=payment):
                self.assertEqual(self.sync([event("taken")]), "review")
                self.assertEqual(self.order.status, status)
                self.assertEqual(self.order.payment_status, payment)

    def test_local_cancellation_during_request_wins(self):
        def during_request(_):
            Order.objects.filter(pk=self.order.pk).update(status="cancelled")
            return [event("taken")]
        self.carrier.get_tracking.side_effect = during_request
        self.assertEqual(sync_easyway_tracking(self.order.pk, client=self.carrier), "review")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    def test_shipment_cancellation_during_request_wins(self):
        def during_request(_):
            Order.objects.filter(pk=self.order.pk).update(easyway_shipment_state="cancelled")
            return [event("taken")]
        self.carrier.get_tracking.side_effect = during_request
        self.assertEqual(sync_easyway_tracking(self.order.pk, client=self.carrier), "review")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    def test_stale_admin_form_does_not_erase_active_tracking_lease(self):
        stale_form_instance = Order.objects.get(pk=self.order.pk)
        def during_request(_):
            stale_form_instance.note = "Operator note"
            admin.site._registry[Order].save_model(None, stale_form_instance, None, True)
            return [event("taken")]
        self.carrier.get_tracking.side_effect = during_request
        self.assertEqual(sync_easyway_tracking(self.order.pk, client=self.carrier), "synced")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")
        self.assertEqual(self.order.note, "Operator note")

    def test_overlapping_refresh_is_skipped_before_http(self):
        Order.objects.filter(pk=self.order.pk).update(
            easyway_tracking_token=uuid4(),
            easyway_tracking_lock_until=timezone.now() + timedelta(minutes=3),
        )
        self.assertEqual(sync_easyway_tracking(self.order.pk, client=self.carrier), "skipped")
        self.carrier.get_tracking.assert_not_called()

    def test_expired_lease_is_recoverable(self):
        Order.objects.filter(pk=self.order.pk).update(
            easyway_tracking_token=uuid4(),
            easyway_tracking_lock_until=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(self.sync([event("taken")]), "synced")

    def test_superseded_worker_cannot_write_or_release_new_workers_lease(self):
        replacement = uuid4()
        def during_request(_):
            Order.objects.filter(pk=self.order.pk).update(easyway_tracking_token=replacement)
            return [event("delivered")]
        self.carrier.get_tracking.side_effect = during_request
        self.assertEqual(sync_easyway_tracking(self.order.pk, client=self.carrier), "skipped")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")
        self.assertEqual(self.order.easyway_tracking_token, replacement)

    def test_changed_carrier_id_discards_inflight_response(self):
        def during_request(_):
            Order.objects.filter(pk=self.order.pk).update(easyway_order_id=124)
            return [event("delivered")]
        self.carrier.get_tracking.side_effect = during_request
        self.assertEqual(sync_easyway_tracking(self.order.pk, client=self.carrier), "skipped")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    def test_final_carrier_status_cannot_be_overwritten_by_later_movement(self):
        self.sync([event("canceled")])
        self.assertEqual(self.sync([event("taken", 5)]), "review")
        self.assertEqual(self.order.easyway_tracking_status, "canceled")
        self.assertEqual(self.order.status, "confirmed")

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_scheduler_skips_terminal_unsent_and_internal_shipments(self, factory):
        for fields in [{"delivery_provider": "internal"}, {"easyway_order_id": None},
                       {"easyway_shipment_state": "cancelled"},
                       {"easyway_tracking_status": "delivered"},
                       {"easyway_tracking_status": "canceled"}]:
            Order.objects.filter(pk=self.order.pk).update(
                delivery_provider="easyway", easyway_order_id=123,
                easyway_shipment_state="created", easyway_tracking_status="",
            )
            Order.objects.filter(pk=self.order.pk).update(**fields)
            with self.subTest(fields=fields):
                out = StringIO()
                call_command("sync_easyway_tracking", stdout=out)
                self.assertIn("synced=0", out.getvalue())
        factory.assert_not_called()

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_scheduler_no_orders_makes_no_http_requests(self, factory):
        Order.objects.all().update(easyway_order_id=None)
        call_command("sync_easyway_tracking", stdout=StringIO())
        factory.assert_not_called()

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_scheduler_continues_after_bad_response_and_throttles_repeat(self, factory):
        second = Order.objects.create(
            order_number="ORD-TRACKING-2", subtotal=1, total=1,
            payment_status="paid", delivery_provider="easyway", easyway_order_id=456,
        )
        factory.return_value.get_tracking.side_effect = [[], [event("taken")]]
        with self.assertRaises(CommandError):
            call_command("sync_easyway_tracking", stdout=StringIO(), stderr=StringIO())
        second.refresh_from_db()
        self.assertEqual(second.status, "shipped")
        self.assertEqual(factory.return_value.get_tracking.call_count, 2)
        call_command("sync_easyway_tracking", stdout=StringIO())
        self.assertEqual(factory.return_value.get_tracking.call_count, 2)

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_dry_run_does_not_write_or_call_carrier(self, factory):
        call_command("sync_easyway_tracking", dry_run=True, stdout=StringIO())
        self.order.refresh_from_db()
        self.assertIsNone(self.order.easyway_tracking_attempted_at)
        factory.assert_not_called()

    def test_http_client_uses_only_documented_tracking_get(self):
        http = Mock()
        http.request.return_value.status_code = 200
        http.request.return_value.json.return_value = OBSERVED_HISTORY
        carrier = EasywayClient(api_user="test", api_key="test", api_base_url="https://example.com/api",
                                connect_timeout=5, read_timeout=15, http_client=http)
        self.assertEqual(parse_tracking(carrier.get_tracking(123))[-1]["status"], "canceled")
        self.assertEqual(http.request.call_args.args, ("GET", "https://example.com/api/order/tracking/123"))
        self.assertEqual(http.request.call_args.kwargs["params"], {"lang": "en"})

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_admin_confirmation_post_permissions_and_csrf(self, factory):
        user = get_user_model().objects.create_superuser(
            username="tracking@example.com", email="tracking@example.com", password="Test-only-123"
        )
        self.client.force_login(user)
        url = reverse("admin:commerce_order_easyway_tracking", args=[self.order.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        factory.assert_not_called()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(user)
        self.assertEqual(strict.post(url).status_code, 403)
        factory.assert_not_called()
        factory.return_value.get_tracking.return_value = [event("taken")]
        self.assertEqual(self.client.post(url).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")
        user.is_superuser = False
        user.save()
        user.user_permissions.add(Permission.objects.get(codename="view_order", content_type__app_label="commerce"))
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_admin_order_page_renders_tracking_fields(self):
        user = get_user_model().objects.create_superuser(
            username="tracking-view@example.com", email="tracking-view@example.com", password="Test-only-123"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("admin:commerce_order_change", args=[self.order.pk]))
        self.assertContains(response, "Refresh EasyWay tracking")
        self.assertContains(response, "easyway_tracking_status")


class TrackingConcurrencyTests(TransactionTestCase):
    def test_two_connections_cannot_fetch_same_shipment_at_once(self):
        order = Order.objects.create(
            order_number="ORD-CONCURRENT", subtotal=1, total=1,
            payment_status="paid", delivery_provider="easyway", easyway_order_id=789,
        )
        fetching, release = Event(), Event()
        first_client, second_client = Mock(spec=EasywayClient), Mock(spec=EasywayClient)

        def delayed_response(_):
            fetching.set()
            if not release.wait(10):
                raise AssertionError("Test worker was not released")
            return [event("taken")]

        first_client.get_tracking.side_effect = delayed_response

        def worker():
            try:
                return sync_easyway_tracking(order.pk, client=first_client)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            try:
                self.assertTrue(fetching.wait(10))
                self.assertEqual(sync_easyway_tracking(order.pk, client=second_client), "skipped")
                second_client.get_tracking.assert_not_called()
            finally:
                release.set()
            self.assertEqual(future.result(timeout=10), "synced")
        order.refresh_from_db()
        self.assertEqual(order.status, "shipped")
