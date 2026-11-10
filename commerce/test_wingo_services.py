from datetime import datetime, timedelta
from unittest.mock import patch

from django.core import signing
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .delivery_quote_data import DeliveryQuoteError, delivery_order_fields
from .models import WingoLocality, WingoReferenceData, WingoShipment
from .services import build_checkout_request_fingerprint
from .test_wingo import reference_client
from .test_wingo_checkout import item
from .test_wingo_shipments import WingoShipmentFixture
from .wingo_locations import resolve_delivery_location
from .wingo_quotes import build_delivery_quote, validate_delivery_quote, LEGACY_QUOTE_SIGNING_SALT
from .wingo_references import refresh_wingo_references
from .wingo_services import service_policy, TBILISI
from .wingo_shipments import WingoShipmentError, _validate_identity, build_order_payload


def moment(day=9, hour=11, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=TBILISI)


@override_settings(WINGO_PREPARATION_MINUTES=30)
class WingoServiceCalendarTests(SimpleTestCase):
    def test_standard_cutoff_includes_processing_time(self):
        for now, expected in ((moment(), "2026-11-10"), (moment(minute=59, hour=12), "2026-11-11"),
                              (moment(hour=12, minute=29), "2026-11-10"), (moment(hour=12, minute=30), "2026-11-11"),
                              (moment(hour=15), "2026-11-11")):
            with self.subTest(now=now):
                self.assertEqual(service_policy("tbilisi", "standard", now=now)["estimated_delivery_date"], expected)

    def test_fast_rolls_to_next_working_day_after_1230_and_on_weekends(self):
        for now, expected in ((moment(), "2026-11-09"), (moment(hour=12, minute=29), "2026-11-09"),
                               (moment(hour=12, minute=30), "2026-11-10"), (moment(hour=15), "2026-11-10"),
                               (moment(day=13, hour=15), "2026-11-16"),
                               (moment(day=14), "2026-11-16"), (moment(day=15), "2026-11-16")):
            with self.subTest(now=now):
                policy = service_policy("tbilisi", "fast", now=now)
                self.assertTrue(policy["available"])
                self.assertEqual(policy["estimated_delivery_date"], expected)
                self.assertTrue(policy["booking_deadline_at"].startswith(expected))
                self.assertTrue(policy["booking_deadline_at"].endswith("13:00:00+04:00"))
                self.assertTrue(policy["checkout_deadline_at"].endswith("12:30:00+04:00"))

    def test_friday_and_weekend_use_working_days(self):
        for now, expected in ((moment(day=13), "2026-11-16"), (moment(day=13, hour=15), "2026-11-17"),
                              (moment(day=14), "2026-11-17"), (moment(day=15), "2026-11-17")):
            self.assertEqual(service_policy("tbilisi", "standard", now=now)["estimated_delivery_date"], expected)

    def test_utc_clock_is_converted_to_tbilisi(self):
        utc = datetime.fromisoformat("2026-11-09T08:30:00+00:00")
        self.assertEqual(service_policy("tbilisi", "fast", now=utc)["estimated_delivery_date"], "2026-11-10")

    def test_standard_uses_a_range_and_preparation_setting_moves_same_day_cutoff(self):
        self.assertEqual(service_policy("tbilisi", "standard", now=moment())["estimate_label"], "1–2 სამუშაო დღეში")
        with self.settings(WINGO_PREPARATION_MINUTES=45):
            self.assertEqual(service_policy("tbilisi", "fast", now=moment(hour=12, minute=14))["estimated_delivery_date"], "2026-11-09")
            self.assertEqual(service_policy("tbilisi", "fast", now=moment(hour=12, minute=15))["estimated_delivery_date"], "2026-11-10")

    def test_regions_keep_standard_and_do_not_invent_calendar_dates(self):
        for group in ("standardRegion", "mountainRegion", "tbilisiSuburbs"):
            self.assertFalse(service_policy(group, "fast", now=moment())["available"])
            standard = service_policy(group, "standard", now=moment())
            self.assertIsNone(standard["estimated_delivery_date"])
            self.assertIn("3–5", standard["estimate_label"])


