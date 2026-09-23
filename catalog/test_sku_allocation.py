from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction, close_old_connections
from django.test import TestCase, TransactionTestCase, RequestFactory, skipUnlessDBFeature
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.admin import ProductAdmin
from catalog.internal_skus import assign_admin_sku, import_sku_pairs
from catalog.models import Category, Product, SkuSequence


class SkuAllocationTests(TestCase):
    def setUp(self):
        self.sequence = SkuSequence.objects.get(pk="01")
        self.category = Category.objects.filter(sku_sequence=self.sequence).first()
        if self.category is None:
            self.category = Category.objects.create(name="Lights", slug="test-lights", sku_sequence=self.sequence)
        self.child = Category.objects.create(name="Child", slug="test-lights-child", parent=self.category)
        self.unmapped = Category.objects.create(name="New", slug="test-unmapped")
        self.admin = ProductAdmin(Product, AdminSite())
        self.request = RequestFactory().post("/")
        self.request.user = get_user_model().objects.create_superuser("sku-admin", "sku-admin@example.com", "password")

    def product(self, suffix="1", **kwargs):
        return Product.objects.create(
            name="Lamp", sku=f"CM-{suffix}", slug=f"lamp-cm-{suffix}", price=20,
            category=kwargs.pop("category", self.category), stock_qty=10, **kwargs,
        )

    def save_admin(self, product):
        self.admin.save_model(self.request, product, SimpleNamespace(changed_data=["category"]), True)
        product.refresh_from_db()

    def test_plain_creation_and_supplier_like_save_never_assign_code(self):
        product = self.product()
        product.price = 30
        product.save()
        self.assertIsNone(product.internal_sku)

    def test_admin_save_starts_after_maximum_and_child_uses_root(self):
        self.product("old", internal_sku="FD-01-0005")
        product = self.product(category=self.child)
        self.save_admin(product)
        self.assertEqual(product.internal_sku, "FD-01-0006")
        second = self.product("2")
        self.save_admin(second)
        self.assertEqual(second.internal_sku, "FD-01-0007")

    def test_deletion_never_reuses_number(self):
        product = self.product()
        self.save_admin(product)
        old = product.internal_sku
        product.delete()
        next_product = self.product("next")
        self.save_admin(next_product)
        self.assertNotEqual(next_product.internal_sku, old)
        self.assertEqual(int(next_product.internal_sku.rsplit("-", 1)[1]), int(old.rsplit("-", 1)[1]) + 1)

    def test_groups_have_independent_counters(self):
        other_sequence = SkuSequence.objects.get(pk="02")
        other_category = Category.objects.filter(sku_sequence=other_sequence).first()
        if other_category is None:
            other_category = Category.objects.create(name="Mirrors", slug="sku-test-mirrors", sku_sequence=other_sequence)
        first, second = self.product("1"), self.product("2", category=other_category)
        self.save_admin(first)
        self.save_admin(second)
        self.assertEqual(first.internal_sku, "FD-01-0001")
        self.assertEqual(second.internal_sku, "FD-02-0001")

    def test_category_change_and_stale_save_preserve_assigned_code(self):
        product = self.product()
        stale = Product.objects.get(pk=product.pk)
        self.save_admin(product)
        code = product.internal_sku
        stale.category = self.unmapped
        stale.save()
        stale.refresh_from_db()
        self.assertEqual(stale.internal_sku, code)
        self.save_admin(stale)
        self.assertEqual(stale.internal_sku, code)

    def test_unmapped_category_stays_draft_and_publication_is_blocked(self):
        product = self.product(category=self.unmapped)
        self.save_admin(product)
        self.assertIsNone(product.internal_sku)
        product.status = "published"
        with self.assertRaises(ValidationError):
            product.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            product.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=product.pk).update(status="published")

    def test_admin_publish_selection_is_all_or_nothing(self):
        first, second = self.product("1"), self.product("2")
        self.save_admin(first)
        with patch.object(self.admin, "message_user") as message:
            self.admin.action_publish(self.request, Product.objects.filter(pk__in=[first.pk, second.pk]))
            message.assert_called_once()
        first.refresh_from_db()
        self.assertEqual(first.status, "draft")
        self.save_admin(second)
        self.admin.action_publish(self.request, Product.objects.filter(pk__in=[first.pk, second.pk]))
        self.assertEqual(Product.objects.filter(pk__in=[first.pk, second.pk], status="published").count(), 2)

    def test_actual_admin_form_can_assign_and_publish_in_one_save(self):
        product = self.product()
        form_class = self.admin.get_form(self.request, product)
        form = form_class(data={"name": product.name, "slug": product.slug, "sku": product.sku,
            "category": self.category.pk, "price": "20.00", "stock_qty": 10,
            "status": "published", "supplier_source": "manual"}, instance=product)
        self.assertTrue(form.is_valid(), form.errors)
        self.admin.save_model(self.request, form.save(commit=False), form, True)
        product.refresh_from_db()
        self.assertTrue(product.internal_sku.startswith("FD-01-"))
        self.assertEqual(product.status, "published")
        self.assertIn("internal_sku", self.admin.get_readonly_fields(self.request, product))

    def test_rollback_does_not_leave_code_or_counter_and_retry_is_safe(self):
        product = self.product()
        initial = SkuSequence.objects.get(pk="01").last_number
        try:
            with transaction.atomic():
                assign_admin_sku(product)
                raise ValueError("Failed admin save")
        except ValueError:
            pass
        self.assertIsNone(Product.objects.get(pk=product.pk).internal_sku)
        self.assertEqual(SkuSequence.objects.get(pk="01").last_number, initial)
        self.save_admin(product)
        self.assertEqual(int(product.internal_sku.rsplit("-", 1)[1]), initial + 1)

    def test_import_advances_counter_and_deleting_imported_code_cannot_reuse_it(self):
        product = self.product()
        import_sku_pairs({product.sku: "FD-01-0500"}, commit=True)
        product.delete()
        next_product = self.product("next")
        self.save_admin(next_product)
        self.assertEqual(next_product.internal_sku, "FD-01-0501")

    def test_new_and_old_urls_resolve_same_product_and_return_new_canonical(self):
        product = self.product()
        self.save_admin(product)
        product.status = "published"
        product.save()
        self.assertNotIn("cm-", product.public_slug)
        client = APIClient()
        for slug in (product.slug, product.public_slug):
            response = client.get(reverse("catalog-product-detail", args=[slug]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["id"], product.pk)
            self.assertEqual(response.data["slug"], product.public_slug)
            self.assertEqual(response.data["seo"]["canonical"], f"/catalog/{product.public_slug}")
            self.assertEqual(response.data["sku"], product.internal_sku)
        wrong = client.get(reverse("catalog-product-detail", args=["wrong-" + product.internal_sku.lower()]))
        self.assertEqual(wrong.status_code, 404)
        sitemap = client.get(reverse("sitemap-entries"))
        self.assertEqual(sitemap.status_code, 200)
        self.assertIn(f"/catalog/{product.public_slug}", str(sitemap.data))
        self.assertNotIn(f"/catalog/{product.slug}", str(sitemap.data))


class ConcurrentSkuAllocationTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_concurrent_allocations_in_one_group_get_distinct_codes(self):
        sequence, _ = SkuSequence.objects.get_or_create(code="01")
        category = Category.objects.filter(sku_sequence=sequence).first()
        if category is None:
            category = Category.objects.create(name="Concurrent lights", slug="concurrent-lights", sku_sequence=sequence)
        products = [Product.objects.create(name="Lamp", sku=f"CM-THREAD-{n}", slug=f"thread-{n}", category=category, price=20) for n in range(2)]
        barrier = Barrier(2)

        def allocate(pk):
            close_old_connections()
            try:
                product = Product.objects.get(pk=pk)
                barrier.wait(timeout=10)
                return assign_admin_sku(product)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            codes = list(executor.map(allocate, [p.pk for p in products]))
        self.assertEqual(len(set(codes)), 2)
        self.assertEqual(set(Product.objects.filter(pk__in=[p.pk for p in products]).values_list("internal_sku", flat=True)), set(codes))
