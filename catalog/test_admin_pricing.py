from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .admin import ProductAdmin
from .crossmotors_import import _calculate_customer_price
from .models import Category, Product


class ProductAdminPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Pricing", slug="pricing-tests", markup_percent=10)
        cls.user = get_user_model().objects.create_superuser("pricing-admin", "pricing@example.com", "password")

    def setUp(self):
        self.product = Product.objects.create(
            category=self.category, name="Pricing part", sku="pricing-part", slug="pricing-part",
            supplier_price=100, price=100, stock_qty=10,
        )
        self.admin = ProductAdmin(Product, AdminSite())
        self.request = RequestFactory().post("/")
        self.request.user = self.user

    def form(self, **changes):
        data = dict(name=self.product.name, sku=self.product.sku, slug=self.product.slug,
                    category=self.category.pk, status="draft", stock_qty=10,
                    supplier_price="100.00", price="100.00", markup_percent_override="0")
        data.update(changes)
        return self.admin.get_form(self.request, self.product)(data=data, instance=self.product)

    def save(self, **changes):
        form = self.form(**changes)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.product.refresh_from_db()
        return self.product

    def test_amount_sets_markup_and_supplier_refresh_preserves_percentage(self):
        product = self.save(pricing_input="price", price="120.00")
        self.assertEqual(product.markup_percent_override, Decimal("20"))
        self.assertEqual(product.price, Decimal("120"))
        product.supplier_price = Decimal("110")
        product.save(update_fields=["supplier_price"])
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal("132"))
        self.assertEqual(_calculate_customer_price(product, self.category), Decimal("132"))

    def test_amount_round_trips_at_cent_precision(self):
        for cost, price in [("73", "100"), ("3999", "4999.99"), ("99999998", "99999999.99")]:
            with self.subTest(cost=cost):
                product = self.save(pricing_input="price", supplier_price=cost, price=price)
                self.assertEqual(product.price, Decimal(price))
                product.save()
                product.refresh_from_db()
                self.assertEqual(product.price, Decimal(price))
                self.assertEqual(_calculate_customer_price(product, self.category), Decimal(price))

    def test_percentage_is_authoritative_and_server_recalculates(self):
        product = self.save(pricing_input="markup", markup_percent_override="25", price="999")
        self.assertEqual(product.price, Decimal("125"))

    def test_clearing_markup_means_zero(self):
        self.save(pricing_input="price", price="120")
        product = self.save(pricing_input="markup", markup_percent_override="", price="120")
        self.assertEqual(product.markup_percent_override, 0)
        self.assertEqual(product.price, Decimal("100"))

    def test_newly_selected_category_does_not_change_price(self):
        other = Category.objects.create(name="Other", slug="pricing-other", markup_percent=35)
        product = self.save(pricing_input="markup", category=other.pk)
        self.assertEqual(product.price, Decimal("100"))

    def test_no_javascript_price_edit(self):
        self.assertEqual(self.save(price="120").markup_percent_override, Decimal("20"))

    def test_unchanged_form_preserves_zero_markup(self):
        self.assertEqual(self.save().markup_percent_override, 0)

    def test_no_supplier_price_keeps_manual_price(self):
        product = self.save(pricing_input="price", supplier_price="", price="120")
        self.assertEqual(product.price, Decimal("120"))
        self.assertEqual(product.markup_percent_override, 0)

    def test_zero_supplier_and_zero_price_are_valid(self):
        self.assertEqual(self.save(pricing_input="price", supplier_price="0", price="0").price, 0)

    def test_invalid_amounts_are_rejected(self):
        for changes in [dict(supplier_price="0", price="120"), dict(price="99.99"),
                        dict(price="1100.01"), dict(price=""), dict(price="-1")]:
            with self.subTest(changes=changes):
                form = self.form(pricing_input="price", **changes)
                self.assertFalse(form.is_valid())
                self.assertIn("price", form.errors)

    def test_old_price_is_validated_against_entered_price(self):
        form = self.form(pricing_input="price", price="120", old_price="119")
        self.assertFalse(form.is_valid())
        self.assertIn("old_price", form.errors)

    def test_percentage_mode_can_calculate_missing_price(self):
        self.assertEqual(self.save(pricing_input="markup", price="", markup_percent_override="20").price, 120)

    @override_settings(STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    })
    def test_admin_renders_editable_amount_and_calculation_metadata(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:catalog_product_change", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_price"')
        self.assertContains(response, 'id="id_pricing_input"')
        self.assertNotContains(response, "category_markup_readonly")
        self.assertNotIn("price", self.admin.get_readonly_fields(self.request, self.product))

    def test_both_supplier_importers_ignore_category_and_preserve_product_markup(self):
        from .crossmotors_import import build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk
        from .test_supplier_sync import feed_item
        self.product.sku = "CM-000015"
        self.product.save()
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            for markup, expected in [(None, Decimal("110")), (Decimal("20"), Decimal("132"))]:
                with self.subTest(importer=importer.__name__, markup=markup):
                    self.product.markup_percent_override = markup
                    self.product.save()
                    item = feed_item()
                    item["dealer_price"] = 110
                    importer(build_crossmotors_report([item]))
                    self.product.refresh_from_db()
                    self.assertEqual(self.product.price, expected)
                    self.assertEqual(self.product.markup_percent_override, markup)

    def test_public_price_is_numeric_and_later_admin_edit_updates_it(self):
        self.product.internal_sku = "FD-01-9000"
        self.product.status = "published"
        self.product.save()
        url = reverse("catalog-product-detail", args=[self.product.public_slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["price"]), Decimal("100"))
        self.assertNotIn("supplier_price", response.data)
        self.save(pricing_input="price", price="120", status="published")
        response = self.client.get(url)
        self.assertEqual(Decimal(response.data["price"]), Decimal("120"))

    def test_category_admin_has_no_pricing_field(self):
        from .admin import CategoryAdmin
        category_admin = CategoryAdmin(Category, AdminSite())
        self.assertNotIn("markup_percent", category_admin.get_form(self.request).base_fields)
        self.assertNotIn("markup_percent", category_admin.list_display)

    def test_cutover_only_resets_current_product_pricing(self):
        from django.apps import apps
        from django.db import connection
        from importlib import import_module
        from types import SimpleNamespace
        self.product.markup_percent_override = 25
        self.product.save()
        before = Product.objects.values().get(pk=self.product.pk)
        manual = Product.objects.create(name="Manual", sku="manual-pricing", slug="manual-pricing",
                                        category=self.category, price=17, markup_percent_override=10)
        cutover = import_module("catalog.migrations.0026_individual_product_pricing")
        cutover.set_initial_zero_markup(apps, SimpleNamespace(connection=connection))
        after = Product.objects.values().get(pk=self.product.pk)
        self.assertEqual(after.pop("price"), Decimal("100"))
        self.assertEqual(after.pop("markup_percent_override"), 0)
        before.pop("price")
        before.pop("markup_percent_override")
        self.assertEqual(before, after)
        manual.refresh_from_db()
        self.assertEqual(manual.price, 17)
        self.assertEqual(manual.markup_percent_override, 0)

    def test_rounded_display_does_not_round_stored_markup_on_ordinary_save(self):
        product = self.save(pricing_input="price", supplier_price="3999", price="4999.99")
        exact = product.markup_percent_override
        form = self.admin.get_form(self.request, product)(instance=product)
        rendered = str(form["markup_percent_override"])
        self.assertIn('value="25.03"', rendered)
        self.assertIn('data-exact-markup="25.0310077519"', rendered)
        product = self.save(supplier_price="3999", price="4999.99", markup_percent_override="25.03")
        self.assertEqual(product.markup_percent_override, exact)
        self.assertEqual(product.price, Decimal("4999.99"))

    def test_supplier_edit_retains_precision_despite_rounded_display(self):
        self.save(pricing_input="price", supplier_price="3999", price="4999.99")
        product = self.save(pricing_input="supplier", supplier_price="4000", price="5001.24", markup_percent_override="25.03")
        self.assertEqual(product.markup_percent_override, Decimal("25.0310077519"))
        self.assertEqual(product.price, Decimal("5001.24"))

    def test_explicit_edit_to_displayed_rounded_percentage_is_respected(self):
        self.save(pricing_input="price", supplier_price="3999", price="4999.99")
        product = self.save(pricing_input="markup", supplier_price="4000", price="5001.24", markup_percent_override="25.03")
        self.assertEqual(product.markup_percent_override, Decimal("25.03"))
        self.assertEqual(product.price, Decimal("5001.20"))

    def test_amount_entry_with_rounded_percentage_still_stores_precise_rate(self):
        product = self.save(pricing_input="price", supplier_price="3999", price="4999.99", markup_percent_override="25.03")
        self.assertEqual(product.markup_percent_override, Decimal("25.0310077519"))
        self.assertEqual(product.price, Decimal("4999.99"))
