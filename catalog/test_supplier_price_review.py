from decimal import Decimal
from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from commerce.models import Cart
from commerce.services import add_product_to_cart, get_product_availability_issue

from .crossmotors_import import (
    build_crossmotors_report, import_crossmotors_report, import_crossmotors_report_bulk,
)
from .admin import ProductAdmin
from .models import Category, Product, ProductStatus, SupplierPriceReview
from .pricing_review import resolve_supplier_price_review
from .test_supplier_sync import feed_item


class SupplierPriceReviewTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Parts", slug="review-parts", is_active=True)
        self.product = Product.objects.create(
            category=category, name="Lamp", slug="review-lamp", sku="CM-000015",
            internal_sku="FD-01-9001", supplier_price=Decimal("100.00"),
            price=Decimal("150.00"), stock_qty=12, status=ProductStatus.PUBLISHED,
        )
        self.cart = Cart.objects.create()

    def sync(self, cost, importer=import_crossmotors_report):
        item = feed_item()
        item["dealer_price"] = cost
        importer(build_crossmotors_report([item]))
        self.product.refresh_from_db()

    def test_cost_drop_keeps_sale_and_adds_review_for_each_importer(self):
        for importer in (import_crossmotors_report, import_crossmotors_report_bulk):
            with self.subTest(importer=importer.__name__):
                self.sync(80, importer)
                self.assertEqual(self.product.price, Decimal("150.00"))
                self.assertTrue(self.product.supplier_price_review_pending)
                self.assertTrue(self.product.price_available)
                self.assertEqual(get_product_availability_issue(self.product), "available")
                review = SupplierPriceReview.objects.get(product=self.product)
                self.assertEqual(review.previous_supplier_price, Decimal("100.00"))
                self.assertEqual(review.latest_supplier_price, Decimal("80.00"))
                self.assertEqual(add_product_to_cart(self.cart, self.product, 1).unit_price_snapshot, Decimal("150.00"))
                self.product.supplier_price = Decimal("100.00")
                self.product.save(update_fields=["supplier_price"])
                self.product.refresh_from_db()
                self.assertTrue(resolve_supplier_price_review(self.product.pk))
                self.product.refresh_from_db()

    def test_cost_rise_blocks_purchase_until_manual_price_change(self):
        self.sync(150)
        self.assertEqual(self.product.price, Decimal("150.00"))
        self.assertFalse(self.product.price_available)
        self.assertFalse(self.product.purchasable)
        self.assertEqual(get_product_availability_issue(self.product), "unavailable")
        response = self.client.get(reverse("catalog-product-detail", args=[self.product.public_slug]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["price_available"])
        self.assertFalse(response.data["purchasable"])
        with self.assertRaises(ValidationError):
            add_product_to_cart(self.cart, self.product, 1)
        self.assertFalse(resolve_supplier_price_review(self.product.pk))
        self.product.price = Decimal("180.00")
        self.product.save(update_fields=["price"])
        self.assertTrue(resolve_supplier_price_review(self.product.pk))
        self.product.refresh_from_db()
        self.assertTrue(self.product.price_available)
        self.assertFalse(SupplierPriceReview.objects.filter(product=self.product).exists())

    def test_repeated_changes_update_one_pending_row_and_no_change_does_nothing(self):
        self.sync(80)
        first = SupplierPriceReview.objects.get(product=self.product)
        self.sync(90, import_crossmotors_report_bulk)
        latest = SupplierPriceReview.objects.get(product=self.product)
        self.assertEqual(latest.pk, first.pk)
        self.assertEqual(latest.previous_supplier_price, Decimal("100.00"))
        self.assertEqual(latest.latest_supplier_price, Decimal("90.00"))
        self.sync(90)
        self.assertEqual(SupplierPriceReview.objects.filter(product=self.product).count(), 1)

    def test_missing_supplier_cost_stays_unavailable_until_reviewable(self):
        self.sync(None)
        self.assertEqual(self.product.price, Decimal("150.00"))
        self.assertIsNone(self.product.supplier_price)
        self.assertFalse(self.product.price_available)
        self.assertFalse(resolve_supplier_price_review(self.product.pk))

    @override_settings(STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    })
    def test_admin_queue_can_mark_safe_product_reviewed(self):
        self.sync(80)
        user = get_user_model().objects.create_superuser("review-admin", "review@example.com", "password")
        self.client.force_login(user)
        url = reverse("admin:catalog_supplierpricereview_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Front lamp (RH)")
        response = self.client.post(url, {
            "action": "mark_reviewed", "_selected_action": [str(SupplierPriceReview.objects.get().pk)],
            "index": "0", "select_across": "0",
        })
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.supplier_price_review_pending)
        self.assertFalse(SupplierPriceReview.objects.exists())

    def test_admin_price_edit_closes_review_and_restores_sale(self):
        self.sync(150)
        self.assertFalse(self.product.price_available)
        self.product.price = Decimal("180.00")
        request = RequestFactory().post("/")
        request.user = get_user_model().objects.create_superuser("price-editor", "editor@example.com", "password")
        ProductAdmin(Product, AdminSite()).save_model(
            request, self.product, SimpleNamespace(changed_data=["price"]), True,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("180.00"))
        self.assertTrue(self.product.price_available)
        self.assertFalse(self.product.supplier_price_review_pending)
        self.assertFalse(SupplierPriceReview.objects.exists())
