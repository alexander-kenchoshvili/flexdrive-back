from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .redcap_quotes import (DeliveryQuoteError, build_delivery_quote, delivery_locations,
                             delivery_order_fields, resolve_delivery_location, validate_delivery_quote)
from .models import Order, OrderItem, RedcapReferenceData, RedcapShipment, RedcapSyncReport
from .redcap import RedcapClient, RedcapResponseError, RedcapTransportError
from .redcap_references import refresh_redcap_references
from .redcap_shipments import (RedcapShipmentError, build_order_payload, cancel_shipment,
                               recover_submission, submit_shipment)
from .redcap_tracking import sync_shipments
from .test_redcap import reference_client


def item(pk=1, weight="3", quantity=1):
    # Dimensions deliberately absent: RedCap uses summed packaged weight.
    return SimpleNamespace(product=SimpleNamespace(pk=pk, effective_shipping_weight_kg=Decimal(weight)), quantity=quantity)


class RedcapQuoteTests(TestCase):
    def setUp(self):
        refresh_redcap_references(client=reference_client())
        self.location = resolve_delivery_location(1, 1)

    def quote(self, items=None, location=None, source="cart"):
        location = location or self.location
        return build_delivery_quote(source=source, items=items or [item()], region=location, city=location)

    @patch("commerce.redcap.RedcapClient.from_settings", side_effect=AssertionError("No checkout carrier call"))
    def test_two_three_kg_units_charge_six_kg_once_for_both_checkouts(self, factory):
        for source in ("cart", "buy_now"):
            quote = self.quote(items=[item(quantity=2)], source=source)
            self.assertEqual(quote["measurements"]["weight"], "6.00")
            self.assertEqual(quote["customer_delivery_price"], "12.00")
            self.assertEqual(quote["delivery_margin"], "0.00")
            self.assertEqual(quote["provider"], "redcap")
            self.assertIsNone(quote["measurements"]["length"])
        factory.assert_not_called()

    def test_distinct_products_sum_weight_and_no_volume_fee(self):
        quote = self.quote(items=[item(1, "3"), item(2, "3")])
        self.assertEqual(quote["customer_delivery_price"], "12.00")
        hood = item(3, "8")
        hood.product.effective_shipping_length_cm = Decimal(200)
        self.assertEqual(self.quote([hood])["customer_delivery_price"], "12.00")

    def test_all_zones_use_standard_service_and_stored_carrier_tariff(self):
        for zone, service, price in ((1, "same_day", "10.00"), (6, "Dgesshemog", "12.00"),
                                     (4, "RegionCity", "12.00"), (5, "sofeli", "13.00"), (7, "Magalmtiani", "15.00")):
            quote = self.quote(location=resolve_delivery_location(zone, zone))
            self.assertEqual((quote["service_slug"], quote["customer_delivery_price"]), (service, price))

    def test_invalid_weight_and_missing_reference_table_fail_without_free_fallback(self):
        for weight in (None, Decimal(0), Decimal("NaN")):
            bad = item()
            bad.product.effective_shipping_weight_kg = weight
            with self.assertRaises(DeliveryQuoteError):
                self.quote([bad])
        RedcapReferenceData.objects.all().delete()
        self.assertEqual(delivery_locations(), [])
        with self.assertRaises(DeliveryQuoteError):
            resolve_delivery_location(1, 1)

    def test_signed_quote_binds_source_cart_weight_zone_and_current_tariffs(self):
        quote = self.quote()
        self.assertEqual(validate_delivery_quote(quote_token=quote["quote_token"], source="cart", items=[item()],
                         region=self.location, city=self.location)["version"], 2)
        changes = [("buy_now", [item()], self.location), ("cart", [item(quantity=2)], self.location),
                   ("cart", [item(weight="3.001")], self.location),
                   ("cart", [item()], resolve_delivery_location(4, 4))]
        for source, items, location in changes:
            with self.assertRaises(DeliveryQuoteError):
                validate_delivery_quote(quote_token=quote["quote_token"], source=source, items=items,
                                         region=location, city=location)
        changed = reference_client()
        changed.get_weight_options.return_value["weights"][0]["prices"]["same_day"] = 11
        refresh_redcap_references(client=changed)
        location = resolve_delivery_location(1, 1)
        with self.assertRaises(DeliveryQuoteError):
            validate_delivery_quote(quote_token=quote["quote_token"], source="cart", items=[item()], region=location, city=location)
        # A bank's already-frozen quote is decoded independently of today's table.
        self.assertEqual(delivery_order_fields(quote)["delivery_price"], Decimal(10))

    def test_tampered_and_expired_tokens_reject(self):
        for token in (self.quote()["quote_token"] + "tamper", "garbage"):
            with self.assertRaises(DeliveryQuoteError):
                validate_delivery_quote(quote_token=token, source="cart", items=[item()], region=self.location, city=self.location)
        with patch("django.core.signing.time.time", return_value=1):
            quote = self.quote()
        with self.assertRaises(DeliveryQuoteError) as caught:
            validate_delivery_quote(quote_token=quote["quote_token"], source="cart", items=[item()], region=self.location, city=self.location)
        self.assertEqual(caught.exception.code, "delivery_quote_expired")

    def test_legacy_redcap_references_are_not_exposed_by_active_checkout(self):
        with patch("commerce.redcap.RedcapClient.from_settings", side_effect=AssertionError("No HTTP")):
            response = self.client.get(reverse("commerce-delivery-region-list"))
            self.assertEqual(response.json()["results"], [])
            self.assertTrue(all(not row["is_internal_delivery"] for row in response.json()["results"]))
            response = self.client.get(reverse("commerce-delivery-city-list", args=[5]))
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.client.get(reverse("commerce-delivery-city-list", args=[999])).status_code, 404)

    def test_retired_redcap_locations_cannot_start_a_new_checkout(self):
        from rest_framework.exceptions import ValidationError
        from .serializers import CheckoutSerializer
        serializer = CheckoutSerializer()
        for city in ("", "რეგიონი (ქალაქები)", "ბათუმი"):
            with self.assertRaises(ValidationError):
                serializer.validate({"delivery_region_id": 4, "delivery_city_id": 4, "city": city})


