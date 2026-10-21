from unittest.mock import Mock, patch
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from commerce.easyway_locations import sync_easyway_locations
from commerce.delivery_quotes import (
    DeliveryQuoteError,
    delivery_order_fields,
    validate_delivery_quote,
)
from catalog.models import Category, Product, ProductStatus
from commerce.models import BuyNowSession, Cart, CartItem, EasywayCity, EasywayRegion


class EasywayLocationSyncTests(TestCase):
    def test_sync_creates_locations_and_marks_tbilisi_internal(self):
        client = Mock()
        client.get_regions.return_value = [
            {"id": 24, "name": "თბილისი"},
            {"id": 25, "name": "აჭარა"},
        ]
        client.get_cities.side_effect = (
            [{"id": 11, "name": "საბურთალო"}],
            [{"id": 21, "name": "ბათუმი"}],
        )

        result = sync_easyway_locations(client)

        self.assertEqual(result.regions_created, 2)
        self.assertEqual(result.cities_created, 2)
        self.assertTrue(
            EasywayRegion.objects.get(external_id=24).is_internal_delivery
        )
        self.assertFalse(
            EasywayRegion.objects.get(external_id=25).is_internal_delivery
        )
        self.assertEqual(
            EasywayCity.objects.get(external_id=21).region.external_id,
            25,
        )

    def test_sync_preserves_internal_setting_and_deactivates_missing_rows(self):
        region = EasywayRegion.objects.create(
            external_id=24,
            name="თბილისი",
            is_internal_delivery=False,
        )
        EasywayCity.objects.create(
            region=region,
            external_id=11,
            name="საბურთალო",
        )
        stale_region = EasywayRegion.objects.create(
            external_id=99,
            name="ძველი რეგიონი",
        )
        EasywayCity.objects.create(
            region=stale_region,
            external_id=999,
            name="ძველი ქალაქი",
        )
        client = Mock()
        client.get_regions.return_value = [{"id": 24, "name": "თბილისი"}]
        client.get_cities.return_value = [{"id": 11, "name": "ვაკე"}]

        result = sync_easyway_locations(client)

        region.refresh_from_db()
        stale_region.refresh_from_db()
        self.assertFalse(region.is_internal_delivery)
        self.assertFalse(stale_region.is_active)
        self.assertFalse(EasywayCity.objects.get(external_id=999).is_active)
        self.assertEqual(EasywayCity.objects.get(external_id=11).name, "ვაკე")
        self.assertEqual(result.regions_deactivated, 1)
        self.assertEqual(result.cities_deactivated, 1)


