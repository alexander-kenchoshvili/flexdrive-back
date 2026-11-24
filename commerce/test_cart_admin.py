import uuid
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from .models import Cart, CartItem


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CartAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="cart-staff", email="cart-staff@example.com", is_staff=True,
        )
        cls.staff.user_permissions.add(Permission.objects.get(codename="view_cart"))
        cls.buyer = get_user_model().objects.create_user(
            username="cart-buyer", email="cart-buyer@example.com",
        )
        category = Category.objects.create(name="Cart admin", slug="cart-admin")
        cls.products = [Product.objects.create(
            category=category, name=f'Part {index} <script>alert("x")</script>',
            slug=f"cart-admin-{index}", sku=f"PRIVATE-SUPPLIER-{index}",
            internal_sku=f"FD-99-{index:04}", price=Decimal("10.00"),
        ) for index in range(7)]
        cls.empty = Cart.objects.create(guest_token=uuid.uuid4())
        cls.guest = Cart.objects.create(guest_token=uuid.uuid4())
        cls.owned = Cart.objects.create(user=cls.buyer)
        cls.inactive = Cart.objects.create(guest_token=uuid.uuid4(), is_active=False)
        for cart in (cls.guest, cls.owned, cls.inactive):
            for index, product in enumerate(cls.products):
                CartItem.objects.create(cart=cart, product=product, quantity=index + 1)

    def setUp(self):
        self.client.force_login(self.staff)
        self.url = reverse("admin:commerce_cart_changelist")
        self.model_admin = admin.site._registry[Cart]

    def test_contents_filters_and_active_filter_keep_counts_exact(self):
        for params, expected in (
            ({}, {self.empty.pk, self.guest.pk, self.owned.pk, self.inactive.pk}),
            ({"contents": "empty"}, {self.empty.pk}),
            ({"contents": "nonempty"}, {self.guest.pk, self.owned.pk, self.inactive.pk}),
            ({"contents": "nonempty", "is_active__exact": "1"}, {self.guest.pk, self.owned.pk}),
        ):
            with self.subTest(params=params):
                page = self.client.get(self.url, params)
                self.assertEqual(page.status_code, 200)
                rows = list(page.context["cl"].result_list)
                self.assertEqual({row.pk for row in rows}, expected)
                for row in rows:
                    self.assertEqual(row.admin_item_count, 0 if row.pk == self.empty.pk else 7)
                    self.assertEqual(row.admin_total_quantity, 0 if row.pk == self.empty.pk else 28)

    def test_preview_escapes_names_shows_public_code_quantity_and_more_link(self):
        page = self.client.get(self.url, {"contents": "nonempty"})
        self.assertContains(page, "FD-99-0000")
        self.assertContains(page, "&lt;script&gt;")
        self.assertNotContains(page, '<script>alert("x")</script>')
        self.assertNotContains(page, "PRIVATE-SUPPLIER-")
        self.assertContains(page, "× 5")
        self.assertContains(page, "კიდევ 2 პროდუქტი")
        self.assertContains(page, reverse("admin:commerce_cart_change", args=[self.guest.pk]))
        self.assertContains(page, reverse("admin:catalog_product_change", args=[self.products[0].pk]))
        self.assertContains(page, "სტუმარი — ვინაობა უცნობია")
        self.assertContains(page, str(self.buyer))

    def test_empty_preview_and_existing_user_search(self):
        page = self.client.get(self.url, {"contents": "empty"})
        self.assertContains(page, "ცარიელია")
        page = self.client.get(self.url, {"contents": "nonempty", "q": self.buyer.email})
        self.assertEqual([row.pk for row in page.context["cl"].result_list], [self.owned.pk])

    def test_preview_is_bounded_per_cart_without_per_row_queries(self):
        request = RequestFactory().get(self.url)
        request.user = self.staff
        with self.assertNumQueries(2):
            rows = list(self.model_admin.get_queryset(request))
        with self.assertNumQueries(0):
            for row in rows:
                self.model_admin.cart_owner(row)
                self.model_admin.product_preview(row)
                self.model_admin.product_count(row)
                self.model_admin.total_quantity(row)
                self.assertEqual(len(row.admin_preview_items), 0 if row.pk == self.empty.pk else 5)

    def test_existing_permissions_still_required(self):
        self.staff.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)