@override_settings(REDCAP_SENDER_NAME="Test Store", REDCAP_SENDER_PHONE="555000001",
                   REDCAP_SENDER_CITY="თბილისი", REDCAP_SENDER_ADDRESS="Test pickup 1")
class RedcapWorkflowFixture(TestCase):
    def setUp(self):
        refresh_redcap_references(client=reference_client())
        self.order = Order.objects.create(order_number="ORDER-RC-1", first_name="Test", last_name="Buyer",
            phone="+995 555 000 002", city="თბილისი", address_line="Test address 2",
            payment_status="paid", payment_method="card", status="confirmed", subtotal=100, total=112,
            delivery_provider="redcap", delivery_region_id=1, delivery_city_id=1, delivery_service_slug="same_day",
            carrier_delivery_cost=12, delivery_margin=0, delivery_price=12, shipping_weight_kg=6)
        OrderItem.objects.create(order=self.order, product_name="Test part", sku="private-supplier-code",
                                 internal_sku="FD-03-0001", unit_price=50, quantity=2, line_total=100)
        self.carrier = Mock(spec=RedcapClient)
        self.carrier.create_order.return_value = {"tracking_number": "000123", "delivery_price": 12}

    def submit(self, **kwargs):
        return submit_shipment(self.order.pk, parcel_count=2, prepared=True, client=self.carrier, **kwargs)

    def status(self, code, number="000123"):
        return {"success": True, "orders": [{"tracking_number": number, "found": True, "status": code}]}


