from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Category, Product, ProductFitment, ProductStatus, VehicleMake, VehicleModel
from .test_vin import VIN, provider_response
from .variant_hints import extract_mentions, parse_variant_query, variant_hint, variant_keys
from .vin import _read_provider, resolve_vehicle


class MentionParserTests(SimpleTestCase):
    def test_observed_supplier_names_and_alternative_versions(self):
        self.assertEqual(variant_keys("ცხაურა GLI"), ["gli"])
        self.assertEqual(variant_keys("წინა ბამპერი - Limited / Sport"), ["sport", "limited"])
        self.assertEqual(variant_keys("სანისლე ბუდე სპორტი"), ["sport"])
        self.assertEqual(variant_keys("ჰიბრიდის ფარი"), ["hybrid"])
        self.assertEqual(variant_keys("M Sport", "EX-V6"), ["m_sport", "ex_v6"])

    def test_whole_words_and_body_feature_names_are_not_versions(self):
        for text in ("Sportage", "Sportback", "Sport Utility Vehicle", "Base plate LED SELENIUM", "Sportline", "სალასკა ჰიბრიდულიანი"):
            with self.subTest(text=text):
                self.assertEqual(variant_keys(text), [])

    def test_negative_and_conflicting_mentions_never_promote(self):
        for text in ("non-Hybrid", "not GLI", "except GLI", "GLI-ს გარდა", "GLI-ის გარდა", "GLI არ ერგება", "GLI not compatible", "გარდა GLI", "ჰიბრიდის გარდა", "GLI / not GLI"):
            with self.subTest(text=text):
                hint = variant_hint(["gli", "hybrid"], text)
                self.assertEqual(hint, {"status": "unverified", "labels": []})
        self.assertEqual(extract_mentions("GLI", "GLI-ს გარდა")[0], set())

    def test_no_mention_does_not_mean_all_versions_and_different_is_not_incompatible(self):
        for text in ("წინა ბამპერი", "ბამპერი GTI"):
            self.assertEqual(variant_hint(["gli"], text), {"status": "unverified", "labels": []})
        self.assertEqual(variant_hint(["gli"], "ბამპერი GLI look"), {"status": "mentioned", "labels": ["GLI"]})
        self.assertEqual(variant_hint(["unspecified"], "GLI"), {"status": "unverified", "labels": []})

    def test_query_is_bounded_known_ids_only(self):
        self.assertEqual(parse_variant_query("gli,gli,sport"), ("gli", "sport"))
        for value in ("GLI", "free text", "gli,", "unspecified,gli", "gli,gti,gte,gtd,sport", "x" * 101):
            with self.assertRaises(ValueError):
                parse_variant_query(value)

    @patch("catalog.vin.requests.get")
    def test_decoder_preserves_optional_provider_versions_without_changing_identity(self, get):
        get.return_value = provider_response(Trim="EX-V6", Series="Sport Utility Vehicle", Trim2=None, Series2="x" * 121)
        result = _read_provider(VIN)
        self.assertEqual(result["vehicle"]["trim"], "EX-V6")
        self.assertEqual(result["vehicle"]["model"], "Accord")
        self.assertNotIn("series2", result["vehicle"])
        self.assertEqual(variant_keys(result["vehicle"]["trim"], result["vehicle"]["series"]), ["ex_v6"])


