from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests.exceptions import Timeout
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductStatus
from commerce.models import Cart, CartItem, Order, PaymentTransaction
from .audience import audience_requests, build_audience_report
from .carts import build_cart_report
from .models import CartAddition
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE, report, response

PERIOD = ReportPeriod(date(2026, 11, 1), date(2026, 11, 25))


@override_settings(BUSINESS_GA4_CREDENTIALS_FILE="reader.json", BUSINESS_GA4_CREDENTIALS_JSON="", CACHES=LOCAL_CACHE)
class AudienceContractTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("business.audience._credentials", return_value=object())
    @patch("business.audience.AuthorizedSession")
    def test_direct_new_and_filtered_returning_counts_and_first_source_are_separate(self, transport, credentials):
        definitions = audience_requests(PERIOD)
        values = [[(3,)], [("20261125", 3)], [(2,)], [("20261125", 2)], [("fb / paid", 2), ("google / organic", 1)]]
        session = transport.return_value.__enter__.return_value
        session.post.return_value = response({"reports": [report(spec, rows) for spec, rows in zip(definitions, values)]})
        result = build_audience_report(PERIOD)
        self.assertEqual((result["new_users"], result["returning_users"]), (3, 2))
        self.assertEqual(result["daily"][-1], {"date": "2026-11-25", "new_users": 3, "returning_users": 2})
        self.assertEqual(result["first_sources"][0], {"source": "fb / paid", "new_users": 2})
        self.assertEqual(result["timezone"], "Asia/Tbilisi")
        for spec in definitions:
            self.assertIn("flexdrive.ge", str(spec["dimensionFilter"]))
        self.assertIn("newVsReturning", str(definitions[2]))
        self.assertIn("returning", str(definitions[3]))
        self.assertEqual(build_audience_report(PERIOD), result)
        self.assertEqual(session.post.call_count, 1)

    @patch("business.audience._credentials", return_value=object())
    @patch("business.audience.AuthorizedSession")
    def test_failed_audience_is_unavailable_without_fake_zero_or_provider_details(self, transport, credentials):
        transport.return_value.__enter__.return_value.post.side_effect = Timeout("PRIVATE")
        result = build_audience_report(PERIOD)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("new_users", result)
        self.assertNotIn("PRIVATE", str(result))


class CartBusinessTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Panel test", slug="panel-test")
        self.product = Product.objects.create(category=self.category, name="Panel part", slug="panel-part", sku="SUPPLIER-PRIVATE",
                                              internal_sku="FD-99-9876", price=Decimal("10.00"), stock_qty=30,
                                              status=ProductStatus.PUBLISHED)
        self.cart = Cart.objects.create(guest_token=uuid.uuid4())
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        self.client = APIClient()

    def test_current_nonempty_snapshot_does_not_expose_guest_or_supplier_identifiers(self):
        Cart.objects.create(guest_token=uuid.uuid4())
        with self.assertNumQueries(3):
            result = build_cart_report(PERIOD, {"q": "FD-99-9876"})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["units"], 2)
        self.assertEqual(result["rows"][0]["items"][0]["sku"], self.product.internal_sku)
        self.assertNotIn(str(self.cart.guest_token), str(result))
        self.assertNotIn(self.product.sku, str(result))

    def test_addition_totals_distinguish_actions_units_and_carts(self):
        for index, qty in enumerate((2, 3)):
            CartAddition.objects.create(cart=self.cart, product=self.product, source_item_id=self.item.pk,
                                        event_key=str(index), cart_key="same-private-context", name=self.product.name,
                                        sku=self.product.internal_sku, quantity=qty, unit_price=self.product.price)
        result = build_cart_report(PERIOD, {"view": "products"})
        self.assertEqual(result["totals"], {"additions": 2, "units": 5, "carts": 1})
        self.assertEqual(result["rows"][0]["carts"], 1)
        self.assertIsNotNone(result["first_recorded_at"])
        self.assertNotIn("same-private-context", str(result))

    def test_later_purchase_requires_saved_cart_item_price_and_time_match(self):
        event = CartAddition.objects.create(cart=self.cart, product=self.product, source_item_id=self.item.pk,
                                           event_key="matched", cart_key="private", name=self.product.name,
                                           sku=self.product.internal_sku, quantity=1, unit_price=self.product.price)
        order = Order.objects.create(order_number="PANEL-PAID", subtotal=10, total=10, payment_status="paid")
        payment = PaymentTransaction.objects.create(order=order, provider="bog", action="sale", status="paid", amount=10,
            captured_at=event.created_at + timedelta(minutes=2), checkout_snapshot={"source": "cart",
                "source_reference": {"cart_id": self.cart.pk}, "buyer": {"phone": "PRIVATE"},
                "items": [{"source_item_id": self.item.pk, "product_id": self.product.pk, "quantity": 1, "unit_price": "10.00"}]})
        PaymentTransaction.objects.filter(pk=payment.pk).update(created_at=event.created_at + timedelta(minutes=1))
        result = build_cart_report(PERIOD, {"view": "additions"})
        self.assertEqual(result["rows"][0]["later_order"]["order_number"], "PANEL-PAID")
        self.assertNotIn("PRIVATE", str(result))
        payment.checkout_snapshot["items"][0]["source_item_id"] += 1
        PaymentTransaction.objects.filter(pk=payment.pk).update(checkout_snapshot=payment.checkout_snapshot)
        self.assertIsNone(build_cart_report(PERIOD, {"view": "additions"})["rows"][0]["later_order"])

    def add(self, **overrides):
        payload = {"product_id": self.product.pk, "quantity": 1, "analytics_consent": True,
                   "analytics_event_id": str(uuid.uuid4()), **overrides}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("commerce-cart-item-list"), payload, format="json", HTTP_ORIGIN="https://flexdrive.ge")

    def test_confirmed_addition_only_and_replayed_observation_deduplicates(self):
        event_id = str(uuid.uuid4())
        self.assertEqual(self.add(analytics_event_id=event_id).status_code, 200)
        self.assertEqual(self.add(analytics_event_id=event_id).status_code, 200)
        self.assertEqual(CartAddition.objects.count(), 1)
        self.assertEqual(self.add(quantity=1000).status_code, 400)
        self.assertEqual(self.add(analytics_consent=False).status_code, 200)
        self.assertEqual(CartAddition.objects.count(), 1)

    @patch("business.cart_additions.CartAddition.objects.get_or_create", side_effect=DatabaseError("PRIVATE"))
    def test_observation_storage_failure_does_not_block_cart(self, save):
        with self.assertLogs("business.cart_additions", level="WARNING") as logs:
            self.assertEqual(self.add().status_code, 200)
        self.assertNotIn("PRIVATE", str(logs.output))

    def test_private_reports_require_existing_dashboard_permission(self):
        staff = get_user_model().objects.create_user(username="panel-staff", is_staff=True)
        for name in ("carts", "audience"):
            url = reverse("business:" + name)
            self.assertEqual(self.client.get(url).status_code, 401)
            self.client.force_authenticate(staff)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_authenticate(None)
        staff.user_permissions.add(Permission.objects.get(codename="view_dashboard"))
        self.client.force_authenticate(get_user_model().objects.get(pk=staff.pk))
        result = self.client.get(reverse("business:carts"), {"start": "2026-11-01", "end": "2026-11-25"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