class RedcapShipmentTests(RedcapWorkflowFixture):
    def test_carrier_panel_cancellation_is_recorded_without_refunding_or_cancelling_the_order(self):
        from .redcap_shipments import has_unsettled_redcap_shipment
        self.submit()
        self.carrier.get_tracking_statuses.return_value = self.status("cancelled")
        counts = sync_shipments([self.order.pk], client=self.carrier)
        self.assertEqual(counts["review"], 1)
        self.assertEqual(RedcapShipment.objects.get().state, "cancelled")
        self.assertFalse(has_unsettled_redcap_shipment(self.order))
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ("confirmed", "paid"))

    def test_provider_rejection_after_status_check_keeps_refunds_blocked(self):
        from .redcap_shipments import has_unsettled_redcap_shipment
        self.submit()
        self.carrier.get_tracking_statuses.return_value = self.status("registered")
        self.carrier.cancel_order.side_effect = RedcapResponseError(status_code=403)
        with self.assertRaises(RedcapShipmentError):
            cancel_shipment(self.order.pk, reason="Test", client=self.carrier)
        self.assertEqual(RedcapShipment.objects.get().state, "created")
        self.assertTrue(has_unsettled_redcap_shipment(self.order))

    def test_retired_easyway_commands_fail_without_network_or_database_changes(self):
        with patch("requests.request", side_effect=AssertionError("Retired courier must not connect")):
            for command in ("sync_easyway_tracking", "sync_easyway_locations", "check_easyway_api"):
                with self.assertRaisesMessage(CommandError, "EasyWay is retired"):
                    call_command(command)
        self.assertFalse(RedcapShipment.objects.exists())

    def test_unexpected_cancellation_failure_can_be_resolved_by_reading_status(self):
        self.submit()
        self.carrier.get_tracking_statuses.return_value = self.status("registered")
        self.carrier.cancel_order.side_effect = RuntimeError("Interrupted response")
        with self.assertRaises(RedcapShipmentError):
            cancel_shipment(self.order.pk, reason="Test", client=self.carrier)
        self.assertEqual(RedcapShipment.objects.get().state, "cancel_unknown")
        self.carrier.get_tracking_statuses.return_value = self.status("cancelled")
        sync_shipments([self.order.pk], client=self.carrier)
        self.assertEqual(RedcapShipment.objects.get().state, "cancelled")
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ("confirmed", "paid"))

    def test_one_batch_partially_missing_preserves_the_missing_orders_progress(self):
        self.submit()
        other = Order.objects.create(order_number="ORDER-RC-2", delivery_provider="redcap", status="processing",
                                     payment_status="paid", subtotal=100, total=112)
        second = RedcapShipment.objects.create(order=other, state="created", tracking_number="000124", service_slug="same_day")
        self.carrier.get_tracking_statuses.return_value = {"success": True, "orders": [
            {"tracking_number": "000124", "found": False},
            {"tracking_number": "000123", "found": True, "status": "picked_up"},
        ]}
        counts = sync_shipments([self.order.pk, other.pk], client=self.carrier)
        self.assertEqual((counts["synced"], counts["failed"]), (1, 1))
        self.carrier.get_tracking_statuses.assert_called_once_with(["000123", "000124"])
        self.order.refresh_from_db()
        other.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((self.order.status, other.status), ("shipped", "processing"))
        self.assertTrue(second.tracking_error)

    def test_operator_creates_once_with_total_weight_invoice_and_no_cod_or_supplier_sku(self):
        shipment = self.submit()
        payload = self.carrier.create_order.call_args.args[0]
        self.assertEqual((payload["quantity"], payload["weight"], payload["item_price"]), (2, 6.0, 0))
        self.assertEqual((payload["payment_type"], payload["delivery_payer"]), ("transfer", "sender"))
        self.assertEqual(payload["products"], [{"name": "Test part", "qty": 2}])
        self.assertNotIn("private-supplier-code", str(payload))
        self.assertEqual(shipment.tracking_number, "000123")
        with self.assertRaises(RedcapShipmentError):
            self.submit()

    def test_duplicate_provider_tracking_cannot_become_a_retryable_failure(self):
        other = Order.objects.create(order_number="RC-OTHER", subtotal=1, total=1)
        RedcapShipment.objects.create(order=other, tracking_number="000123", state="created", service_slug="same_day")
        with self.assertRaises(RedcapShipmentError):
            self.submit()
        shipment = RedcapShipment.objects.get(order=self.order)
        self.assertEqual(shipment.state, "unknown")
        self.assertIsNone(shipment.tracking_number)
        with self.assertRaises(RedcapShipmentError):
            self.submit()
        self.carrier.create_order.assert_called_once()
        self.carrier.create_order.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ("confirmed", "paid"))

    def test_prepared_checkbox_and_paid_state_are_required(self):
        with self.assertRaises(RedcapShipmentError):
            submit_shipment(self.order.pk, parcel_count=1, prepared=False, client=self.carrier)
        self.order.payment_status = "pending"
        self.order.save()
        with self.assertRaises(RedcapShipmentError):
            self.submit()
        self.carrier.create_order.assert_not_called()
        self.assertFalse(RedcapShipment.objects.exists())

    def test_timeout_blocks_resubmission_and_exact_lookup_recovers_existing_shipment(self):
        self.carrier.create_order.side_effect = RedcapTransportError(outcome_unknown=True)
        with self.assertRaises(RedcapShipmentError):
            self.submit()
        self.assertEqual(RedcapShipment.objects.get().state, "unknown")
        with self.assertRaises(RedcapShipmentError):
            self.submit()
        self.carrier.create_order.assert_called_once()
        self.carrier.get_order.return_value = {"success": True, "order": {
            "order_number": self.order.order_number, "tracking_number": "000456", "delivery_price": 12}}
        recovered = recover_submission(self.order.pk, client=self.carrier)
        self.assertEqual((recovered.state, recovered.tracking_number), ("created", "000456"))
        self.carrier.get_order.assert_called_once_with(self.order.order_number)

    def test_wrong_recovery_match_does_not_attach_another_order(self):
        RedcapShipment.objects.create(order=self.order, state="unknown", service_slug="same_day")
        self.carrier.get_order.return_value = {"success": True, "order": {
            "order_number": "OTHER", "tracking_number": "000456"}}
        with self.assertRaises(RedcapShipmentError):
            recover_submission(self.order.pk, client=self.carrier)
        self.assertIsNone(RedcapShipment.objects.get().tracking_number)

    def test_explicit_rejection_can_retry_and_changed_carrier_price_does_not_change_paid_total(self):
        self.carrier.create_order.side_effect = RedcapResponseError(status_code=422)
        with self.assertRaises(RedcapShipmentError):
            self.submit()
        self.assertEqual(RedcapShipment.objects.get().state, "failed")
        self.carrier.create_order.side_effect = None
        self.carrier.create_order.return_value = {"tracking_number": "000123", "delivery_price": 14}
        shipment = self.submit()
        self.assertTrue(shipment.last_error)
        self.order.refresh_from_db()
        self.assertEqual((self.order.delivery_price, self.order.total), (Decimal(12), Decimal(112)))

    def test_order_cancelled_during_http_still_retains_created_tracking_for_review(self):
        def response(_):
            Order.objects.filter(pk=self.order.pk).update(status="cancelled")
            return {"tracking_number": "000123", "delivery_price": 12}
        self.carrier.create_order.side_effect = response
        shipment = self.submit()
        self.assertEqual(shipment.tracking_number, "000123")
        self.assertTrue(shipment.last_error)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    def test_cancellation_reads_eligibility_and_never_cancels_order_or_refunds(self):
        self.submit()
        before = Order.objects.values().get(pk=self.order.pk)
        self.carrier.get_tracking_statuses.return_value = self.status("registered")
        self.carrier.cancel_order.return_value = {"success": True}
        shipment = cancel_shipment(self.order.pk, reason="Test cancellation", client=self.carrier)
        self.assertEqual(shipment.state, "cancelled")
        self.assertEqual(Order.objects.values().get(pk=self.order.pk), before)

    def test_courier_assignment_blocks_cancellation_before_mutation(self):
        self.submit()
        self.carrier.get_tracking_statuses.return_value = self.status("pending_pickup")
        with self.assertRaises(RedcapShipmentError):
            cancel_shipment(self.order.pk, reason="Test", client=self.carrier)
        self.carrier.cancel_order.assert_not_called()

    def test_tracking_advances_once_and_does_not_regress_or_refund(self):
        self.submit()
        for code, expected in (("registered", "confirmed"), ("pending_pickup", "processing"),
                               ("picked_up", "shipped"), ("registered", "shipped"), ("delivered", "delivered")):
            self.carrier.get_tracking_statuses.return_value = self.status(code)
            sync_shipments([self.order.pk], client=self.carrier)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, expected)
            self.assertEqual(self.order.payment_status, "paid")
        shipment = RedcapShipment.objects.get()
        self.assertIn("observed_at", shipment.tracking_history[-1])
        self.assertNotIn("created_at", shipment.tracking_history[-1])
        count = RedcapSyncReport.objects.count()
        sync_shipments([self.order.pk], client=self.carrier)
        self.assertEqual(RedcapSyncReport.objects.count(), count)

    def test_unknown_not_found_or_cancelled_local_order_keeps_progress(self):
        self.submit()
        for payload in (self.status("new_provider_code"), {"success": True, "orders": []}):
            self.carrier.get_tracking_statuses.return_value = payload
            counts = sync_shipments([self.order.pk], client=self.carrier)
            self.assertTrue(counts["review"] or counts["failed"])
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, "confirmed")
        Order.objects.filter(pk=self.order.pk).update(status="cancelled")
        self.carrier.get_tracking_statuses.return_value = self.status("delivered")
        sync_shipments([self.order.pk], client=self.carrier)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    def test_lease_skips_overlapping_worker_and_superseded_worker_cannot_apply(self):
        shipment = self.submit()
        newer = uuid4()
        RedcapShipment.objects.filter(pk=shipment.pk).update(tracking_token=newer, tracking_lock_until=timezone.now() + timedelta(minutes=1))
        self.assertEqual(sync_shipments([self.order.pk], client=self.carrier)["skipped"], 1)
        self.carrier.get_tracking_statuses.assert_not_called()
        RedcapShipment.objects.filter(pk=shipment.pk).update(tracking_lock_until=timezone.now() - timedelta(minutes=1))
        def replace_lease(_):
            RedcapShipment.objects.filter(pk=shipment.pk).update(tracking_token=newer)
            return self.status("delivered")
        self.carrier.get_tracking_statuses.side_effect = replace_lease
        self.assertEqual(sync_shipments([self.order.pk], client=self.carrier)["skipped"], 1)
        shipment.refresh_from_db()
        self.assertEqual(shipment.tracking_token, newer)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    @patch("commerce.redcap_tracking.RedcapClient.from_settings")
    def test_empty_and_dry_run_scheduler_makes_no_carrier_requests_or_writes(self, factory):
        call_command("sync_redcap_tracking", stdout=StringIO())
        self.submit()
        call_command("sync_redcap_tracking", dry_run=True, stdout=StringIO())
        factory.assert_not_called()
        self.assertIsNone(RedcapShipment.objects.get().tracking_attempted_at)
        self.assertFalse(RedcapSyncReport.objects.exists())


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class RedcapOrderAdminTests(RedcapWorkflowFixture):
    # Inherit the same workflow fixtures; test only actual admin boundaries here.
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(username="rc-operator", email="operator@example.com", password="Test-only-123")
        self.client.force_login(self.user)

    @patch("commerce.redcap_shipments.RedcapClient.from_settings")
    def test_get_confirmation_does_not_book_and_post_requires_csrf_and_ready(self, factory):
        url = reverse("admin:commerce_order_redcap_submit", args=[self.order.pk])
        self.assertContains(self.client.get(url), "შეფუთული ამანათების რაოდენობა")
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(url, {"parcel_count": 2, "prepared": True}).status_code, 403)
        self.assertEqual(self.client.post(url, {"parcel_count": 2}).status_code, 200)
        factory.assert_not_called()
        factory.return_value = self.carrier
        self.assertEqual(self.client.post(url, {"parcel_count": 2, "prepared": True}).status_code, 302)
        self.assertEqual(RedcapShipment.objects.get().parcel_count, 2)

    @patch("commerce.redcap_order_admin.RedcapClient.from_settings")
    def test_label_is_private_pdf_after_creation_and_denied_to_view_only_staff(self, factory):
        label = reverse("admin:commerce_order_redcap_label", args=[self.order.pk])
        self.assertEqual(self.client.get(label).status_code, 404)
        self.submit()
        factory.return_value.get_label.return_value = b"%PDF-1.7\ntest"
        response = self.client.get(label + "?size=a4")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(self.client.get(label).status_code, 403)
        self.assertEqual(self.client.get(label + "?size=bad").status_code, 403)


