import importlib
from decimal import Decimal
from types import SimpleNamespace

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from .admin import ProductAdmin
from .crossmotors_import import (
    build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk,
)
from .models import Brand, Category, Product, ProductFitment, ProductSide, ProductStatus, ProductSupplierSource, VehicleMake, VehicleModel
from .seo import active_seo_fitment_queryset, is_legacy_imported_title
from .serializers import ProductListSerializer


class ProductSeoFixture(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="სარკეები", slug="seo-mirrors")
        self.make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        self.model = VehicleModel.objects.create(make=self.make, name="Forester", slug="forester")
        self.product = Product.objects.create(
            category=self.category, name="სარკის ქვედა ხუფი (RH)",
            sku="CM-000015", internal_sku="FD-02-0001", slug="mirror-cm-000015",
            price=Decimal("90"), supplier_price=Decimal("90"), stock_qty=12,
            supplier_source=ProductSupplierSource.CROSS_MOTORS, side=ProductSide.RIGHT,
        )
        self.fitment = ProductFitment.objects.create(
            product=self.product, vehicle_model=self.model, year_from=2012, year_to=2018,
        )


class ProductSeoTests(ProductSeoFixture):
    def test_automatic_title_uses_name_vehicle_years_and_georgian_side(self):
        self.assertEqual(self.product.effective_seo_title, "Subaru Forester 2012–2018 — სარკის ქვედა ხუფი მარჯვენა")
        self.assertEqual(self.product.seo_title, None)

    def test_left_and_right_parts_have_different_titles(self):
        right = self.product.effective_seo_title
        self.product.name = "სარკის ქვედა ხუფი (LH)"
        self.product.side = ProductSide.LEFT
        self.assertIn("მარცხენა", self.product.effective_seo_title)
        self.assertNotEqual(right, self.product.effective_seo_title)

    def test_title_has_no_repeated_name_metadata(self):
        for name in (
            "Subaru Forester 2012-2018 სარკის მარჯვენა ხუფი",
            "სუბარუ ფორესტერი 2012–2018 სარკის მარჯვენა ხუფი",
        ):
            with self.subTest(name=name):
                self.product.name = name
                self.assertEqual(self.product.effective_seo_title, name)

    def test_compact_model_code_is_not_added_twice_or_confused_with_another_model(self):
        self.make.name = "Mazda"
        self.make.save()
        self.model.name = "CX5"
        self.model.save()
        self.product.name = "Mazda CX-5 2012-2018 მარჯვენა სარკე"
        self.assertEqual(self.product.effective_seo_title, self.product.name)
        self.product.name = "Mazda CX50 მარჯვენა სარკე"
        self.assertIn("CX5 2012–2018 —", self.product.effective_seo_title)

    def test_manual_title_survives_name_and_fitment_edits_until_cleared(self):
        self.product.seo_title = "ჩემი სათაური | FlexDrive"
        self.product.save()
        self.product.name = "ახალი დასახელება"
        self.product.save(update_fields=["name"])
        self.fitment.year_to = 2020
        self.fitment.save()
        self.assertEqual(self.product.effective_seo_title, "ჩემი სათაური | FlexDrive")
        self.product.seo_title = ""
        self.product.save(update_fields=["seo_title"])
        self.assertEqual(self.product.effective_seo_title, "Subaru Forester 2012–2020 — ახალი დასახელება მარჯვენა")

    def test_inactive_or_absent_fitments_do_not_invent_vehicle_metadata(self):
        self.model.is_active = False
        self.model.save()
        self.assertEqual(self.product.effective_seo_title, "სარკის ქვედა ხუფი მარჯვენა")
        self.product.is_universal_fitment = True
        self.assertEqual(self.product.effective_seo_title, "სარკის ქვედა ხუფი მარჯვენა")

    def test_multiple_fitments_are_bounded_and_never_merge_gaps(self):
        ProductFitment.objects.create(product=self.product, vehicle_model=self.model, year_from=2021, year_to=2024)
        other = VehicleModel.objects.create(make=self.make, name="XV", slug="xv")
        ProductFitment.objects.create(product=self.product, vehicle_model=other, year_from=2015, year_to=2019)
        title = self.product.effective_seo_title
        self.assertIn("Forester 2012–2018", title)
        self.assertNotIn("2012–2024", title)
        self.assertNotIn("XV", title)
        self.product.name = "Subaru XV მარჯვენა სარკე"
        self.assertEqual(self.product.effective_seo_title, "2015–2019 — Subaru XV მარჯვენა სარკე")

    def test_name_change_leaves_all_product_urls_and_codes_unchanged(self):
        original = (self.product.slug, self.product.public_slug, self.product.public_canonical_url, self.product.internal_sku)
        self.product.name = "სარკის მარჯვენა საფარი"
        self.product.save(update_fields=["name"])
        self.assertIn("სარკის მარჯვენა საფარი", self.product.effective_seo_title)
        self.assertEqual((self.product.slug, self.product.public_slug, self.product.public_canonical_url, self.product.internal_sku), original)

    def test_known_manufacturer_distinguishes_otherwise_equal_parts_without_repetition(self):
        first = self.product.effective_seo_title
        self.product.brand = Brand.objects.create(name="TYG", slug="tyg")
        second = self.product.effective_seo_title
        self.assertEqual(second, f"{first} — TYG")
        self.product.name = "TYG მარჯვენა სარკე"
        self.assertEqual(self.product.effective_seo_title.count("TYG"), 1)

    def test_bare_side_codes_and_english_side_are_not_repeated(self):
        for name, expected in (("ხუფი RH", "ხუფი მარჯვენა"), ("Right mirror", "Right mirror")):
            self.product.name = name
            self.assertTrue(self.product.effective_seo_title.endswith(expected))

    def test_public_detail_and_list_return_automatic_title_with_stable_contract(self):
        self.product.status = ProductStatus.PUBLISHED
        self.product.save(update_fields=["status"])
        client = APIClient()
        detail = client.get(reverse("catalog-product-detail", args=[self.product.public_slug]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["seo"]["title"], self.product.effective_seo_title)
        self.assertEqual(detail.data["seo"]["canonical"], self.product.public_canonical_url)
        self.assertFalse(detail.data["seo"]["noindex"])
        listing = client.get(reverse("catalog-product-list"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["results"][0]["seo"]["title"], detail.data["seo"]["title"])

    def test_serializing_prefetched_titles_does_not_issue_per_product_queries(self):
        self.product.status = ProductStatus.PUBLISHED
        self.product.save(update_fields=["status"])
        for number in range(2, 8):
            product = Product.objects.create(
                category=self.category, name=f"სარკე {number}", sku=f"SEO-{number}",
                internal_sku=f"FD-02-{number:04d}", status=ProductStatus.PUBLISHED,
                slug=f"seo-{number}", price=10,
            )
            ProductFitment.objects.create(product=product, vehicle_model=self.model, year_from=2012, year_to=2018)
        from django.db.models import Prefetch
        products = list(Product.objects.select_related("category", "brand").prefetch_related(
            "images", Prefetch("fitments", queryset=active_seo_fitment_queryset()),
        ))
        with self.assertNumQueries(0):
            data = ProductListSerializer(products, many=True, context={"request": APIRequestFactory().get("/")}).data
        self.assertEqual(len(data), 7)


class ProductSeoAdminImportTests(ProductSeoFixture):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser("seo-admin", "seo@example.test", "password")
        self.admin = ProductAdmin(Product, AdminSite())
        self.request = RequestFactory().post("/")
        self.request.user = self.user

    def admin_save(self, product=None, **changes):
        product = product or self.product
        data = {
            "name": product.name, "sku": product.sku, "slug": product.slug,
            "category": product.category_id, "status": product.status,
            "supplier_price": str(product.supplier_price), "price": str(product.price),
            "markup_percent_override": "0", "side": product.side,
            "seo_title": product.seo_title or "",
        }
        data.update(changes)
        form = self.admin.get_form(self.request, product)(data=data, instance=product)
        self.assertTrue(form.is_valid(), form.errors)
        self.admin.save_model(self.request, form.instance, form, True)
        self.product.refresh_from_db()
        return form

    def report(self, name="მომწოდებლის ახალი ხუფი (RH)"):
        return build_crossmotors_report([{
            "code": "000015", "name": name, "oem": "OEM-1", "brand": "Subaru",
            "model": "Forester", "generation": "Forester 15-19", "manufacturer": "TYG",
            "qty": 20, "dealer_price": 120, "currency": "GEL",
        }], product_queryset=Product.objects.all())

    def test_admin_name_edit_automatically_protects_name_for_both_import_paths(self):
        self.admin_save(name="ჩემი სარკის მარჯვენა საფარი")
        self.assertTrue(self.product.preserve_manual_name)
        self.product.markup_percent_override = Decimal("10")
        self.product.save(update_fields=["markup_percent_override"])
        original_urls = (self.product.slug, self.product.public_slug)
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                importer(self.report())
                self.product.refresh_from_db()
                self.assertEqual(self.product.name, "ჩემი სარკის მარჯვენა საფარი")
                self.assertEqual(self.product.supplier_price, Decimal("120"))
                self.assertEqual(self.product.price, Decimal("132"))
                self.assertEqual(self.product.stock_qty, 20)
                self.assertFalse(self.product.seo_title)
                self.assertIn("ჩემი სარკის მარჯვენა საფარი", self.product.effective_seo_title)
                self.assertIn("2015–2019", self.product.effective_seo_title)
                self.assertEqual((self.product.slug, self.product.public_slug), original_urls)

    def test_unedited_names_continue_to_follow_supplier_for_both_paths(self):
        self.admin_save()
        self.assertFalse(self.product.preserve_manual_name)
        for number, importer in enumerate((import_crossmotors_report, import_crossmotors_report_bulk)):
            name = f"განახლებული ხუფი {number} (RH)"
            importer(self.report(name))
            self.product.refresh_from_db()
            self.assertEqual(self.product.name, name)
            self.assertFalse(self.product.preserve_manual_name)
            self.assertIn(f"განახლებული ხუფი {number}", self.product.effective_seo_title)

    def test_manual_seo_override_survives_both_importers_and_returns_to_auto(self):
        self.admin_save(seo_title="ხელით დაწერილი SEO სათაური")
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            importer(self.report())
            self.product.refresh_from_db()
            self.assertEqual(self.product.effective_seo_title, "ხელით დაწერილი SEO სათაური")
        self.admin_save(seo_title="")
        self.assertIn("მომწოდებლის ახალი ხუფი", self.product.effective_seo_title)
        self.assertIn("2015–2019", self.product.effective_seo_title)

    def test_stale_unrelated_admin_save_keeps_latest_name_protection_and_title(self):
        stale = Product.objects.get(pk=self.product.pk)
        Product.objects.filter(pk=self.product.pk).update(
            name="უკვე განახლებული სახელი", preserve_manual_name=True, seo_title="უახლესი SEO",
        )
        self.admin_save(product=stale)
        self.assertEqual(self.product.name, "უკვე განახლებული სახელი")
        self.assertTrue(self.product.preserve_manual_name)
        self.assertEqual(self.product.seo_title, "უახლესი SEO")

    def test_new_supplier_products_start_with_automatic_titles(self):
        report = build_crossmotors_report([{
            "code": "000016", "name": "ფარი (LH)", "oem": "OEM-2", "brand": "Subaru",
            "model": "Forester", "generation": "Forester 15-19", "manufacturer": "TYG",
            "qty": 20, "dealer_price": 120, "currency": "GEL",
        }], product_queryset=Product.objects.all())
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            importer(report)
            product = Product.objects.get(sku="CM-000016")
            self.assertFalse(product.preserve_manual_name)
            self.assertFalse(product.seo_title)
            self.assertEqual(product.effective_seo_title, "Subaru Forester 2015–2019 — ფარი მარცხენა — TYG")


class ProductSeoIdentifierTests(ProductSeoFixture):
    def test_part_number_and_company_sku_are_not_automatically_appended(self):
        self.product.manufacturer_part_number = "91059-SG000"
        self.product.brand = Brand.objects.create(name="TYG", slug="identifier-tyg")
        self.assertEqual(self.product.effective_seo_title, "Subaru Forester 2012–2018 — სარკის ქვედა ხუფი მარჯვენა — TYG")
        self.product.seo_title = "ჩემი სათაური"
        self.assertEqual(self.product.effective_seo_title, "ჩემი სათაური")

    def test_duplicate_public_identity_does_not_append_company_sku(self):
        self.product.status = ProductStatus.PUBLISHED
        self.product.manufacturer_part_number = "91059-SG000"
        self.product.save()
        other = Product.objects.create(
            category=self.category, name=self.product.name, manufacturer_part_number=self.product.manufacturer_part_number,
            side=self.product.side, placement=self.product.placement, price=90, status=ProductStatus.PUBLISHED,
            sku="PRIVATE-SUPPLIER-2", internal_sku="FD-02-0002", slug="second-mirror",
        )
        for brand in (None, Brand.objects.create(name="TYG", slug="identifier-tyg")):
            self.product.brand = other.brand = brand
            self.product.save(update_fields=["brand"])
            other.save(update_fields=["brand"])
            for product in Product.objects.filter(pk__in=[self.product.pk, other.pk]):
                self.assertNotIn(product.display_sku, product.effective_seo_title)
                self.assertNotIn(product.manufacturer_part_number, product.effective_seo_title)
                self.assertNotIn("PRIVATE-SUPPLIER", product.effective_seo_title)
        other.status = ProductStatus.ARCHIVED
        other.save(update_fields=["status"])
        self.assertNotIn(self.product.display_sku, self.product.effective_seo_title)


class CategorySeoLookupTests(TestCase):
    def test_active_empty_category_is_real_but_unknown_and_inactive_are_404(self):
        empty = Category.objects.create(name="ცარიელი კატეგორია", slug="empty-seo")
        inactive = Category.objects.create(name="არააქტიური", slug="inactive-seo", is_active=False)
        client = APIClient()
        response = client.get(reverse("catalog-category-detail", args=[empty.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["product_count"], 0)
        self.assertEqual(response.data["slug"], empty.slug)
        for slug in (inactive.slug, "does-not-exist"):
            self.assertEqual(client.get(reverse("catalog-category-detail", args=[slug])).status_code, 404)
        self.assertEqual(client.get(reverse("catalog-category-list")).data, [])


class LegacySeoTitleMigrationTests(TestCase):
    def test_conversion_is_exact_conservative_idempotent_and_preserves_other_fields(self):
        category = Category.objects.create(name="Legacy", slug="legacy-seo")
        products = []
        for index, overrides in enumerate((
            {}, {"seo_title": "ხუფი Subaru Forester | FlexDrive"},
            {"preserve_manual_fitment_content": True}, {"supplier_source": "manual"},
            {"seo_title": "ხუფი | სხვა ბრენდი"},
        )):
            values = dict(name="ხუფი (RH)", seo_title="ხუფი | FlexDrive", supplier_source="cross_motors")
            values.update(overrides)
            products.append(Product.objects.create(category=category, sku=f"LEGACY-{index}", slug=f"legacy-{index}", price=10, stock_qty=12, **values))
        before = [Product.objects.values().get(pk=p.pk) for p in products]
        conversion = importlib.import_module("catalog.migrations.0029_auto_product_seo_titles").clear_exact_legacy_imported_titles
        self.assertTrue(is_legacy_imported_title(products[0]))
        conversion(apps, SimpleNamespace(connection=connection))
        conversion(apps, SimpleNamespace(connection=connection))
        for index, product in enumerate(products):
            after = Product.objects.values().get(pk=product.pk)
            self.assertEqual(after["seo_title"], "" if index == 0 else before[index]["seo_title"])
            self.assertEqual({k: v for k, v in after.items() if k != "seo_title"}, {k: v for k, v in before[index].items() if k != "seo_title"})
