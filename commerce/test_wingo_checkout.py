import copy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Category, Product
from .delivery_quotes import (
    DeliveryQuoteError, build_delivery_quote, delivery_cities, delivery_locations,
    delivery_order_fields, resolve_delivery_location, validate_delivery_quote,
)
from .models import BuyNowSession, Cart, CartItem, WingoLocality, WingoReferenceData, WingoRegion
from .serializers import CheckoutSerializer
from .test_wingo import reference_client, sample
from .wingo_references import refresh_wingo_references


def item(weight="31", quantity=1, pk=1):
    return SimpleNamespace(product=SimpleNamespace(pk=pk, effective_shipping_weight_kg=weight), quantity=quantity)


class WingoCheckoutTests(TestCase):
    def setUp(self):
        self.data = sample()
        refresh_wingo_references(client=reference_client(self.data))
        self.location = self.location_for("oayK3wTbTlSTuvTHkTHc")

    def location_for(self, external_id):
        mapping = WingoLocality.objects.get(external_id=external_id)
        return resolve_delivery_location(mapping.region_id, mapping.pk)

    def quote(self, *, items=None, location=None, source="cart"):
        location = location or self.location
        return build_delivery_quote(source=source, items=items if items is not None else [item()], region=location, city=location)

    def test_only_standard_tariffs_are_used_for_all_four_groups(self):
        for external_id, expected in (("oayK3wTbTlSTuvTHkTHc", "46.00"),
                                      ("CEYo2KMYqhlrU5nrVohQ", "51.00"),
                                      ("TPJtXj8vtQefzbiRytWY", "55.00"),
                                      ("gjFtxS8HEeuyq7o6YrUQ", "60.00")):
            with self.subTest(external_id=external_id):
                quote = self.quote(location=self.location_for(external_id))
                self.assertEqual(quote["customer_delivery_price"], expected)
                self.assertEqual((quote["provider"], quote["delivery_type_id"], quote["service_slug"]), ("wingo", 1, "standard"))
                self.assertEqual(quote["delivery_margin"], "0.00")

    def test_fractional_weight_rounds_up_and_exact_upper_boundary_stays_in_band(self):
        for weight, amount in (("0.001", "9.00"), ("5", "9.00"), ("5.001", "11.00"),
                               ("10", "11.00"), ("10.001", "13.00"), ("30", "29.00"),
                               ("30.001", "46.00"), ("50", "46.00"), ("500", "295.00")):
            with self.subTest(weight=weight):
                self.assertEqual(self.quote(items=[item(weight)])["customer_delivery_price"], amount)
        with self.assertRaises(DeliveryQuoteError):
            self.quote(items=[item("500.001")])

    def test_quantities_and_distinct_product_weights_sum_without_volume_or_parcel_multiplier(self):
        unit = item("3", 2)
        unit.product.effective_shipping_length_cm = Decimal(1000)
        for source in ("cart", "buy_now"):
            quote = self.quote(items=[unit], source=source)
            self.assertEqual((quote["measurements"]["weight"], quote["customer_delivery_price"]), ("6.00", "11.00"))
            self.assertIsNone(quote["measurements"]["length"])
        self.assertEqual(self.quote(items=[item("3"), item("3", pk=2)])["measurements"]["weight"], "6.00")

    def test_missing_invalid_weight_or_quantity_never_creates_a_free_quote(self):
        for weight, quantity in ((None, 1), (0, 1), (True, 1), ("NaN", 1), ("Infinity", 1),
                                  ("3", 0), ("3", True), ("3", 1.5)):
            with self.subTest(weight=weight, quantity=quantity), self.assertRaises(DeliveryQuoteError):
                self.quote(items=[item(weight, quantity)])
        with self.assertRaises(DeliveryQuoteError):
            self.quote(items=[])

    def test_quote_and_location_endpoints_do_not_call_courier(self):
        with patch("requests.request", side_effect=AssertionError("No provider request in checkout")):
            self.quote()
            regions = self.client.get(reverse("commerce-delivery-region-list"))
            cities = self.client.get(reverse("commerce-delivery-city-list", args=[self.location.region_id]))
        self.assertEqual(regions.json()["provider"], "wingo")
        self.assertEqual(len(regions.json()["results"]), 4)
        self.assertEqual(cities.json()["results"], [{"id": self.location.external_id, "name": "თბილისი"}])
        self.assertEqual(cities["Cache-Control"], "no-store")
        self.assertNotIn("api_base_url", str(regions.json()))
        self.assertNotIn("revision", str(cities.json()))

    def test_wrong_region_and_missing_snapshot_fail_without_legacy_fallback(self):
        other = WingoRegion.objects.exclude(pk=self.location.region_id).first()
        for region_id, city_id in ((other.pk, self.location.external_id), (True, self.location.external_id), (99999, 99999)):
            with self.subTest(region_id=region_id), self.assertRaises(DeliveryQuoteError):
                resolve_delivery_location(region_id, city_id)
        WingoReferenceData.objects.all().delete()
        self.assertEqual(delivery_locations(), [])
        with patch("commerce.wingo_locations.WingoRegion.objects.filter", side_effect=AssertionError("No mapping lookup without snapshot")):
            self.assertEqual(delivery_cities(self.location.region_id), (None, []))
        with patch("commerce.wingo_locations.WingoLocality.objects.select_related", side_effect=AssertionError("No mapping lookup without snapshot")):
            with self.assertRaises(DeliveryQuoteError):
                self.quote()

    def test_saturday_only_delivery_is_still_orderable_on_other_days(self):
        row = self.data["localities"]["თბილისი"][0]
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            row[day] = day == "saturday"
        refresh_wingo_references(client=reference_client(self.data))
        self.assertEqual(self.quote()["customer_delivery_price"], "46.00")

    def test_inactive_or_nonoperational_locality_is_not_offered(self):
        for flag in ("active", "operational"):
            data = sample()
            data["localities"]["თბილისი"][0][flag] = False
            refresh_wingo_references(client=reference_client(data))
            with self.subTest(flag=flag), self.assertRaises(DeliveryQuoteError):
                self.quote()
            self.assertEqual(delivery_cities(self.location.region_id)[1], [])
            self.assertNotIn(self.location.region_id, [row.external_id for row in delivery_locations()])

    def test_hidden_or_missing_tariff_is_not_treated_as_free(self):
        self.data["tariffs"][5]["hidden"] = True
        refresh_wingo_references(client=reference_client(self.data))
        with self.assertRaises(DeliveryQuoteError):
            self.quote()
        WingoReferenceData.objects.filter(pk=1).update(tariffs=[])
        with self.assertRaises(DeliveryQuoteError):
            self.quote()

    def test_numeric_ids_survive_new_sorted_localities_and_removal_then_reappearance(self):
        old = dict(WingoLocality.objects.values_list("external_id", "pk"))
        new = copy.deepcopy(self.data["localities"]["თბილისი"][0])
        new.update(id="000-new-location", nameGe="თბილისი - ახალი", localityGe="ახალი")
        self.data["localities"]["თბილისი"].append(new)
        self.data["regions"]["localities"].append({key: new[key] for key in ("id", "nameGe", "regionGe")})
        refresh_wingo_references(client=reference_client(self.data))
        self.assertTrue(all(WingoLocality.objects.get(external_id=key).pk == value for key, value in old.items()))
        data = sample()
        data["localities"]["თბილისი"] = []
        data["regions"]["localities"] = [row for row in data["regions"]["localities"] if row["id"] != self.location.provider_city_id]
        refresh_wingo_references(client=reference_client(data))
        with self.assertRaises(DeliveryQuoteError):
            self.quote()
        refresh_wingo_references(client=reference_client())
        self.assertEqual(self.location_for(self.location.provider_city_id).external_id, self.location.external_id)

    def test_quote_is_bound_to_source_contents_raw_weight_and_locality(self):
        quote = self.quote()
        for source, items, location in (("buy_now", [item()], self.location),
                                        ("cart", [item(quantity=2)], self.location),
                                        ("cart", [item("31.001")], self.location),
                                        ("cart", [item()], self.location_for("TPJtXj8vtQefzbiRytWY"))):
            with self.subTest(source=source, items=items), self.assertRaises(DeliveryQuoteError):
                validate_delivery_quote(quote_token=quote["quote_token"], source=source, items=items, region=location, city=location)

    def test_refresh_rejects_old_quote_but_frozen_bank_values_decode_without_current_references(self):
        quote = self.quote()
        self.data["tariffs"][5]["standardTbilisi"] = 47
        refresh_wingo_references(client=reference_client(self.data))
        with self.assertRaises(DeliveryQuoteError):
            validate_delivery_quote(quote_token=quote["quote_token"], source="cart", items=[item()], region=self.location, city=self.location)
        WingoReferenceData.objects.all().delete()
        fields = delivery_order_fields(quote)
        self.assertEqual(fields["delivery_price"], Decimal(46))
        self.assertEqual(fields["delivery_provider_data"], {"region_id": "Tbilisi", "locality_id": self.location.provider_city_id,
                                                          "delivery_type_id": 1, "weight_range_id": 6})

    def test_expired_and_tampered_quotes_cannot_be_used(self):
        for token in ("garbage", self.quote()["quote_token"] + "tampered", ""):
            with self.subTest(token=token[:10]), self.assertRaises(DeliveryQuoteError):
                validate_delivery_quote(quote_token=token, source="cart", items=[item()], region=self.location, city=self.location)
        with patch("django.core.signing.time.time", return_value=1):
            quote = self.quote()
        with self.assertRaises(DeliveryQuoteError) as caught:
            validate_delivery_quote(quote_token=quote["quote_token"], source="cart", items=[item()], region=self.location, city=self.location)
        self.assertEqual(caught.exception.code, "delivery_quote_expired")

    def test_checkout_canonical_city_is_selected_locality_not_client_free_text(self):
        result = CheckoutSerializer().validate({"delivery_region_id": self.location.region_id,
                                               "delivery_city_id": self.location.external_id, "city": "Wrong city"})
        self.assertEqual(result["city"], "თბილისი")

    def test_fast_frozen_payload_is_not_a_supported_new_order(self):
        quote = self.quote()
        for field, value in (("delivery_type_id", 2), ("provider", "redcap"), ("weight_range_id", None)):
            with self.subTest(field=field), self.assertRaises(DeliveryQuoteError):
                delivery_order_fields({**quote, field: value})