@override_settings(WINGO_PREPARATION_MINUTES=30)
class WingoServiceQuoteTests(TestCase):
    def setUp(self):
        refresh_wingo_references(client=reference_client())
        mapping = WingoLocality.objects.get(external_id="oayK3wTbTlSTuvTHkTHc")
        self.location = resolve_delivery_location(mapping.region_id, mapping.pk)

    def quote(self, service="standard", now=None, location=None):
        location = location or self.location
        with patch("django.utils.timezone.now", return_value=now or moment()):
            return build_delivery_quote(source="cart", items=[item()], region=location, city=location, service_slug=service)

    def validate(self, quote, service="standard", now=None):
        with patch("django.utils.timezone.now", return_value=now or moment()):
            return validate_delivery_quote(quote_token=quote["quote_token"], source="cart", items=[item()],
                                            region=self.location, city=self.location, service_slug=service)

    def test_both_prices_use_stored_weight_tariffs_without_provider_calls(self):
        with patch("requests.request", side_effect=AssertionError("No provider call")):
            standard, fast = self.quote(), self.quote("fast")
        self.assertEqual((standard["customer_delivery_price"], fast["customer_delivery_price"]), ("46.00", "83.00"))
        self.assertEqual([(row["service_slug"], row["price"]) for row in standard["options"]], [("standard", "46.00"), ("fast", "83.00")])
        self.assertEqual((fast["delivery_type_id"], fast["service_slug"], fast["version"]), (2, "fast", 4))
        self.assertEqual(fast["schedule"]["estimated_delivery_date"], "2026-11-09")

    def test_fast_only_in_tbilisi_and_after_cutoff_keeps_its_own_price(self):
        mapping = WingoLocality.objects.get(external_id="TPJtXj8vtQefzbiRytWY")
        elsewhere = resolve_delivery_location(mapping.region_id, mapping.pk)
        with self.assertRaises(DeliveryQuoteError):
            self.quote("fast", location=elsewhere)
        fast = self.quote("fast", now=moment(hour=13))
        self.assertTrue(fast["options"][1]["available"])
        self.assertEqual(fast["customer_delivery_price"], "83.00")
        self.assertEqual(fast["schedule"]["estimated_delivery_date"], "2026-11-10")
        self.validate(fast, "fast", now=moment(hour=13, minute=1))

    def test_expiry_before_cutoff_and_schedule_changes_require_requote(self):
        quote = self.quote("fast", now=moment(hour=12, minute=25))
        self.assertTrue(quote["expires_at"].endswith("12:30:00+04:00"))
        self.validate(quote, "fast", now=moment(hour=12, minute=29))
        with self.assertRaises(DeliveryQuoteError):
            self.validate(quote, "fast", now=moment(hour=12, minute=30))
        fresh = self.quote("fast", now=moment(hour=12, minute=30))
        self.validate(fresh, "fast", now=moment(hour=12, minute=31))
        self.assertEqual(fresh["schedule"]["estimated_delivery_date"], "2026-11-10")
        standard = self.quote(now=moment(hour=12, minute=25))
        with self.assertRaises(DeliveryQuoteError):
            self.validate(standard, now=moment(hour=12, minute=31))

    def test_selected_service_is_bound_to_payment_and_cannot_be_swapped(self):
        quote = self.quote("fast")
        with self.assertRaises(DeliveryQuoteError):
            self.validate(quote, "standard")
        fields = delivery_order_fields(self.validate(quote, "fast"))
        self.assertEqual((fields["delivery_service_slug"], fields["delivery_provider_data"]["delivery_type_id"]), ("fast", 2))
        self.assertEqual(fields["delivery_provider_data"]["schedule"], quote["schedule"])
        WingoReferenceData.objects.all().delete()
        self.assertEqual(delivery_order_fields(quote), fields)  # Bank completion never re-quotes today's data.

    def test_legacy_v3_standard_pending_quotes_and_decoding_remain_valid(self):
        legacy = self.quote()
        for key in ("schedule", "expires_at", "group_type", "options", "server_time", "quote_token"):
            legacy.pop(key)
        legacy["version"] = 3
        token = signing.dumps(legacy, salt=LEGACY_QUOTE_SIGNING_SALT, compress=True)
        restored = self.validate({"quote_token": token})
        self.assertEqual(restored, legacy)
        self.assertNotIn("schedule", delivery_order_fields(restored)["delivery_provider_data"])

    def test_service_change_is_a_distinct_idempotent_purchase_and_standard_history_is_stable(self):
        base = {"first_name": "Test"}
        standard = build_checkout_request_fingerprint(source="cart", validated_data=base)
        self.assertEqual(standard, build_checkout_request_fingerprint(source="cart", validated_data={**base, "delivery_service_slug": "standard"}))
        self.assertNotEqual(standard, build_checkout_request_fingerprint(source="cart", validated_data={**base, "delivery_service_slug": "fast"}))


