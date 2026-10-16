from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Category, Product, ProductFitment, ProductStatus, VehicleMake, VehicleModel


class HeaderSearchFilterTests(APITestCase):
    def setUp(self):
        self.lights = Category.objects.create(name="Lights", slug="lights")
        self.mirrors = Category.objects.create(name="Mirrors", slug="mirrors")
        self.body = Category.objects.create(name="Body", slug="body")
        self.hidden_category = Category.objects.create(name="Hidden", slug="hidden", is_active=False)
        self.make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        self.model = VehicleModel.objects.create(make=self.make, name="Forester", slug="forester")
        self.other_model = VehicleModel.objects.create(make=self.make, name="XV", slug="xv")
        self.light = self.product("light", self.lights)
        self.mirror = self.product("mirror", self.mirrors)
        self.product("body", self.body)
        self.product("hidden", self.hidden_category)
        self.product("draft", self.lights, status=ProductStatus.DRAFT)
        self.product("archived", self.mirrors, status=ProductStatus.ARCHIVED)
        for product in (self.light, self.mirror):
            ProductFitment.objects.create(product=product, vehicle_model=self.model, year_from=2015, year_to=2018)
        self.outside_year = self.product("outside-year", self.lights)
        ProductFitment.objects.create(product=self.outside_year, vehicle_model=self.model, year_from=2019, year_to=2021)
        self.other_vehicle = self.product("other-vehicle", self.mirrors)
        ProductFitment.objects.create(product=self.other_vehicle, vehicle_model=self.other_model, year_from=2015, year_to=2018)

    def product(self, code, category, **kwargs):
        return Product.objects.create(
            category=category, name=f"Search part {code}", slug=f"header-{code}",
            sku=f"PRIVATE-{code}", internal_sku=f"FD-03-{Product.objects.count() + 1:04d}",
            price=Decimal("30"), stock_qty=20, **{"status": ProductStatus.PUBLISHED, **kwargs},
        )

    def rows(self, endpoint, params, status=200):
        response = self.client.get(reverse(endpoint), params)
        self.assertEqual(response.status_code, status, response.data)
        if status != 200:
            return response.data
        return response.data["results"] if endpoint == "catalog-product-list" else response.data

    def test_category_union_intersects_text_vehicle_and_year_on_both_endpoints(self):
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            rows = self.rows(endpoint, {"q": "Search part", "categories": "lights,mirrors", "make": "subaru", "model": "forester", "year": 2018})
            self.assertEqual({row["id"] for row in rows}, {self.light.pk, self.mirror.pk})

    def test_categories_only_and_duplicate_mixed_identifiers(self):
        rows = self.rows("catalog-product-list", {"categories": f"lights,{self.mirrors.pk},lights"})
        self.assertEqual({row["id"] for row in rows}, {self.light.pk, self.mirror.pk, self.outside_year.pk, self.other_vehicle.pk})

    def test_header_can_list_all_active_categories_including_empty_ones(self):
        empty = Category.objects.create(name="Empty", slug="empty")
        url = reverse("catalog-category-list")
        default = self.client.get(url)
        self.assertNotIn(empty.pk, {row["id"] for row in default.data})
        response = self.client.get(url, {"include_empty": "true"})
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data}
        self.assertIn(empty.pk, ids)
        self.assertNotIn(self.hidden_category.pk, ids)
        self.assertEqual(self.client.get(url, {"include_empty": "invalid"}).status_code, 400)

    def test_repeated_category_parameters_are_combined(self):
        rows = self.rows("catalog-product-list", {"categories": ["lights", "mirrors"], "make": "subaru", "model": "forester", "year": 2015})
        self.assertEqual({row["id"] for row in rows}, {self.light.pk, self.mirror.pk})

    def test_existing_category_contract_is_retained(self):
        for category in ("lights", str(self.lights.pk)):
            rows = self.rows("catalog-product-list", {"category": category})
            self.assertEqual({row["id"] for row in rows}, {self.light.pk, self.outside_year.pk})
        self.assertEqual(self.rows("catalog-product-list", {"category": "missing"}), [])

    def test_single_category_and_plural_selection_intersect(self):
        rows = self.rows("catalog-product-list", {"category": "mirrors", "categories": "lights,mirrors"})
        self.assertEqual({row["id"] for row in rows}, {self.mirror.pk, self.other_vehicle.pk})

    def test_invalid_plural_categories_do_not_silently_broaden_results(self):
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            for value in ("missing", "lights,missing", "hidden", "lights,", ",", "0", "9" * 255, ",".join(["lights"] * 101)):
                with self.subTest(endpoint=endpoint, value=value):
                    self.assertIn("categories", self.rows(endpoint, {"q": "Search part", "categories": value}, status=400))

    def test_suggestions_apply_vehicle_without_a_category(self):
        rows = self.rows("catalog-product-suggestions", {"q": "Search part", "make": "subaru", "model": "forester", "year": 2020})
        self.assertEqual([row["id"] for row in rows], [self.outside_year.pk])

    def test_invalid_vehicle_combinations_are_rejected_by_suggestions(self):
        self.rows("catalog-product-suggestions", {"q": "Search part", "model": "forester"}, status=400)
        self.rows("catalog-product-suggestions", {"q": "Search part", "make": "subaru", "year": "bad"}, status=400)

    def test_no_match_and_universal_fitment_preserve_existing_rules(self):
        universal = self.product("universal", self.mirrors, is_universal_fitment=True)
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            rows = self.rows(endpoint, {"q": "Search part", "categories": "mirrors", "make": "subaru", "model": "forester", "year": 2025})
            self.assertEqual([row["id"] for row in rows], [universal.pk])
            self.assertEqual(self.rows(endpoint, {"q": "nonexistent", "categories": "mirrors"}), [])
