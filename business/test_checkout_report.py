from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from catalog.models import Category, Product
from commerce.delivery_quote_data import contents_fingerprint, normalize_quote_items
from commerce.models import BuyNowSession, Cart, CartItem, Order, PaymentTransaction, StockReservation
from commerce.services import build_checkout_owner_fingerprint
from commerce.wingo_quotes import QUOTE_SIGNING_SALT

from .authentication import BUSINESS_COOKIE, SESSION_KIND, session_store
from .models import CheckoutProgress
from .reports import TBILISI


class CheckoutReportTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name="Parts", slug="parts")
        self.product = Product.objects.create(category=category, name="ფარი", slug="light", sku="SUP-001",
                                              internal_sku="FD-TEST-1", price=60, shipping_weight_kg=1)
        self.token = uuid4()
        self.cart = Cart.objects.create(guest_token=self.token)
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=1, unit_price_snapshot=60)
        self.client.cookies["cart_token"] = str(self.token)
        self.collect = reverse("business:checkout-progress")
        self.report = reverse("business:checkout")
        self.start = timezone.now().astimezone(TBILISI).replace(hour=10, minute=0, second=0) - timedelta(days=2)

    def observe(self, stage="opened", **fields):
        return self.client.post(self.collect, {"source": "cart", "stage": stage,
            "analytics_consent": True, **fields}, format="json")

    def enable_report(self):
        owner = get_user_model().objects.create_superuser("checkout-owner", "owner@example.test", "test-password")
        session = session_store()
        session.update({"kind": SESSION_KIND, "user_id": owner.pk, "auth_hash": owner.get_session_auth_hash()})
        session.save()
        self.client.cookies[BUSINESS_COOKIE] = session.session_key

    def report_for_product(self, **query):
        day = self.start.astimezone(TBILISI).date().isoformat()
        response = self.client.get(self.report, {"start": day, "end": day, "product_id": self.product.pk, **query})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        return response.data

    def payment(self, minute, status="failed", with_provider=True):
        order = (Order.objects.create(order_number=f"CHECKOUT-{minute}", subtotal=60, total=69, payment_status="paid")
                 if status == "paid" else None)
        paid_at = self.start + timedelta(minutes=minute, seconds=20) if order else None
        reservation = StockReservation.objects.create(guest_token=self.token, expires_at=self.start + timedelta(days=1))
        payment = PaymentTransaction.objects.create(order=order, reservation=reservation, provider="bog", action="sale", status=status,
            amount=69, provider_order_id="PRIVATE-BANK" if with_provider else "", captured_at=paid_at,
            provider_reference={"details": {"order_status": {"key": "rejected"}, "payment_detail": {"code": "109"},
                                            "private": "PRIVATE-CARD"}} if status == "failed" and with_provider else {},
            checkout_snapshot={"source": "cart", "owner_fingerprint": build_checkout_owner_fingerprint(guest_token=self.token),
                "source_reference": {"cart_id": self.cart.pk}, "buyer": {"phone": "PRIVATE-PHONE"},
                "items": [{"product_id": self.product.pk, "quantity": 1, "unit_price": "60.00"}],
                "totals": {"subtotal": "60.00", "delivery": "9.00", "total": "69.00", "currency": "GEL"},
                "delivery": {"service_slug": "standard"}})
        created = self.start + timedelta(minutes=minute)
        PaymentTransaction.objects.filter(pk=payment.pk).update(created_at=created, updated_at=created + timedelta(seconds=20))
        return payment

    def test_collection_needs_existing_checkout_consent_and_csrf_and_deduplicates(self):
        strict = APIClient(enforce_csrf_checks=True)
        self.assertEqual(strict.post(self.collect, {"source": "cart", "stage": "opened",
            "analytics_consent": True}, format="json").status_code, 403)
        self.assertEqual(self.observe(analytics_consent=False).status_code, 204)
        self.assertEqual(self.observe(phone="PRIVATE-PHONE").status_code, 400)
        self.assertEqual(self.observe("quoted", quote_token="forged").status_code, 400)
        self.assertFalse(CheckoutProgress.objects.exists())
        self.assertEqual(self.observe().status_code, 204)
        self.assertEqual(self.observe().status_code, 204)
        self.assertEqual(CheckoutProgress.objects.count(), 1)
        self.client.cookies.clear()
        self.assertEqual(self.observe("form_invalid").status_code, 204)
        self.assertEqual(CheckoutProgress.objects.count(), 1)
        self.assertEqual(self.client.get(self.report).status_code, 401)

    def test_buy_now_and_signed_quote_store_only_safe_fields(self):
        session = BuyNowSession.objects.create(guest_token=self.token, product=self.product, unit_price_snapshot=60, quantity=1)
        session = BuyNowSession.objects.select_related("product").get(pk=session.pk)
        self.client.cookies["buy_now_token"] = str(self.token)
        amount = Decimal("9.00")
        payload = {"source": "buy_now", "service_slug": "standard", "customer_delivery_price": str(amount),
                   "contents_fingerprint": contents_fingerprint(normalize_quote_items([session])),
                   "city_name": "PRIVATE-CITY"}
        token = signing.dumps(payload, salt=QUOTE_SIGNING_SALT)
        self.assertEqual(self.observe("quoted", source="buy_now", quote_token=token).status_code, 204)
        row = CheckoutProgress.objects.get()
        self.assertEqual(row.delivery_amount, amount)
        self.assertEqual(row.delivery_service, "standard")
        self.assertEqual(row.items, [[self.product.pk, 1, "60.00"]])
        self.assertNotIn(str(self.token), str(CheckoutProgress.objects.values().get()))
        self.assertNotIn("PRIVATE-CITY", str(CheckoutProgress.objects.values().get()))

    def test_report_groups_retry_then_paid_and_does_not_expose_identity_or_bank_payload(self):
        self.observe()
        CheckoutProgress.objects.update(created_at=self.start)
        failed = self.payment(1)
        self.payment(2)
        self.payment(3, status="paid")
        self.enable_report()
        report = self.report_for_product(q="FD-TEST-1", result="paid_later")
        self.assertEqual(report["products"][0]["started"], 1)
        self.assertEqual(report["products"][0]["unfinished"], 0)
        case = report["detail"]["cases"][0]
        self.assertEqual(case["result"], "paid_later")
        self.assertEqual(case["payment_attempts"], 3)
        self.assertEqual(case["steps"][0]["label"], "გაფორმების გვერდი გაიხსნა")
        self.assertIn("ბანკმა ტექნიკური შეცდომა დააფიქსირა", [step["label"] for step in case["steps"]])
        self.assertNotIn("PRIVATE", str(report))
        self.assertNotIn(str(self.token), str(report))
        failed.refresh_from_db()
        self.assertEqual(failed.status, "failed")

    def test_report_distinguishes_form_problem_from_missing_bank_reply(self):
        self.observe("form_invalid")
        CheckoutProgress.objects.update(created_at=self.start)
        self.enable_report()
        case = self.report_for_product()["detail"]["cases"][0]
        self.assertEqual(case["result"], "before_bank")
        self.assertEqual(case["reason"], "ფორმა შევსებას ან შესწორებას ითხოვდა")
        self.payment(2, status="pending", with_provider=False)
        case = self.report_for_product()["detail"]["cases"][0]
        self.assertEqual(case["result"], "bank_pending")
        self.assertIn("ბანკის პასუხი ჯერ ვერ დადასტურდა", [step["label"] for step in case["steps"]])