@override_settings(ORDER_RECEIPTS_ENABLED=False)
class RedcapCustomerStatusTests(RedcapWorkflowFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def lookup(self, phone="555000002"):
        with patch("commerce.views.validate_recaptcha", return_value=True):
            return Client().post(reverse("commerce-order-lookup"), {
                "order_number": self.order.order_number, "phone": phone, "recaptcha_token": "test-only",
            })

    def test_synced_status_reaches_profile_list_detail_guest_lookup_and_success_page(self):
        user = get_user_model().objects.create_user(username="rc-buyer", email="rc-buyer@example.test", password="Test-only-123", is_active=True)
        self.order.user = user
        self.order.save(update_fields=["user"])
        self.client.force_authenticate(user=user)
        self.submit()
        for carrier_status, visible_status in (("pending_pickup", "processing"), ("picked_up", "shipped"), ("delivered", "delivered")):
            with self.subTest(carrier_status=carrier_status):
                self.carrier.get_tracking_statuses.return_value = self.status(carrier_status)
                sync_shipments([self.order.pk], client=self.carrier)
                listed = self.client.get(reverse("commerce-order-list"))
                detail = self.client.get(reverse("commerce-order-detail", args=[self.order.public_token]))
                public = Client().get(reverse("commerce-order-summary", args=[self.order.public_token]))
                guest = self.lookup()
                self.assertEqual(listed.status_code, 200)
                self.assertEqual(listed.json()["results"][0]["status"], visible_status)
                for response in (detail, public, guest):
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["status"], visible_status)
                for private_field in ("tracking_history", "tracking_error", "operation_token", "sender_address"):
                    self.assertNotIn(private_field, guest.json())

    def test_guest_order_is_available_without_registration_but_requires_matching_phone(self):
        self.assertIsNone(self.order.user_id)
        self.submit()
        self.carrier.get_tracking_statuses.return_value = self.status("picked_up")
        sync_shipments([self.order.pk], client=self.carrier)
        response = self.lookup()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "shipped")
        self.assertEqual(self.lookup(phone="555000999").status_code, 404)

    def test_another_account_cannot_open_the_order_in_profile(self):
        owner = get_user_model().objects.create_user(username="rc-owner", email="rc-owner@example.test", is_active=True)
        other = get_user_model().objects.create_user(username="rc-other", email="rc-other@example.test", is_active=True)
        self.order.user = owner
        self.order.save(update_fields=["user"])
        self.client.force_authenticate(user=other)
        self.assertEqual(self.client.get(reverse("commerce-order-list")).json()["results"], [])
        self.assertEqual(self.client.get(reverse("commerce-order-detail", args=[self.order.public_token])).status_code, 404)