class EasywayLocationApiTests(APITestCase):
    def setUp(self):
        self.tbilisi = EasywayRegion.objects.create(
            external_id=24,
            name="თბილისი",
            is_internal_delivery=True,
        )
        EasywayCity.objects.create(
            region=self.tbilisi,
            external_id=11,
            name="საბურთალო",
        )
        EasywayCity.objects.create(
            region=self.tbilisi,
            external_id=12,
            name="მთაწმინდა",
            is_active=False,
        )
        EasywayRegion.objects.create(
            external_id=99,
            name="Inactive",
            is_active=False,
        )

    def test_region_list_returns_only_active_regions(self):
        response = self.client.get(
            reverse("commerce-delivery-region-list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "results": [
                    {
                        "id": 24,
                        "name": "თბილისი",
                        "is_internal_delivery": True,
                    }
                ]
            },
        )

    def test_city_list_returns_active_cities_for_region(self):
        response = self.client.get(
            reverse(
                "commerce-delivery-city-list",
                kwargs={"region_id": 24},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["region"]["id"], 24)
        self.assertEqual(
            response.data["results"],
            [{"id": 11, "name": "საბურთალო"}],
        )

    def test_city_list_rejects_unknown_region(self):
        response = self.client.get(
            reverse(
                "commerce-delivery-city-list",
                kwargs={"region_id": 404},
            )
        )

        self.assertEqual(response.status_code, 404)


@override_settings(
    EASYWAY_SENDER_CITY_ID=11,
    EASYWAY_STANDARD_PACKAGE_ID=2,
    EASYWAY_DELIVERY_MARGIN_GEL="2.00",
    # Legacy fixed-price overrides must not bypass the Tbilisi tariff.
    EASYWAY_INTERNAL_DELIVERY_PRICE_GEL="0.00",
)
class EasywayDeliveryQuoteApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="quote@example.com",
            email="quote@example.com",
            password="Password123!",
        )
        self.client.force_authenticate(self.user)
        self.tbilisi = EasywayRegion.objects.create(
            external_id=24,
            name="თბილისი",
            is_internal_delivery=True,
        )
        self.tbilisi_city = EasywayCity.objects.create(
            region=self.tbilisi,
            external_id=11,
            name="საბურთალო",
        )
        self.regional = EasywayRegion.objects.create(
            external_id=25,
            name="აჭარა",
        )
        self.regional_city = EasywayCity.objects.create(
            region=self.regional,
            external_id=21,
            name="ბათუმი",
        )
        category = Category.objects.create(
            name="Parts",
            slug="parts",
            default_shipping_weight_kg=Decimal("2.00"),
            default_shipping_length_cm=Decimal("20.00"),
            default_shipping_width_cm=Decimal("30.00"),
            default_shipping_height_cm=Decimal("10.00"),
        )
        product = Product.objects.create(
            category=category,
            name="Test Part",
            slug="test-part",
            sku="TEST-PART",
            internal_sku="FD-03-0900",
            short_description="Part",
            description="Part",
            price=Decimal("100.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
            shipping_weight_kg=Decimal("2.000"),
            shipping_length_cm=Decimal("20.00"),
            shipping_width_cm=Decimal("30.00"),
            shipping_height_cm=Decimal("10.00"),
        )
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=2,
            unit_price_snapshot=product.price,
        )

    def quote(self, region, city, *, source="cart"):
        return self.client.post(
            reverse("commerce-delivery-quote"),
            {
                "source": source,
                "delivery_region_id": region.external_id,
                "delivery_city_id": city.external_id,
            },
            format="json",
        )

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_internal_quote_is_ten_gel_without_calling_easyway(self, from_settings):
        response = self.quote(self.tbilisi, self.tbilisi_city)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], "internal")
        self.assertEqual(response.data["customer_delivery_price"], "10.00")
        self.assertEqual(response.data["carrier_delivery_cost"], "0.00")
        self.assertEqual(response.data["delivery_margin"], "0.00")
        self.assertTrue(response.data["quote_token"])
        from_settings.assert_not_called()

    def set_product_measurements(self, *, weight, length, width, height, quantity=1):
        item = CartItem.objects.get(cart__user=self.user)
        Product.objects.filter(pk=item.product_id).update(
            shipping_weight_kg=Decimal(str(weight)),
            shipping_length_cm=Decimal(str(length)),
            shipping_width_cm=Decimal(str(width)),
            shipping_height_cm=Decimal(str(height)),
        )
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        return item

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_tbilisi_weight_boundary_uses_exact_total_and_quantity(self, from_settings):
        for weight, quantity, price in (
            ("9.999", 1, "10.00"),
            ("10.000", 1, "10.00"),
            ("10.001", 1, "20.00"),
            ("5.000", 2, "10.00"),
            ("5.001", 2, "20.00"),
        ):
            with self.subTest(weight=weight, quantity=quantity):
                self.set_product_measurements(
                    weight=weight, length=20, width=20, height=10, quantity=quantity,
                )
                response = self.quote(self.tbilisi, self.tbilisi_city)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["customer_delivery_price"], price)
        from_settings.assert_not_called()

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_tbilisi_checks_each_side_with_strict_boundary(self, from_settings):
        for side in ("length", "width", "height"):
            for size, price in (("100.00", "10.00"), ("100.01", "20.00")):
                with self.subTest(side=side, size=size):
                    dimensions = {"length": 10, "width": 10, "height": 10}
                    dimensions[side] = size
                    self.set_product_measurements(weight=1, **dimensions)
                    response = self.quote(self.tbilisi, self.tbilisi_city)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data["customer_delivery_price"], price)
        from_settings.assert_not_called()

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_tbilisi_volume_boundary(self, from_settings):
        for height, price in (("39.99", "10.00"), ("40.00", "10.00"), ("40.01", "20.00")):
            with self.subTest(height=height):
                self.set_product_measurements(weight=1, length=50, width=50, height=height)
                response = self.quote(self.tbilisi, self.tbilisi_city)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["customer_delivery_price"], price)
        from_settings.assert_not_called()

    def add_distinct_products(self, *, weight, length, width, height):
        item = self.set_product_measurements(
            weight=weight, length=length, width=width, height=height,
        )
        for number in (1, 2):
            product = Product.objects.create(
                category=item.product.category,
                name=f"Distinct part {number}",
                slug=f"distinct-part-{number}",
                sku=f"DISTINCT-{number}",
                internal_sku=f"FD-03-090{number}",
                price=Decimal("100.00"),
                stock_qty=5,
                status=ProductStatus.PUBLISHED,
                shipping_weight_kg=Decimal(str(weight)),
                shipping_length_cm=Decimal(str(length)),
                shipping_width_cm=Decimal(str(width)),
                shipping_height_cm=Decimal(str(height)),
            )
            CartItem.objects.create(
                cart=item.cart, product=product, quantity=1,
                unit_price_snapshot=product.price,
            )

    def test_three_distinct_products_below_limits_cost_ten_gel(self):
        self.add_distinct_products(weight=2, length=40, width=30, height=20)
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["customer_delivery_price"], "10.00")

    def test_three_distinct_products_total_weight_costs_twenty_gel_once(self):
        self.add_distinct_products(weight=4, length=20, width=10, height=5)
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["customer_delivery_price"], "20.00")

    def test_three_distinct_products_total_volume_costs_twenty_gel_once(self):
        self.add_distinct_products(weight=2, length=50, width=40, height=20)
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["customer_delivery_price"], "20.00")

    def test_repeated_item_quantity_counts_towards_volume(self):
        self.set_product_measurements(weight=2, length=50, width=40, height=20, quantity=3)
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["customer_delivery_price"], "20.00")

    def test_tbilisi_does_not_treat_stacked_quote_height_as_an_item_side(self):
        self.set_product_measurements(weight=1, length=10, width=10, height=50, quantity=3)
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["measurements"]["height"], "150.00")
        self.assertEqual(response.data["customer_delivery_price"], "10.00")

    def test_product_measurements_override_large_category_defaults(self):
        item = self.set_product_measurements(weight=1, length=20, width=10, height=5)
        Category.objects.filter(pk=item.product.category_id).update(
            default_shipping_weight_kg=Decimal("20"),
            default_shipping_length_cm=Decimal("150"),
            default_shipping_width_cm=Decimal("120"),
            default_shipping_height_cm=Decimal("20"),
        )
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["customer_delivery_price"], "10.00")

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_missing_product_measurement_rejects_both_routes_despite_category_defaults(self, from_settings):
        for field in ("weight_kg", "length_cm", "width_cm", "height_cm"):
            self.set_product_measurements(weight=2, length=20, width=30, height=10, quantity=2)
            Product.objects.filter(slug="test-part").update(**{f"shipping_{field}": None})
            for region, city in ((self.tbilisi, self.tbilisi_city), (self.regional, self.regional_city)):
                with self.subTest(field=field, region=region.external_id):
                    response = self.quote(region, city)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.data["code"], "shipping_measurements_missing")
        from_settings.assert_not_called()

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_buy_now_uses_same_tbilisi_tariff(self, from_settings):
        item = self.set_product_measurements(weight=1, length=50, width=40, height=20)
        session = BuyNowSession.objects.create(
            user=self.user, product=item.product, quantity=1,
            unit_price_snapshot=item.product.price,
        )
        for quantity, price in ((1, "10.00"), (3, "20.00")):
            with self.subTest(quantity=quantity):
                session.quantity = quantity
                session.save(update_fields=["quantity"])
                response = self.quote(self.tbilisi, self.tbilisi_city, source="buy_now")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["customer_delivery_price"], price)
        from_settings.assert_not_called()

    def test_large_quote_is_signed_and_carried_to_order_fields(self):
        self.set_product_measurements(weight=8, length=140, width=120, height=15)
        response = self.quote(self.tbilisi, self.tbilisi_city)
        self.assertEqual(response.status_code, 200)
        items = list(CartItem.objects.filter(cart__user=self.user).select_related("product__category"))
        payload = validate_delivery_quote(
            quote_token=response.data["quote_token"], source="cart", items=items,
            region=self.tbilisi, city=self.tbilisi_city,
        )
        fields = delivery_order_fields(payload)
        self.assertEqual(fields["delivery_price"], Decimal("20.00"))
        self.assertEqual(fields["delivery_provider"], "internal")
        self.assertEqual(fields["carrier_delivery_cost"], Decimal("0.00"))
        self.assertEqual(fields["delivery_margin"], Decimal("0.00"))

        items[0].quantity = 2
        with self.assertRaises(DeliveryQuoteError) as error:
            validate_delivery_quote(
                quote_token=response.data["quote_token"], source="cart", items=items,
                region=self.tbilisi, city=self.tbilisi_city,
            )
        self.assertEqual(error.exception.code, "delivery_quote_stale")

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_large_regional_order_still_uses_easyway_price(self, from_settings):
        self.set_product_measurements(weight=12, length=140, width=120, height=15)
        easyway_client = Mock()
        easyway_client.get_shipping_price.return_value = Decimal("35.00")
        from_settings.return_value = easyway_client
        response = self.quote(self.regional, self.regional_city)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], "easyway")
        self.assertEqual(response.data["customer_delivery_price"], "37.00")
        easyway_client.get_shipping_price.assert_called_once_with(
            weight=Decimal("12.00"), length=Decimal("140.00"),
            width=Decimal("120.00"), height=Decimal("15.00"),
            from_city_id=11, to_city_id=21, package_id=2,
        )

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_regional_quote_uses_easyway_price_and_adds_margin(self, from_settings):
        easyway_client = Mock()
        easyway_client.get_shipping_price.return_value = Decimal("9.00")
        from_settings.return_value = easyway_client

        response = self.quote(self.regional, self.regional_city)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], "easyway")
        self.assertEqual(response.data["carrier_delivery_cost"], "9.00")
        self.assertEqual(response.data["delivery_margin"], "2.00")
        self.assertEqual(response.data["customer_delivery_price"], "11.00")
        easyway_client.get_shipping_price.assert_called_once_with(
            length=Decimal("20.00"),
            width=Decimal("30.00"),
            height=Decimal("20.00"),
            weight=Decimal("4.00"),
            from_city_id=11,
            to_city_id=21,
            package_id=2,
        )
