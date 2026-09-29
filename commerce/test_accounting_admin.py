from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Order, OrderItem, PaymentTransaction


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AccountingAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.superuser = users.create_user(username="accounting-admin", email="admin@example.test", is_staff=True, is_superuser=True)
        cls.staff = users.create_user(username="ordinary-staff", email="staff@example.test", is_staff=True)
        cls.customer = users.create_user(username="customer", email="customer@example.test")
        cls.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="commerce").exclude(codename="view_accounting_report"))
        cls.order = Order.objects.create(order_number="ACC-UI", subtotal=Decimal(35), total=Decimal(45),
                                        delivery_provider="internal", delivery_price=Decimal(10))
        Order.objects.filter(pk=cls.order.pk).update(created_at=datetime(2026, 9, 15, tzinfo=timezone.utc))
        OrderItem.objects.create(order=cls.order, product_name='<script>alert("xss")</script>', sku="PRIVATE-TEST",
                                 internal_sku="FD-01-0999", unit_price=Decimal(35), quantity=1, line_total=Decimal(35),
                                 purchase_unit_gross=Decimal(15), purchase_cost_source="catalog_supplier_price")
        cls.payment = PaymentTransaction.objects.create(order=cls.order, provider="bog", action="sale", status="paid",
                                                        amount=Decimal(45), captured_at=datetime(2026, 9, 16, tzinfo=timezone.utc))

    def setUp(self):
        self.url = reverse("accounting-report")
        self.params = {"start": "2026-09-01", "end": "2026-09-30"}

    def get(self, **kwargs):
        return self.client.get(self.url, {**self.params, **kwargs})

    def test_permissions(self):
        self.assertEqual(self.get().status_code, 302)
        for user, expected in ((self.staff, 403), (self.customer, 302), (self.superuser, 200)):
            self.client.force_login(user)
            self.assertEqual(self.get().status_code, expected)
            self.assertEqual(self.get(export="xlsx").status_code, expected)

    def test_single_table_fixed_vat_and_safe_text(self):
        self.client.force_login(self.superuser)
        response = self.get()
        self.assertEqual(response.context["rows"][0][9], "12.71")
        self.assertEqual(response.context["rows"][0][10], "16.95")
        self.assertEqual(response.context["totals"][14], "45.00")
        self.assertNotContains(response, "id_tax_mode")
        self.assertNotContains(response, "accounting-tabs")
        self.assertContains(response, "&lt;script&gt;")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_unpaid_excluded(self):
        PaymentTransaction.objects.filter(pk=self.payment.pk).update(status="pending", captured_at=None)
        self.client.force_login(self.superuser)
        self.assertEqual(self.get().context["rows"], [])

    def refund(self, amount=45):
        return PaymentTransaction.objects.create(order=self.order, provider="bog", action="refund", status="refunded",
            amount=amount, refunded_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
            provider_reference={"refund_request": {"sale_payment_id": self.payment.pk}})

    def test_return_filter_uses_return_date_and_excludes_returned_sale(self):
        self.refund()
        self.client.force_login(self.superuser)
        self.assertEqual(self.get().context["rows"], [])
        self.assertEqual(self.get(status="refunded").context["rows"], [])
        response = self.get(start="2026-10-01", end="2026-10-31", status="refunded")
        self.assertEqual(response.context["totals"][14], "45.00")
        self.assertEqual(response.context["totals"][10], "16.95")

    def test_partial_refund_does_not_invent_full_product_reversal(self):
        self.refund(amount=5)
        self.client.force_login(self.superuser)
        response = self.get(start="2026-10-01", end="2026-10-31", status="refunded")
        self.assertEqual(response.context["totals"][14], "5.00")
        self.assertEqual(response.context["totals"][10], "—")

    def test_order_delivery_once_and_totals_across_pages(self):
        for i in range(51):
            OrderItem.objects.create(order=self.order, product_name=f"Part {i}", sku=f"P{i}", unit_price=0,
                line_total=0, quantity=1, purchase_unit_gross=0)
        self.client.force_login(self.superuser)
        response = self.get()
        self.assertEqual(len(response.context["rows"]), 52)
        self.assertEqual(len(response.context["groups"]), 1)
        self.assertEqual(response.context["page"].paginator.num_pages, 1)
        self.assertEqual(response.context["totals"][4], 52)
        self.assertEqual(response.context["totals"][11], "10.00")
        self.assertEqual(response.context["totals"][14], "45.00")
        self.assertEqual(self.get(page=2).context["totals"], response.context["totals"])
        self.assertEqual(response.context["groups"][0]["delivery"][0][1], "10.00")

    def test_invalid_date_status_and_post(self):
        self.client.force_login(self.superuser)
        for params in ({"start": "2026-10-01"}, {"end": "bad"}, {"status": "pending"}):
            with patch("commerce.accounting_admin.build_ledger") as build:
                self.assertFalse(self.get(**params).context["form"].is_valid())
                build.assert_not_called()
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_admin_home_link(self):
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(reverse("admin:index")), self.url)
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(reverse("admin:index")), self.url)

    def test_month_range_without_markup_column(self):
        self.client.force_login(self.superuser)
        response = self.get(period_mode="months", start_month="2026-09", end_month="2026-09")
        self.assertNotIn("ფასნამატი %", response.context["headers"])
        self.assertEqual(response.context["totals"][15], "—")
        self.assertEqual(self.get(period_mode="months", start_month="2026-08", end_month="2026-08").context["rows"], [])

    def test_sku_search_returns_only_matched_products(self):
        OrderItem.objects.create(order=self.order, product_name="Unmatched", internal_sku="FD-OTHER", sku="PRIVATE-OTHER",
                                 unit_price=10, quantity=1, line_total=10, purchase_unit_gross=5)
        Order.objects.filter(pk=self.order.pk).update(subtotal=45, total=55)
        PaymentTransaction.objects.filter(pk=self.payment.pk).update(amount=55)
        self.client.force_login(self.superuser)
        response = self.get(sku=" fd-01-0999 ")
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertEqual(response.context["totals"][8], "35.00")
        self.assertEqual(response.context["totals"][14], "—")
        self.assertEqual(response.context["rows"][0][11], "—")
        self.assertEqual(self.get(sku="PRIVATE-TEST").context["rows"], response.context["rows"])
        self.assertEqual(self.get(sku="does-not-exist").context["rows"], [])

    def test_product_name_search_partial_and_export(self):
        OrderItem.objects.filter(order=self.order).update(product_name="წინა ფარი Headlamp")
        self.client.force_login(self.superuser)
        for search in ("ფარი", "headLAMP"):
            response = self.get(sku=search)
            self.assertEqual(len(response.context["rows"]), 1)
            self.assertEqual(response.context["rows"][0][3], "FD-01-0999")
            self.assertEqual(response.context["totals"][8], "35.00")
            from io import BytesIO
            from zipfile import ZipFile
            with ZipFile(BytesIO(self.get(sku=search, export="xlsx").content)) as archive:
                self.assertIn(b"FD-01-0999", archive.read("xl/worksheets/sheet1.xml"))

    def test_all_includes_sale_and_signed_refund_once(self):
        self.refund()
        self.client.force_login(self.superuser)
        response = self.get(status="all", end="2026-10-31")
        self.assertEqual(len(response.context["rows"]), 2)
        self.assertEqual(len(response.context["groups"]), 2)
        self.assertNotEqual(response.context["groups"][0]["event_id"], response.context["groups"][1]["event_id"])
        self.assertEqual(response.context["rows"][0][15], "გადახდილი")
        self.assertEqual(response.context["rows"][1][15], "დაბრუნებული")
        self.assertEqual(response.context["rows"][1][10], "-16.95")
        self.assertEqual(response.context["totals"][14], "0.00")
        self.assertEqual(response.context["totals"][10], "0.00")
        self.assertEqual(self.get(status="all").context["totals"][14], "45.00")
        self.assertEqual(self.get(status="all", start="2026-10-01", end="2026-10-31").context["totals"][14], "-45.00")

    def test_order_blocks_keep_products_together_on_page_boundary(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("accounting_demo", stdout=StringIO())
        self.client.force_login(self.superuser)
        first = self.get(start="2026-04-01", end="2026-09-30")
        second = self.get(start="2026-04-01", end="2026-09-30", page=2)
        self.assertEqual(len(first.context["groups"]), 20)
        self.assertEqual(len(second.context["groups"]), 11)
        first_ids = {g["event_id"] for g in first.context["groups"]}
        self.assertFalse(first_ids.intersection(g["event_id"] for g in second.context["groups"]))
        self.assertEqual(first.context["totals"], second.context["totals"])
        for group in first.context["groups"] + second.context["groups"]:
            self.assertEqual(len(group["rows"]), group["line_count"])
            self.assertEqual(len(group["delivery"]), 4)
        self.assertContains(first, 'class="accounting-order"', count=20)
