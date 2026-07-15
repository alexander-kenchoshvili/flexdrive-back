from unittest.mock import Mock, patch
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from commerce.easyway_locations import sync_easyway_locations
from catalog.models import Category, Product, ProductStatus
from commerce.models import Cart, CartItem, EasywayCity, EasywayRegion


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
            short_description="Part",
            description="Part",
            price=Decimal("100.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=2,
            unit_price_snapshot=product.price,
        )

    def quote(self, region, city):
        return self.client.post(
            reverse("commerce-delivery-quote"),
            {
                "source": "cart",
                "delivery_region_id": region.external_id,
                "delivery_city_id": city.external_id,
            },
            format="json",
        )

    @patch("commerce.delivery_quotes.EasywayClient.from_settings")
    def test_internal_quote_is_free_without_calling_easyway(self, from_settings):
        response = self.quote(self.tbilisi, self.tbilisi_city)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], "internal")
        self.assertEqual(response.data["customer_delivery_price"], "0.00")
        self.assertTrue(response.data["quote_token"])
        from_settings.assert_not_called()

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