class WingoServiceBookingTests(WingoShipmentFixture):
    def test_next_day_fast_sends_explicit_frozen_date_even_before_carrier_cutoff(self):
        schedule = service_policy("tbilisi", "fast", now=moment(hour=12, minute=40))
        self.change_order(delivery_service_slug="fast", delivery_provider_data={
            **self.order.delivery_provider_data, "delivery_type_id": 2, "schedule": schedule})
        with patch("django.utils.timezone.now", return_value=moment(hour=12, minute=45)):
            self.submit()
        payload = self.carrier.create_order.call_args.args[0]
        self.assertEqual(payload["deliveryDate"], "2026-11-10")
        self.assertEqual(payload["deliveryTypeId"], 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_price, 46)

    def test_provider_date_mismatch_or_missing_date_does_not_confirm_a_different_day(self):
        schedule = service_policy("tbilisi", "fast", now=moment(hour=15))
        self.change_order(delivery_service_slug="fast", delivery_provider_data={
            **self.order.delivery_provider_data, "delivery_type_id": 2, "schedule": schedule})
        with patch("django.utils.timezone.now", return_value=moment(hour=15)):
            payload = build_order_payload(self.order, parcel_count=1, client=self.carrier)
        result = {**payload, "id": "provider-test-id", "orderNumber": "test-tracking"}
        _validate_identity({**result, "deliveryDate": "2026-11-10T08:00:00Z"}, payload)
        _validate_identity({**result, "deliveryDate": "2026-11-09T20:00:00Z"}, payload)
        for value in (None, "2026-11-09", "bad", "2026-11-11T00:00:00+04:00"):
            with self.subTest(value=value), self.assertRaises(WingoShipmentError):
                _validate_identity({**result, "deliveryDate": value}, payload)

    def test_provider_ignoring_requested_date_blocks_duplicate_booking(self):
        schedule = service_policy("tbilisi", "fast", now=moment(hour=12, minute=40))
        self.change_order(delivery_service_slug="fast", delivery_provider_data={
            **self.order.delivery_provider_data, "delivery_type_id": 2, "schedule": schedule})
        self.carrier.create_order.side_effect = lambda payload: self.result(payload, deliveryDate="2026-11-09")
        with patch("django.utils.timezone.now", return_value=moment(hour=12, minute=45)):
            with self.assertRaises(WingoShipmentError):
                self.submit()
            self.assertEqual(WingoShipment.objects.get(order=self.order).state, "unknown")
            with self.assertRaises(WingoShipmentError):
                self.submit()
        self.carrier.create_order.assert_called_once()

    def test_fast_selection_reaches_provider_with_frozen_price_and_same_day_guard(self):
        data = {**self.order.delivery_provider_data, "delivery_type_id": 2,
                "schedule": {"booking_deadline_at": (timezone.now() + timedelta(minutes=30)).isoformat()}}
        self.change_order(delivery_service_slug="fast", delivery_provider_data=data)
        self.submit()
        self.assertEqual(self.carrier.create_order.call_args.args[0]["deliveryTypeId"], 2)
        self.assertEqual(self.order.delivery_price, 46)  # Never replace paid money while booking.

    def test_missed_fast_deadline_never_silently_books_tomorrow(self):
        data = {**self.order.delivery_provider_data, "delivery_type_id": 2,
                "schedule": {"booking_deadline_at": (timezone.now() - timedelta(minutes=1)).isoformat()}}
        self.change_order(delivery_service_slug="fast", delivery_provider_data=data)
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.carrier.create_order.assert_not_called()

    def test_fast_without_a_frozen_deadline_cannot_bypass_the_cutoff(self):
        self.change_order(delivery_service_slug="fast", delivery_provider_data={
            **self.order.delivery_provider_data, "delivery_type_id": 2, "schedule": {}})
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.carrier.create_order.assert_not_called()

    def test_late_standard_requires_explicit_customer_agreement(self):
        data = {**self.order.delivery_provider_data,
                "schedule": {"booking_deadline_at": (timezone.now() - timedelta(minutes=1)).isoformat()}}
        self.change_order(delivery_provider_data=data)
        with self.assertRaises(WingoShipmentError):
            self.submit()
        self.submit(late_delivery_confirmed=True)
        self.carrier.create_order.assert_called_once()