class VariantCatalogTests(APITestCase):
    def setUp(self):
        self.make = VehicleMake.objects.create(name="Volkswagen", slug="vw")
        self.model = VehicleModel.objects.create(make=self.make, name="Jetta", slug="jetta")
        self.category = Category.objects.create(name="Bumpers", slug="bumpers")
        self.unknown = self.product("წინა ბამპერი სტანდარტი", price=90)
        self.gti = self.product("წინა ბამპერი GTI", price=110)
        self.gli = self.product("წინა ბამპერი GLI", price=150)
        self.negative = self.product("წინა ბამპერი GLI-ს გარდა", price=130)
        self.filters = {"make": "vw", "model": "jetta", "year": 2017}

    def product(self, name, price=100, stock=20):
        n = Product.objects.count() + 1
        p = Product.objects.create(
            category=self.category, name=name, slug=f"variant-{n}", sku=f"V-{n}",
            internal_sku=f"FD-01-{n:04d}", price=price, stock_qty=stock, status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(product=p, vehicle_model=self.model, year_from=2015, year_to=2018)
        return p

    def rows(self, **params):
        result = self.client.get(reverse("catalog-product-list"), {**self.filters, **params})
        self.assertEqual(result.status_code, 200, result.data)
        return result.data

    def test_version_changes_priority_and_metadata_but_never_result_membership(self):
        original = self.rows()
        selected = self.rows(variant="gli")
        self.assertEqual(original["count"], selected["count"])
        self.assertEqual({p["id"] for p in original["results"]}, {p["id"] for p in selected["results"]})
        self.assertEqual(selected["results"][0]["id"], self.gli.pk)
        hints = {p["id"]: p["compatibility"]["variant"] for p in selected["results"]}
        self.assertEqual(hints[self.gli.pk], {"status": "mentioned", "labels": ["GLI"]})
        for p in (self.unknown, self.gti, self.negative):
            self.assertEqual(hints[p.pk], {"status": "unverified", "labels": []})
        self.assertNotIn("variant", original["results"][0]["compatibility"])

    def test_unavailable_versions_and_unspecified_keep_every_product(self):
        for variant in ("amg", "unspecified"):
            result = self.rows(variant=variant)
            self.assertEqual(result["count"], 4)
            self.assertTrue(all(p["compatibility"]["variant"]["status"] == "unverified" for p in result["results"]))

    def test_availability_and_explicit_price_order_are_preserved(self):
        self.gli.stock_qty = 0
        self.gli.save(update_fields=["stock_qty"])
        self.assertNotEqual(self.rows(variant="gli")["results"][0]["id"], self.gli.pk)
        ordered = self.rows(variant="gli", ordering="price_asc")["results"]
        self.assertEqual([p["id"] for p in ordered], [self.unknown.pk, self.gti.pk, self.negative.pk, self.gli.pk])

    def test_part_query_and_suggestions_keep_context_without_excluding_other_versions(self):
        result = self.rows(variant="gli", q="წინა ბამპერი")
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["results"][0]["id"], self.gli.pk)
        response = self.client.get(reverse("catalog-product-suggestions"), {**self.filters, "variant": "gli", "q": "წინა ბამპერი"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data[0]["id"], self.gli.pk)
        self.assertEqual(len(response.data), 4)

    def test_only_notes_for_the_selected_vehicle_and_year_affect_priority(self):
        another = VehicleModel.objects.create(make=self.make, name="Golf", slug="golf")
        ProductFitment.objects.create(product=self.unknown, vehicle_model=another, year_from=2015, year_to=2018, notes="GLI")
        ProductFitment.objects.create(product=self.gti, vehicle_model=self.model, year_from=2020, year_to=2022, notes="GLI")
        result = self.rows(variant="gli")
        hints = {p["id"]: p["compatibility"]["variant"]["status"] for p in result["results"]}
        self.assertEqual(hints[self.unknown.pk], "unverified")
        self.assertEqual(hints[self.gti.pk], "unverified")
        own = self.unknown.fitments.get(vehicle_model=self.model)
        own.notes = "Jetta GLI 15-18"
        own.save()
        updated = self.rows(variant="gli")
        self.assertEqual(next(p for p in updated["results"] if p["id"] == self.unknown.pk)["compatibility"]["variant"]["status"], "mentioned")

    def test_pagination_is_stable_complete_and_deduplicated(self):
        for n in range(17):
            self.product("წინა ბამპერი " + ("GLI" if n % 2 else "სხვა"))
        pages = [self.rows(variant="gli", page=page, page_size=15) for page in (1, 2)]
        ids = [p["id"] for page in pages for p in page["results"]]
        self.assertEqual(len(ids), 21)
        self.assertEqual(len(set(ids)), 21)
        self.assertEqual([p["id"] for p in pages[0]["results"]], [p["id"] for p in self.rows(variant="gli", page=1, page_size=15)["results"]])

    def test_invalid_context_is_rejected_and_vin_supplies_version_context(self):
        for params in ({"variant": "unknown"}, {"variant": "gli", "year": ""}, {"variant": "gli", "model": ""}):
            response = self.client.get(reverse("catalog-product-list"), {**self.filters, **params})
            self.assertEqual(response.status_code, 400)
        matched = resolve_vehicle({"make": "Volkswagen", "model": "Jetta", "year": 2017, "trim": "GLI"})
        self.assertEqual(matched["filters"]["variant"], "gli")
        self.assertEqual(matched["vehicle"]["trim"], "GLI")
