from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .models import (
    Brand, Category, Product, ProductFitment, ProductStatus, VehicleMake, VehicleModel,
)


class RefinementFacetTests(APITestCase):
    def setUp(self):
        self.lights = Category.objects.create(name="Lights", slug="lights")
        self.mirrors = Category.objects.create(name="Mirrors", slug="mirrors")
        self.other_category = Category.objects.create(name="Other", slug="other")
        self.hidden_category = Category.objects.create(name="Hidden", slug="hidden", is_active=False)
        self.alpha = Brand.objects.create(name="Alpha", slug="alpha")
        self.beta = Brand.objects.create(name="Beta", slug="beta")
        self.gamma = Brand.objects.create(name="Gamma", slug="gamma")
        make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        self.model = VehicleModel.objects.create(make=make, name="Forester", slug="forester")
        self.other_model = VehicleModel.objects.create(make=make, name="XV", slug="xv")
        self.a = self.product(self.alpha)
        self.b = self.product(self.beta, category=self.mirrors)
        self.c = self.product(self.alpha, placement="rear")
        self.d = self.product(self.alpha, side="right")
        self.e = self.product(self.beta, placement="rear", side="right")
        self.f = self.product(self.alpha, price=Decimal("50"))

    def product(self, brand, *, model=None, year=2015, **overrides):
        number = Product.objects.count() + 1
        values = {
            "category": self.lights, "brand": brand, "placement": "front", "side": "left",
            "name": f"Match part {number}", "slug": f"facet-part-{number}",
            "sku": f"PRIVATE-FACET-{number}", "internal_sku": f"FD-03-{number:04d}",
            "price": Decimal("30"), "old_price": Decimal("90"), "stock_qty": 20,
            "status": ProductStatus.PUBLISHED,
            **overrides,
        }
        product = Product.objects.create(**values)
        ProductFitment.objects.create(
            product=product, vehicle_model=model or self.model, year_from=year, year_to=year + 3,
        )
        return product

    def listing(self, **params):
        response = self.client.get(reverse("catalog-product-list"), params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def counts(self, data, facet):
        key = "slug" if facet == "brands" else "value"
        return {row[key]: row["count"] for row in data["facets"][facet]}

    def test_brand_selection_keeps_other_brand_choices_and_their_counts(self):
        for brand in (self.alpha.slug, str(self.alpha.pk)):
            with self.subTest(brand=brand):
                data = self.listing(brand=brand)
                self.assertEqual(data["count"], 4)
                self.assertEqual(self.counts(data, "brands"), {"alpha": 4, "beta": 2})
                self.assertTrue(all(row["brand"]["slug"] == "alpha" for row in data["results"]))

    def test_placement_selection_keeps_other_placement_choices(self):
        data = self.listing(placement="front")
        self.assertEqual(data["count"], 4)
        self.assertEqual(self.counts(data, "placements"), {"front": 4, "rear": 2})
        self.assertTrue(all(row["placement"] == "front" for row in data["results"]))

    def test_side_selection_keeps_other_side_choices(self):
        data = self.listing(side="left")
        self.assertEqual(data["count"], 4)
        self.assertEqual(self.counts(data, "sides"), {"left": 4, "right": 2})
        self.assertTrue(all(row["side"] == "left" for row in data["results"]))

    def test_each_choice_list_respects_the_other_two_refinements(self):
        data = self.listing(brand="alpha", placement="front", side="left")
        self.assertEqual({row["id"] for row in data["results"]}, {self.a.pk, self.f.pk})
        self.assertEqual(self.counts(data, "brands"), {"alpha": 2, "beta": 1})
        self.assertEqual(self.counts(data, "placements"), {"front": 2, "rear": 1})
        self.assertEqual(self.counts(data, "sides"), {"left": 2, "right": 1})
        self.assertEqual(data["facets"]["categories"][0]["count"], 2)
        self.assertEqual(Decimal(data["facets"]["price"]["min"]), Decimal("30"))
        self.assertEqual(Decimal(data["facets"]["price"]["max"]), Decimal("50"))

    def test_switching_choices_does_not_require_clearing_first(self):
        for brand, expected in (("alpha", {self.a.pk, self.f.pk}), ("beta", {self.b.pk})):
            data = self.listing(brand=brand, placement="front", side="left")
            self.assertEqual({row["id"] for row in data["results"]}, expected)
            self.assertEqual(self.counts(data, "brands"), {"alpha": 2, "beta": 1})

    def test_zero_results_still_offer_choices_that_can_recover_results(self):
        data = self.listing(brand="alpha", placement="rear", side="right")
        self.assertEqual(data["count"], 0)
        self.assertEqual(self.counts(data, "brands"), {"beta": 1, "alpha": 0})
        self.assertEqual(self.counts(data, "placements"), {"front": 1, "rear": 0})
        self.assertEqual(self.counts(data, "sides"), {"left": 1, "right": 0})
        self.assertEqual(data["facets"]["categories"], [])
        self.assertEqual(data["facets"]["price"], {"min": None, "max": None})

    def test_empty_context_keeps_selected_refinements_with_real_labels_and_zero_counts(self):
        for brand in (self.alpha.slug, str(self.alpha.pk)):
            with self.subTest(brand=brand):
                data = self.listing(
                    q="no matching product here", brand=brand, placement="rear", side="right",
                )
                self.assertEqual(data["count"], 0)
                self.assertEqual(data["results"], [])
                self.assertEqual(data["facets"]["brands"], [{
                    "id": self.alpha.pk, "slug": "alpha", "name": "Alpha", "count": 0,
                }])
                self.assertEqual(data["facets"]["placements"], [{
                    "value": "rear", "label": "უკანა", "count": 0,
                }])
                self.assertEqual(data["facets"]["sides"], [{
                    "value": "right", "label": "მარჯვენა", "count": 0,
                }])

    def test_empty_context_without_selections_does_not_invent_choices(self):
        data = self.listing(q="no matching product here")
        for facet in ("brands", "placements", "sides"):
            self.assertEqual(data["facets"][facet], [])

    def test_context_and_public_visibility_constrain_all_three_choice_lists(self):
        for overrides in (
            {"category": self.other_category}, {"category": self.hidden_category},
            {"name": "Unrelated"}, {"status": ProductStatus.DRAFT},
            {"status": ProductStatus.ARCHIVED}, {"model": self.other_model},
            {"year": 2022}, {"price": Decimal("10")},
            {"price": Decimal("100"), "old_price": Decimal("120")},
            {"stock_qty": 0}, {"old_price": None},
        ):
            self.product(self.gamma, **overrides)
        # Two matching fitment rows must still count as one product.
        ProductFitment.objects.create(
            product=self.a, vehicle_model=self.model, year_from=2016, year_to=2018,
        )
        for category_filter in ({"categories": "lights,mirrors"}, {"category": "lights"}):
            with self.subTest(category_filter=category_filter):
                data = self.listing(
                    **category_filter, q="Match", make="subaru", model="forester", year=2017,
                    min_price=20, max_price=80, in_stock="true", on_sale="true",
                    brand="alpha", placement="front", side="left",
                )
                self.assertEqual(data["count"], 2)
                brands = {"alpha": 2, "beta": 1, "gamma": 0} if "categories" in category_filter else {"alpha": 2, "beta": 0, "gamma": 0}
                self.assertEqual(self.counts(data, "brands"), brands)
                self.assertEqual(self.counts(data, "placements"), {"front": 2, "rear": 1})
                self.assertEqual(self.counts(data, "sides"), {"left": 2, "right": 1})

    def test_sort_and_pagination_do_not_slice_refinement_choices(self):
        data = self.listing(brand="alpha", page=2, page_size=1, ordering="price_desc")
        self.assertEqual(data["count"], 4)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(self.counts(data, "brands"), {"alpha": 4, "beta": 2})

    def test_quick_filters_keep_all_context_options_with_zero_counts_and_recover(self):
        Product.objects.update(old_price=None)
        data = self.listing(in_stock="true", on_sale="true")
        self.assertEqual(data["count"], 0)
        self.assertEqual(self.counts(data, "brands"), {"alpha": 0, "beta": 0})
        self.assertEqual(self.counts(data, "placements"), {"front": 0, "rear": 0})
        self.assertEqual(self.counts(data, "sides"), {"left": 0, "right": 0})

        selected = self.listing(in_stock="true", on_sale="true", brand="alpha", side="left")
        self.assertEqual(selected["count"], 0)
        for field in ("brands", "placements", "sides"):
            self.assertEqual(self.counts(selected, field), self.counts(data, field))

        restored = self.listing(in_stock="true", brand="alpha", side="left")
        self.assertEqual(restored["count"], 3)
        self.assertEqual(self.counts(restored, "brands"), {"alpha": 3, "beta": 1})
        self.assertEqual(self.counts(restored, "placements"), {"front": 2, "rear": 1})
        self.assertEqual(self.counts(restored, "sides"), {"left": 3, "right": 1})

    def test_price_filters_keep_zero_count_context_options(self):
        data = self.listing(min_price=999)
        self.assertEqual(data["count"], 0)
        self.assertEqual(self.counts(data, "brands"), {"alpha": 0, "beta": 0})
        self.assertEqual(self.counts(data, "placements"), {"front": 0, "rear": 0})
        self.assertEqual(self.counts(data, "sides"), {"left": 0, "right": 0})

    def test_option_vocabulary_remains_scoped_to_search_vehicle_category_and_visibility(self):
        for overrides in (
            {"category": self.other_category}, {"category": self.hidden_category},
            {"name": "Unrelated"}, {"status": ProductStatus.DRAFT},
            {"status": ProductStatus.ARCHIVED}, {"model": self.other_model}, {"year": 2022},
        ):
            self.product(self.gamma, placement="upper", side="both", **overrides)
        for category_filter in ({"categories": "lights,mirrors"}, {"category": "lights"}):
            data = self.listing(
                **category_filter, q="Match", make="subaru", model="forester", year=2017,
                min_price=999, in_stock="true", on_sale="true",
            )
            self.assertEqual(data["count"], 0)
            expected = {"alpha": 0, "beta": 0}
            self.assertEqual(self.counts(data, "brands"), expected)
            self.assertEqual(self.counts(data, "placements"), {"front": 0, "rear": 0})
            self.assertEqual(self.counts(data, "sides"), {"left": 0, "right": 0})

    def test_counts_stay_distinct_and_newly_zero_alternatives_remain_visible(self):
        self.product(self.gamma, placement="upper", side="both")
        ProductFitment.objects.create(
            product=self.a, vehicle_model=self.model, year_from=2016, year_to=2018,
        )
        data = self.listing(make="subaru", model="forester", year=2017, brand="alpha", side="left")
        self.assertEqual(data["count"], 3)
        self.assertEqual(self.counts(data, "brands"), {"alpha": 3, "beta": 1, "gamma": 0})
        self.assertEqual(self.counts(data, "placements"), {"front": 2, "rear": 1, "upper": 0})
        self.assertEqual(self.counts(data, "sides"), {"left": 3, "right": 1, "both": 0})

    def test_invalid_refinements_still_return_validation_errors(self):
        for field in ("brand", "placement", "side"):
            with self.subTest(field=field):
                response = self.client.get(reverse("catalog-product-list"), {field: "missing"})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
