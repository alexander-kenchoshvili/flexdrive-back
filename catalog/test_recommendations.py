from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Brand, Category, Product, ProductFitment, ProductImage, VehicleEngine, VehicleMake, VehicleModel
from .recommendations import recommended_products


@override_settings(STOREFRONT_ACCESS_GUARD_ENABLED=False)
class CatalogRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Parts", slug="recommendation-parts")
        cls.make = VehicleMake.objects.create(name="Subaru", slug="recommendation-subaru")
        cls.model = VehicleModel.objects.create(make=cls.make, name="Forester", slug="recommendation-forester")
        cls.other_model = VehicleModel.objects.create(make=cls.make, name="Legacy", slug="recommendation-legacy")
        cls.hoods = [cls.part(f"კაპოტი {i}") for i in range(100)]
        cls.primary = [cls.part(name) for name in ("წინა ფარი (LH)", "წინა ბამპერი", "წინა კრილო (RH)", "წინა კარები (LH)", "სარკე გათბობით", "წყლის რადიატორი", "ცხაურა", "წინა ბალკა")]
        cls.small = [cls.part(name, price="3") for name in ("დისკის ბოლტი", "წინა ფარის სამაგრი", "კაპოტის პეტლი", "წინა ბამპერის სალასკა", "სარკის ზედა ხუფი", "წინა ფარი სალასკა - LH")]
        cls.other = cls.part("წინა ამორტიზატორი")
        cls.unavailable = cls.part("კაპოტი უნაშთო", stock=0)
        # Two matching fitments must still yield exactly one product for make filters.
        ProductFitment.objects.create(product=cls.primary[0], vehicle_model=cls.other_model, year_from=2015, year_to=2018)

    @classmethod
    def part(cls, name, price="150", stock=12):
        n = Product.objects.count() + 1
        p = Product.objects.create(
            category=cls.category, name=name, slug=f"rec-{n}", sku=f"REC-{n}",
            internal_sku=f"FD-01-{n:04d}", status="published", price=Decimal(price), stock_qty=stock,
        )
        ProductFitment.objects.create(product=p, vehicle_model=cls.model, year_from=2015, year_to=2018)
        return p

    def listing(self, **params):
        response = self.client.get(reverse("catalog-product-list"), params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_first_page_mixes_main_types_even_with_a_hundred_hoods(self):
        page = self.listing()
        ids = [p["id"] for p in page["results"]]
        self.assertTrue(set(p.pk for p in self.primary).issubset(ids))
        self.assertFalse(set(p.pk for p in self.small).intersection(ids))
        self.assertEqual(len(set(ids)), len(ids))

    def test_classification_keeps_accessories_out_of_main_families(self):
        rows = recommended_products(Product.objects.filter(pk__in=[p.pk for p in self.small]))
        self.assertTrue(all(p.merch_family == "small" and p.merch_tier == 2 for p in rows))

    def test_all_pages_are_stable_complete_and_unique(self):
        first = self.listing(page_size=25)
        ids = []
        for page in range(1, first["total_pages"] + 1):
            rows = self.listing(page_size=25, page=page)["results"]
            ids.extend(p["id"] for p in rows)
            self.assertEqual(rows, self.listing(page_size=25, page=page)["results"])
        expected = set(Product.objects.values_list("pk", flat=True))
        self.assertEqual(set(ids), expected)
        self.assertEqual(len(ids), len(expected))
        self.assertEqual(ids[-1], self.unavailable.pk)

    def test_make_model_filters_keep_mixing_without_duplicate_join_rows(self):
        for params in ({"make": self.make.slug}, {"make": self.make.slug, "model": self.model.slug}):
            with self.subTest(params=params):
                page = self.listing(**params)
                self.assertEqual(page["count"], Product.objects.count())
                ids = [p["id"] for p in page["results"]]
                self.assertTrue(set(p.pk for p in self.primary).issubset(ids))
                self.assertTrue(all(p["compatibility"]["matched"] for p in page["results"]))

    def test_search_and_explicit_price_order_do_not_use_merchandising(self):
        target = self.small[0]
        page = self.listing(q=target.internal_sku)
        self.assertEqual(page["results"][0]["id"], target.pk)
        self.assertEqual(self.listing(q="ბოლტი")["results"][0]["id"], target.pk)
        self.assertEqual(self.listing(ordering="price_asc")["results"][0]["price"], "3.00")
        self.assertEqual(self.listing(ordering="newest")["results"][0]["id"], self.other.pk)

    def test_explicit_recommended_matches_default_and_retains_search_relevance(self):
        self.assertEqual(self.listing()["results"], self.listing(ordering="recommended")["results"])
        target = self.small[1]
        self.assertEqual(self.listing(q=target.internal_sku, ordering="recommended")["results"][0]["id"], target.pk)

    def test_other_filters_and_facets_keep_their_full_counts(self):
        page = self.listing(category=self.category.slug, in_stock=True)
        self.assertEqual(page["count"], Product.objects.count() - 1)
        self.assertEqual(page["facets"]["categories"][0]["count"], page["count"])
        price_page = self.listing(max_price=3)
        self.assertEqual({p["id"] for p in price_page["results"]}, {p.pk for p in self.small})

    def test_multiple_matching_images_do_not_duplicate_recommended_products(self):
        target = self.primary[0]
        ProductImage.objects.create(product=target, image_desktop="test/one.webp")
        ProductImage.objects.create(product=target, image_desktop="test/two.webp")
        page = self.listing(has_image=True)
        self.assertEqual(page["count"], 1)
        self.assertEqual([p["id"] for p in page["results"]], [target.pk])

    def pair(self, name="წინა ფარი", **overrides):
        left, right = self.part(f"{name} (LH)"), self.part(f"{name} (RH)")
        for product, side in ((left, "left"), (right, "right")):
            Product.objects.filter(pk=product.pk).update(side=side, placement="front", **overrides)
        return left, right

    def test_pairs_share_one_family_turn_and_remain_adjacent_through_pagination(self):
        pairs = [self.pair(name) for name in ("წინა ფარი შავი", "წინა კრილო", "წინა კარები", "წინა გიტარა")]
        # A featured side promotes the pair as one group, never separates it.
        Product.objects.filter(pk=pairs[0][1].pk).update(is_featured=True)
        for params in ({}, {"make": self.make.slug}, {"make": self.make.slug, "model": self.model.slug}):
            with self.subTest(params=params):
                first = self.listing(page_size=15, **params)
                self.assertEqual(len(first["results"]), 15)
                self.assertEqual(first["total_pages"], (first["count"] + 14) // 15)
                ids = [p["id"] for p in first["results"]]
                for number in range(2, first["total_pages"] + 1):
                    page = self.listing(page=number, page_size=15, **params)
                    if number < first["total_pages"]:
                        self.assertEqual(len(page["results"]), 15)
                    ids.extend(p["id"] for p in page["results"])
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(set(ids), set(Product.objects.values_list("pk", flat=True)))
                for left, right in pairs:
                    self.assertEqual(abs(ids.index(left.pk) - ids.index(right.pk)), 1)
                self.assertEqual(first["results"], self.listing(page_size=15, **params)["results"])
        rows = {p.pk: p for p in recommended_products(Product.objects.all())}
        for left, right in pairs:
            self.assertEqual(rows[left.pk].merch_group, rows[right.pk].merch_group)
            self.assertEqual(rows[left.pk].merch_round, rows[right.pk].merch_round)

    def test_pairing_requires_exact_variant_brand_placement_category_and_full_fitments(self):
        for dimension in ("name", "steering", "brand", "placement", "category", "model", "years", "engine", "notes", "notes_side", "extra_fitment"):
            with self.subTest(dimension=dimension):
                left, right = self.pair(f"წინა ფარი {dimension}")
                if dimension == "name":
                    Product.objects.filter(pk=right.pk).update(name=f"წინა ფარი {dimension} LED (RH)")
                elif dimension == "steering":
                    Product.objects.filter(pk=left.pk).update(name="წინა ფარი (LH) left hand drive")
                    Product.objects.filter(pk=right.pk).update(name="წინა ფარი (RH) right hand drive")
                elif dimension == "brand":
                    brand = Brand.objects.create(name="Other brand", slug="pair-other-brand")
                    Product.objects.filter(pk=right.pk).update(brand=brand)
                elif dimension == "placement":
                    Product.objects.filter(pk=right.pk).update(placement="rear")
                elif dimension == "category":
                    category = Category.objects.create(name="Other category", slug="pair-other-category")
                    Product.objects.filter(pk=right.pk).update(category=category)
                elif dimension == "model":
                    ProductFitment.objects.filter(product=right).update(vehicle_model=self.other_model)
                elif dimension == "years":
                    ProductFitment.objects.filter(product=right).update(year_from=2016)
                elif dimension == "engine":
                    engine = VehicleEngine.objects.create(model=self.model, name="2.0", slug="pair-engine")
                    ProductFitment.objects.filter(product=right).update(engine=engine)
                elif dimension == "notes":
                    ProductFitment.objects.filter(product=right).update(notes="LED only")
                elif dimension == "notes_side":
                    ProductFitment.objects.filter(product=left).update(notes="Left hand drive")
                    ProductFitment.objects.filter(product=right).update(notes="Right hand drive")
                else:
                    ProductFitment.objects.create(product=right, vehicle_model=self.other_model, year_from=2015, year_to=2018)
                queryset = Product.objects.filter(pk__in=[left.pk, right.pk])
                if dimension == "extra_fitment":
                    queryset = queryset.filter(pk__in=Product.objects.filter(fitments__vehicle_model=self.model).values("pk"))
                rows = {p.pk: p for p in recommended_products(queryset)}
                self.assertNotEqual(rows[left.pk].merch_group, rows[right.pk].merch_group)
                left.delete()
                right.delete()

    def test_pairing_accepts_side_words_and_name_only_markers_but_skips_ambiguous_rows(self):
        left, right = self.pair("სარკე გათბობით")
        Product.objects.filter(pk=left.pk).update(name="სარკე გათბობით — მარცხენა", side="")
        Product.objects.filter(pk=right.pk).update(name="სარკე გათბობით — მარჯვენა", side="")
        rows = {p.pk: p for p in recommended_products(Product.objects.all())}
        self.assertEqual(rows[left.pk].merch_group, rows[right.pk].merch_group)
        for condition in ("conflict", "duplicates", "no_fitments"):
            with self.subTest(condition=condition):
                a, b = self.pair(f"წინა ფარი {condition}")
                if condition == "conflict":
                    Product.objects.filter(pk=b.pk).update(side="left")
                elif condition == "duplicates":
                    duplicate = self.part(a.name)
                    Product.objects.filter(pk=duplicate.pk).update(placement="front")
                else:
                    ProductFitment.objects.filter(product__in=[a, b]).delete()
                rows = {p.pk: p for p in recommended_products(Product.objects.all())}
                self.assertNotEqual(rows[a.pk].merch_group, rows[b.pk].merch_group)

    def test_pairing_preserves_availability_filters_and_explicit_ordering(self):
        left, right = self.pair("წინა ფარი წყვილი")
        Product.objects.filter(pk=left.pk).update(price=50)
        Product.objects.filter(pk=right.pk).update(price=60, stock_qty=0)
        rows = {p.pk: p for p in recommended_products(Product.objects.all())}
        self.assertNotEqual(rows[left.pk].merch_group, rows[right.pk].merch_group)
        self.assertNotIn(right.pk, [p["id"] for p in self.listing(in_stock=True, page_size=100)["results"]])
        # Filtering one side out never pulls the partner into the results.
        self.assertEqual([p["id"] for p in self.listing(min_price=50, max_price=50)["results"]], [left.pk])
        self.assertEqual(self.listing(q=right.internal_sku)["results"][0]["id"], right.pk)
        page = self.listing(ordering="price_asc", page_size=100)
        self.assertNotIn(right.pk, [p["id"] for p in page["results"]])  # Unavailable still follows all stocked items.
