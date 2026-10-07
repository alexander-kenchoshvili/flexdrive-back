from decimal import Decimal
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from catalog.models import (
    CUSTOMER_STOCK_RESERVE_QTY, Brand, Category, Product, ProductFitment, ProductPlacement, ProductSide,
    ProductStatus, VehicleEngine, VehicleMake, VehicleModel,
)


class CatalogSearchRegressionTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Search parts", slug="search-parts")
        self.left = self.product("სარკის ქვედა ხუფი (LH)", "mirror-left", side=ProductSide.LEFT)
        self.right = self.product("სარკის ქვედა ხუფი (RH)", "mirror-right", side=ProductSide.RIGHT)
        self.legacy_left = self.product("სარკის ქვედა ხუფი - LH", "mirror-legacy-left")
        self.legacy_right = self.product("სარკის ქვედა ხუფი - RH", "mirror-legacy-right")
        self.mechanism = self.product("სარკის ქვედა მექანიზმი (LH)", "mirror-mechanism", side=ProductSide.LEFT)
        self.upper = self.product("სარკის ზედა ხუფი (LH)", "mirror-upper", side=ProductSide.LEFT,
                                  placement=ProductPlacement.UPPER)
        self.other = self.product("სხვა ქვედა ხუფი (LH)", "other-cover", side=ProductSide.LEFT)

    def product(self, name, slug, **overrides):
        values = {
            "category": self.category, "name": name, "slug": slug,
            "sku": f"PRIVATE-{slug}", "internal_sku": f"FD-03-{Product.objects.count() + 1:04d}",
            "price": Decimal("30.00"), "stock_qty": CUSTOMER_STOCK_RESERVE_QTY + 5,
            "status": ProductStatus.PUBLISHED, "placement": ProductPlacement.LOWER,
        }
        values.update(overrides)
        return Product.objects.create(**values)

    def assert_search_ids(self, query, expected, **params):
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            with self.subTest(endpoint=endpoint, query=query):
                response = self.client.get(reverse(endpoint), {"q": query, **params})
                self.assertEqual(response.status_code, 200)
                rows = response.data["results"] if endpoint == "catalog-product-list" else response.data
                self.assertEqual({row["id"] for row in rows}, {product.pk for product in expected})

    def test_full_mirror_name_matches_on_both_endpoints(self):
        self.assert_search_ids("სარკის ქვედა ხუფი (LH)", [self.left, self.legacy_left])

    def test_right_mirror_does_not_match_left_side(self):
        self.assert_search_ids("სარკის ქვედა ხუფი (RH)", [self.right, self.legacy_right])

    def test_bracketed_side_matches_unbracketed_saved_name_without_side_field(self):
        self.assert_search_ids("(LH)", [self.left, self.legacy_left, self.mechanism, self.upper, self.other])

    def test_unbracketed_side_matches_bracketed_saved_name(self):
        self.assert_search_ids("სარკის ქვედა ხუფი LH", [self.left, self.legacy_left])

    def test_copied_dash_name_matches_both_side_spellings(self):
        self.assert_search_ids("სარკის ქვედა ხუფი - LH", [self.left, self.legacy_left])

    def test_multiple_product_words_are_all_required(self):
        self.assert_search_ids("სარკის ქვედა ხუფი", [self.left, self.right, self.legacy_left, self.legacy_right])

    def test_missing_product_word_still_returns_no_results(self):
        self.assert_search_ids("სარკის ქვედა ხუფი არარსებული (LH)", [])

    def test_extra_whitespace_and_word_order_do_not_break_attribute_search(self):
        self.assert_search_ids("  ხუფი   ქვედა   სარკის   (lh)  ", [self.left, self.legacy_left])

    def test_rear_bumper_full_name_still_matches(self):
        bumper = self.product("უკანა ბამპერის ქვედა ტუჩი", "rear-bumper", placement=ProductPlacement.REAR)
        self.product("წინა ბამპერის ქვედა ტუჩი", "front-bumper", placement=ProductPlacement.FRONT)
        self.assert_search_ids("უკანა ბამპერის ქვედა ტუჩი", [bumper])

    def test_vehicle_constraints_are_preserved_with_full_product_name(self):
        subaru = VehicleMake.objects.create(name="Subaru", slug="subaru")
        forester = VehicleModel.objects.create(make=subaru, name="Forester", slug="forester")
        ProductFitment.objects.create(product=self.left, vehicle_model=forester, year_from=2012, year_to=2018)
        self.assert_search_ids("Subaru Forester სარკის ქვედა ხუფი (LH)", [self.left])

    def year_search_vehicle(self):
        make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        model = VehicleModel.objects.create(make=make, name="Forester", slug="forester")
        ProductFitment.objects.create(product=self.left, vehicle_model=model, year_from=2019, year_to=2021)
        ProductFitment.objects.create(product=self.legacy_left, vehicle_model=model, year_from=2012, year_to=2018)
        # An unrelated mention of 2019 must not override saved compatibility.
        self.legacy_left.description = "სარკის ხუფი 2019"
        self.legacy_left.save(update_fields=["description"])
        return make, model

    def test_vehicle_year_uses_fitment_not_product_text(self):
        self.year_search_vehicle()
        for query in (
            "Subaru Forester 2019 სარკის ქვედა ხუფი (LH)",
            "2019 სარკის ქვედა ხუფი LH Subaru Forester",
            "ხუფი Subaru 2019 Forester ქვედა სარკის LH",
            "subaru forester 2019 sarkis qveda khufi lh",
            "სუბარუ ფორესტერი 2019 სარკის ქვედა ხუფი LH",
        ):
            self.assert_search_ids(query, [self.left])

    def test_vehicle_year_range_boundaries_and_absent_year(self):
        self.year_search_vehicle()
        for year, expected in ((2012, self.legacy_left), (2018, self.legacy_left),
                               (2019, self.left), (2020, self.left), (2021, self.left)):
            self.assert_search_ids(f"Subaru Forester {year} სარკის ქვედა ხუფი LH", [expected])
        self.assert_search_ids("Subaru Forester 2022 სარკის ქვედა ხუფი LH", [])
        self.assert_search_ids("Subaru Forester სარკის ქვედა ხუფი LH", [self.left, self.legacy_left])

    def test_vehicle_year_alone_with_make_or_model_and_repeated_year(self):
        self.year_search_vehicle()
        for query in ("Subaru Forester 2019", "Subaru 2019", "Forester 2019", "Subaru Forester 2019 2019"):
            self.assert_search_ids(query, [self.left])

    def test_vehicle_year_and_engine_use_the_same_fitment(self):
        make, model = self.year_search_vehicle()
        engine = VehicleEngine.objects.create(model=model, name="2.5", slug="25")
        other_engine = VehicleEngine.objects.create(model=model, name="2.0", slug="20")
        ProductFitment.objects.create(product=self.legacy_left, vehicle_model=model, engine=engine,
                                     year_from=2012, year_to=2018)
        ProductFitment.objects.create(product=self.legacy_left, vehicle_model=model, engine=other_engine,
                                     year_from=2019, year_to=2021)
        exact = self.product(self.left.name, "exact-engine", side=ProductSide.LEFT)
        ProductFitment.objects.create(product=exact, vehicle_model=model, engine=engine,
                                     year_from=2019, year_to=2021)
        self.assert_search_ids("Subaru Forester 2019 2.5 სარკის ქვედა ხუფი LH", [self.left, exact])

    def test_year_search_preserves_universal_and_excludes_inactive_fitments(self):
        make, model = self.year_search_vehicle()
        self.other.is_universal_fitment = True
        self.other.save(update_fields=["is_universal_fitment"])
        self.assert_search_ids("Subaru Forester 2019", [self.left, self.other])
        model.is_active = False
        model.save(update_fields=["is_active"])
        self.assert_search_ids("Subaru 2019", [self.other])

    def test_numeric_models_and_identifiers_are_not_interpreted_as_years(self):
        make = VehicleMake.objects.create(name="Peugeot", slug="peugeot")
        model = VehicleModel.objects.create(make=make, name="2008", slug="2008")
        ProductFitment.objects.create(product=self.left, vehicle_model=model, year_from=2019, year_to=2021)
        self.assert_search_ids("Peugeot 2008 2019 სარკის ქვედა ხუფი LH", [self.left])
        numbered = self.product("ნაწილი 2019", "year-like-name", manufacturer_part_number="20191234")
        self.assert_search_ids("ნაწილი 2019", [numbered])
        self.assert_search_ids("2019", [numbered])
        self.assert_search_ids("201912", [numbered])

    def test_year_name_fallback_cannot_bypass_compatibility(self):
        make, model = self.year_search_vehicle()
        misleading = self.product("Subaru Forester 2019 სარკის ქვედა ხუფი LH", "wrong-year-name", side=ProductSide.LEFT)
        ProductFitment.objects.create(product=misleading, vehicle_model=model, year_from=2012, year_to=2018)
        self.assert_search_ids("Subaru Forester 2019 სარკის ქვედა ხუფი LH", [self.left])

    def test_year_search_keeps_explicit_filters_and_facets(self):
        make, model = self.year_search_vehicle()
        brand = Brand.objects.create(name="Selected brand", slug="selected-brand")
        self.left.brand = brand
        self.left.save(update_fields=["brand"])
        endpoint = reverse("catalog-product-list")
        query = "Subaru Forester 2019 სარკის ქვედა ხუფი LH"
        response = self.client.get(endpoint, {"q": query, "brand": brand.slug, "category": self.category.slug,
                                             "side": "left", "placement": "lower", "in_stock": "true",
                                             "min_price": "30", "max_price": "30", "ordering": "price_asc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [self.left.pk])
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["facets"]["categories"][0]["count"], 1)
        for params in ({"make": make.slug, "model": model.slug, "year": 2018},
                       {"side": "right"}, {"min_price": "31"}, {"in_stock": "false"}):
            response = self.client.get(endpoint, {"q": query, **params})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 0)

    def test_adjacent_product_words_stay_a_phrase_after_attribute_parsing(self):
        product = self.product("Product 0", "numbered-part", side=ProductSide.LEFT)
        self.product("Product 10", "other-numbered-part", side=ProductSide.LEFT)
        self.assert_search_ids("ქვედა Product 0 (LH)", [product])

    def test_attribute_in_middle_of_vehicle_product_search_keeps_fragments(self):
        subaru = VehicleMake.objects.create(name="Subaru", slug="subaru")
        forester = VehicleModel.objects.create(make=subaru, name="Forester", slug="forester")
        ProductFitment.objects.create(product=self.left, vehicle_model=forester, year_from=2012, year_to=2018)
        self.assert_search_ids("სარკის Subaru Forester ქვედა ხუფი (LH)", [self.left])

    def test_attribute_and_product_transliteration_still_match(self):
        self.assert_search_ids("sarkis qveda khufi LH", [self.left, self.legacy_left])

    def test_draft_and_inactive_category_products_are_excluded(self):
        self.product(self.left.name, "draft-cover", status=ProductStatus.DRAFT)
        inactive = Category.objects.create(name="Inactive search", slug="inactive-search", is_active=False)
        self.product(self.left.name, "inactive-cover", category=inactive)
        self.assert_search_ids(self.left.name, [self.left, self.legacy_left])

    def test_company_sku_and_part_number_search_still_work(self):
        self.assert_search_ids(self.left.internal_sku, [self.left])
        self.left.manufacturer_part_number = "MIRROR-001"
        self.left.save(update_fields=["manufacturer_part_number"])
        self.assert_search_ids("MIRROR-001", [self.left])

    def test_supplier_sku_remains_private_in_search(self):
        self.assert_search_ids(self.left.sku, [])

    def test_plain_name_word_order_and_whitespace_are_ignored(self):
        product = self.product("წყლის რადიატორი", "radiator")
        for query in ("რადიატორი წყლის", "წყლის   რადიატორი", "წყლის\t\nრადიატორი", "წყლის\u00a0რადიატორი"):
            self.assert_search_ids(query, [product])

    def test_name_punctuation_and_separators_are_ignored(self):
        product = self.product("ქვედა ცხაურა - Limited / Premium (Sport)", "grille")
        for query in (product.name, "ქვედა ცხაურა Limited Premium Sport", "Premium Sport ცხაურა Limited ქვედა"):
            self.assert_search_ids(query, [product])

    def test_unicode_paste_and_georgian_uppercase_are_normalized(self):
        product = self.product("წყლის რადიატორი", "radiator")
        for query in ("წყლის\u200b რადიატორი\ufeff", "წყლის რადიატორი".upper()):
            self.assert_search_ids(query, [product])

    def test_long_ambiguous_transliteration_does_not_lose_variants(self):
        product = self.product("ქქქქქქქქ", "ambiguous-transliteration")
        self.assert_search_ids("kkkkkkkk", [product])

    def test_plain_numeric_terms_do_not_match_other_numbers(self):
        product = self.product("Product 0", "numbered-zero")
        self.product("Product 10", "numbered-ten")
        self.assert_search_ids("Product 0", [product])

    def test_attribute_synonyms_find_legacy_name_markers(self):
        for query in ("სარკის ქვედა ხუფი მარცხენა", "სარკის lower ხუფი left"):
            self.assert_search_ids(query, [self.left, self.legacy_left])

    def test_side_marker_does_not_match_inside_another_word(self):
        self.product("Wheelhouse panel", "wheelhouse")
        self.assert_search_ids("wheelhouse LH", [])

    def test_punctuation_only_search_does_not_return_the_catalog(self):
        self.assert_search_ids("() --- /", [])

    def test_unknown_token_is_required_for_plain_search_too(self):
        product = self.product("წყლის რადიატორი", "radiator")
        self.assert_search_ids("წყლის რადიატორი არარსებული", [])

    def test_named_product_is_not_hidden_by_vehicle_prefix_collision(self):
        make = VehicleMake.objects.create(name="Kia", slug="kia")
        VehicleModel.objects.create(make=make, name="Sportage", slug="sportage")
        product = self.product("ქვედა ცხაურა Sport", "sport-grille")
        self.assert_search_ids(product.name, [product])
        self.assert_search_ids("Sport ცხაურა ქვედა", [product])

    def test_ambiguous_vehicle_prefix_keeps_all_matching_models(self):
        make = VehicleMake.objects.create(name="Toyota", slug="toyota")
        first = VehicleModel.objects.create(make=make, name="RAV4", slug="rav4")
        second = VehicleModel.objects.create(make=make, name="RAV5", slug="rav5")
        for product, model in ((self.left, first), (self.legacy_left, second)):
            ProductFitment.objects.create(product=product, vehicle_model=model, year_from=2012, year_to=2018)
        self.assert_search_ids("Toyota rav სარკის ქვედა ხუფი LH", [self.left, self.legacy_left])

    def test_shared_model_name_is_resolved_with_selected_make(self):
        toyota = VehicleMake.objects.create(name="Toyota", slug="toyota")
        honda = VehicleMake.objects.create(name="Honda", slug="honda")
        first = VehicleModel.objects.create(make=toyota, name="Shared", slug="shared")
        second = VehicleModel.objects.create(make=honda, name="Shared", slug="shared")
        for product, model in ((self.left, first), (self.legacy_left, second)):
            ProductFitment.objects.create(product=product, vehicle_model=model, year_from=2012, year_to=2018)
        self.assert_search_ids("Honda Shared სარკის ქვედა ხუფი LH", [self.legacy_left])
        self.assert_search_ids("Shared სარკის ქვედა ხუფი LH", [self.left, self.legacy_left])

    def test_vehicle_punctuation_is_ignored(self):
        make = VehicleMake.objects.create(name="Mazda", slug="mazda")
        model = VehicleModel.objects.create(make=make, name="CX5", slug="cx5")
        ProductFitment.objects.create(product=self.left, vehicle_model=model, year_from=2012, year_to=2018)
        self.assert_search_ids("Mazda CX-5 სარკის ქვედა ხუფი LH", [self.left])

    def test_duplicate_fitments_do_not_duplicate_results(self):
        make = VehicleMake.objects.create(name="Toyota", slug="toyota")
        model = VehicleModel.objects.create(make=make, name="RAV4", slug="rav4")
        for year in (2012, 2019):
            ProductFitment.objects.create(product=self.left, vehicle_model=model, year_from=year, year_to=year + 2)
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            response = self.client.get(reverse(endpoint), {"q": "Toyota სარკის ქვედა ხუფი LH"})
            rows = response.data["results"] if endpoint == "catalog-product-list" else response.data
            self.assertEqual([row["id"] for row in rows], [self.left.pk])

    def test_literal_name_fallback_does_not_bypass_explicit_vehicle_filter(self):
        make = VehicleMake.objects.create(name="Kia", slug="kia")
        model = VehicleModel.objects.create(make=make, name="Sportage", slug="sportage")
        product = self.product("ქვედა ცხაურა Sport", "sport-grille")
        response = self.client.get(reverse("catalog-product-list"), {"q": product.name, "make": make.slug, "model": model.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_query_count_stays_bounded_with_more_catalog_rows(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("catalog-product-suggestions"), {"q": self.left.name})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 7)

    def test_audit_is_repeatable_and_preserves_product_values(self):
        before = list(Product.objects.values())
        with TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            call_command("audit_catalog_search", output=str(output), stdout=StringIO())
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["products"], len(before))
        self.assertEqual(report["failures"], [])
        self.assertEqual(list(Product.objects.values()), before)

    def test_audit_does_not_query_remote_databases(self):
        with patch("catalog.management.commands.audit_catalog_search.connection") as database:
            database.vendor = "postgresql"
            with self.assertRaises(CommandError):
                call_command("audit_catalog_search", stdout=StringIO())

    def test_identifier_coinciding_with_vehicle_prefix_remains_searchable(self):
        make = VehicleMake.objects.create(name="Toyota", slug="toyota")
        model = VehicleModel.objects.create(make=make, name="RAV4", slug="rav4")
        ProductFitment.objects.create(product=self.right, vehicle_model=model, year_from=2012, year_to=2018)
        self.left.manufacturer_part_number = "RAV"
        self.left.save(update_fields=["manufacturer_part_number"])
        self.assert_search_ids("RAV", [self.left, self.right])

    def test_exact_identifier_is_not_hidden_by_in_stock_partial_matches(self):
        self.left.manufacturer_part_number = "EXACT-1234"
        self.left.stock_qty = 0
        self.left.save(update_fields=["manufacturer_part_number", "stock_qty"])
        for index in range(6):
            self.product(f"Other part {index}", f"partial-identifier-{index}",
                         manufacturer_part_number=f"EXACT-1234-{index}")
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            response = self.client.get(reverse(endpoint), {"q": "EXACT-1234"})
            rows = response.data["results"] if endpoint == "catalog-product-list" else response.data
            self.assertEqual(response.status_code, 200)
            self.assertEqual(rows[0]["id"], self.left.pk)

    def test_exact_name_is_not_hidden_by_in_stock_related_products(self):
        target = self.product("წყლის რადიატორი", "radiator", stock_qty=0)
        for index in range(6):
            self.product(f"წყლის რადიატორის სამაგრი {index}", f"radiator-accessory-{index}")
        for endpoint in ("catalog-product-list", "catalog-product-suggestions"):
            response = self.client.get(reverse(endpoint), {"q": target.name})
            rows = response.data["results"] if endpoint == "catalog-product-list" else response.data
            self.assertEqual(response.status_code, 200)
            self.assertEqual(rows[0]["id"], target.pk)

    def test_numeric_identifier_prefixes_still_work(self):
        self.left.manufacturer_part_number = "12345678"
        self.left.save(update_fields=["manufacturer_part_number"])
        self.assert_search_ids("1234", [self.left])

    def test_invalid_and_empty_queries_have_predictable_responses(self):
        suggestions = reverse("catalog-product-suggestions")
        listing = reverse("catalog-product-list")
        for query in ("", " ", "ფ"):
            response = self.client.get(suggestions, {"q": query})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, [])
        response = self.client.get(listing, {"q": "ფ"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("q", response.data)
        for endpoint in (listing, suggestions):
            response = self.client.get(endpoint, {"q": "a" * 256})
            self.assertEqual(response.status_code, 400)
            self.assertIn("q", response.data)

    def test_audit_can_fail_automatically_when_a_product_is_not_found(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            with patch("catalog.management.commands.audit_catalog_search.search_cases",
                       return_value=[("full_name", "definitely nonexistent search")]):
                with self.assertRaises(CommandError):
                    call_command("audit_catalog_search", output=str(output), fail_on_missing=True, stdout=StringIO())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["failed_checks"], Product.objects.count())

    def test_full_product_names_above_the_old_100_character_limit_work(self):
        product = self.product("საძიებო ნაწილი " * 10 + "ფარი", "long-name")
        self.assertGreater(len(product.name), 100)
        self.assert_search_ids(product.name, [product])

    def test_company_sku_works_with_optional_separators(self):
        for query in (self.left.internal_sku.replace("-", ""), self.left.internal_sku.replace("-", " ")):
            self.assert_search_ids(query.lower(), [self.left])
