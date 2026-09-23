from decimal import Decimal

from django.test import TestCase

from catalog.models import Category, Product
from commerce.meta_conversions import _build_content_id
from commerce.models import Order, OrderItem, Cart, CartItem, BuyNowSession
from commerce.receipts import build_receipt_snapshot, ReceiptEligibility
from commerce.serializers import (
    CartItemSerializer, BuyNowSessionSerializer, OrderItemSerializer, OrderLookupItemSerializer,
)


class CommerceInternalSkuTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Parts", slug="sku-test-parts")
        self.product = Product.objects.create(
            category=category, name="Part", slug="sku-test-part", sku="CM-TEST",
            internal_sku="FD-03-0001", price=Decimal("20.00"), stock_qty=5,
        )
        self.order = Order.objects.create(
            subtotal=20, total=20, first_name="Test", last_name="Buyer", phone="555111222",
            city="Tbilisi", address_line="Test address",
        )

    def item(self, **kwargs):
        return OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            sku=self.product.sku, unit_price=20, quantity=1, line_total=20, **kwargs,
        )

    def test_cart_and_buy_now_only_expose_our_code(self):
        cart = Cart.objects.create()
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price_snapshot=20)
        session = BuyNowSession(product=self.product, quantity=1, unit_price_snapshot=20)
        for serializer, obj in ((CartItemSerializer, item), (BuyNowSessionSerializer, session)):
            data = serializer(obj).data
            self.assertEqual(data["sku"], "FD-03-0001")
            self.assertEqual(data["display_sku"], "FD-03-0001")

    def test_order_receipt_and_analytics_use_frozen_internal_code(self):
        item = self.item(internal_sku="FD-03-0001")
        Product.objects.filter(pk=self.product.pk).update(internal_sku="FD-03-9999")
        item.refresh_from_db()
        for serializer in (OrderItemSerializer, OrderLookupItemSerializer):
            data = serializer(item).data
            self.assertEqual(data["sku"], "FD-03-0001")
            self.assertEqual(data["display_sku"], "FD-03-0001")
        self.assertEqual(_build_content_id(item), "FD-03-0001")
        snapshot = build_receipt_snapshot(self.order, ReceiptEligibility(is_preview=True, payment=None))
        self.assertEqual(snapshot["items"][0]["sku"], "FD-03-0001")

    def test_old_order_keeps_original_code_without_backfill(self):
        item = self.item()
        self.assertEqual(item.display_sku, "CM-TEST")
        snapshot = build_receipt_snapshot(self.order, ReceiptEligibility(is_preview=True, payment=None))
        self.assertEqual(snapshot["items"][0]["sku"], "CM-TEST")