class WingoQuoteAPITests(TestCase):
    def setUp(self):
        refresh_wingo_references(client=reference_client())
        self.user = get_user_model().objects.create_user(username="wingo-buyer", password="test-password")
        category = Category.objects.create(name="Wingo test", slug="wingo-test")
        self.product = Product.objects.create(category=category, name="Test part", slug="wingo-part", sku="PRIVATE-SKU",
                                              internal_sku="FD-03-9001", price=100, stock_qty=20, shipping_weight_kg=31, status="published")
        self.mapping = WingoLocality.objects.get(external_id="oayK3wTbTlSTuvTHkTHc")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def payload(self, source):
        return {"source": source, "delivery_region_id": self.mapping.region_id, "delivery_city_id": self.mapping.pk}

    def test_cart_and_buy_now_quote_endpoints_use_local_standard_prices(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        BuyNowSession.objects.create(user=self.user, product=self.product, quantity=1)
        with patch("requests.request", side_effect=AssertionError("No HTTP during quote")):
            for source in ("cart", "buy_now"):
                response = self.api.post(reverse("commerce-delivery-quote"),
                    {**self.payload(source), "delivery_type_id": 2, "customer_delivery_price": "0"}, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual((response.data["provider"], response.data["delivery_type_id"], response.data["customer_delivery_price"]),
                                 ("wingo", 1, "46.00"))
                self.assertNotIn("PRIVATE-SKU", str(response.data))

    def test_guest_quote_uses_only_the_guest_cart(self):
        token = uuid4()
        cart = Cart.objects.create(guest_token=token)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        guest = APIClient()
        guest.cookies["cart_token"] = str(token)
        response = guest.post(reverse("commerce-delivery-quote"), self.payload("cart"), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["customer_delivery_price"], "46.00")


class WingoLocationMigrationTests(TransactionTestCase):
    def test_existing_snapshot_is_backfilled_without_provider_requests(self):
        name = str(connection.settings_dict["NAME"])
        assert connection.vendor == "sqlite" and (name == ":memory:" or (name.startswith("file:memorydb_") and "mode=memory" in name))
        refresh_wingo_references(client=reference_client())
        expected_ids = set(WingoLocality.objects.values_list("external_id", flat=True))
        executor = MigrationExecutor(connection)
        try:
            with patch("requests.request", side_effect=AssertionError("Migration cannot call provider")):
                executor.migrate([("commerce", "0040_wingo_reference_data")])
                MigrationExecutor(connection).migrate([("commerce", "0041_wingo_checkout_locations")])
            self.assertEqual(set(WingoLocality.objects.values_list("external_id", flat=True)), expected_ids)
            self.assertEqual(WingoRegion.objects.count(), 4)
            self.assertTrue(all(row.region_id for row in WingoLocality.objects.all()))
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
