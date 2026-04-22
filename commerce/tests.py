import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import Category, Product, ProductImage, ProductStatus

from .images import build_product_primary_image_snapshot
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    Order,
    OrderCheckoutSource,
    OrderItem,
    OrderPaymentMethod,
    OrderStatus,
    WishlistItem,
)
from .services import (
    BUY_NOW_ACTION_CONFIRM_UPDATES,
    BUY_NOW_ACTION_RESTART,
    BUY_NOW_ACTION_RETURN_TO_PRODUCT,
    BUY_NOW_AVAILABILITY_CHANGED_CODE,
    BUY_NOW_PRICE_CHANGED_CODE,
    BUY_NOW_PRICE_CHANGED_DETAIL,
    BUY_NOW_QUANTITY_MISMATCH_DETAIL,
    BUY_NOW_SESSION_EXPIRED_CODE,
    BUY_NOW_SESSION_INACTIVE_DETAIL,
    BUY_NOW_SESSION_NOT_FOUND_CODE,
    BUY_NOW_TOKEN_COOKIE_NAME,
    BUY_NOW_UNAVAILABLE_DETAIL,
    CART_AVAILABILITY_CHANGED_CODE,
    CART_TOKEN_COOKIE_NAME,
    CHECKOUT_PRODUCT_UNAVAILABLE_DETAIL,
    CHECKOUT_STOCK_MISMATCH_DETAIL,
    WISHLIST_TOKEN_COOKIE_NAME,
    cancel_order_and_restore_stock,
    transition_order_status,
)


def _generate_test_image(filename="sample.jpg", color=(255, 0, 0)):
    file_obj = BytesIO()
    image = Image.new("RGB", (100, 100), color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


class CommerceAPITests(APITestCase):
    def setUp(self):
        WishlistItem.objects.all().delete()
        CartItem.objects.all().delete()
        Cart.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        get_user_model().objects.filter(
            email__in=["buyer@example.com", "other@example.com"],
        ).delete()

        self.user = get_user_model().objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="Password123!",
            is_active=True,
        )
        self.other_user = get_user_model().objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="Password123!",
            is_active=True,
        )
        self.category = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.product = Product.objects.create(
            category=self.category,
            name="Car Vacuum 53",
            slug="car-vacuum-53",
            sku="CV-53",
            short_description="Daily cleaning",
            description="Long description",
            price=Decimal("120.00"),
            old_price=Decimal("150.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )
        self.second_product = Product.objects.create(
            category=self.category,
            name="Dash Cam 44",
            slug="dash-cam-44",
            sku="DC-44",
            short_description="Dash cam",
            description="4K dash cam",
            price=Decimal("300.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )
        self.draft_product = Product.objects.create(
            category=self.category,
            name="Draft Product",
            slug="draft-product",
            sku="DRAFT-1",
            short_description="Draft",
            description="Draft",
            price=Decimal("99.00"),
            stock_qty=3,
            status=ProductStatus.DRAFT,
        )
        self.archived_product = Product.objects.create(
            category=self.category,
            name="Archived Product",
            slug="archived-product",
            sku="ARCHIVED-1",
            short_description="Archived",
            description="Archived",
            price=Decimal("89.00"),
            stock_qty=3,
            status=ProductStatus.ARCHIVED,
        )
        self.inactive_category = Category.objects.create(
            name="Inactive",
            slug="inactive",
            sort_order=2,
            is_active=False,
        )
        self.inactive_category_product = Product.objects.create(
            category=self.inactive_category,
            name="Inactive Category Product",
            slug="inactive-category-product",
            sku="INACTIVE-1",
            short_description="Inactive",
            description="Inactive",
            price=Decimal("79.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        self.out_of_stock_product = Product.objects.create(
            category=self.category,
            name="Sold Out Adapter",
            slug="sold-out-adapter",
            sku="SOLDOUT-1",
            short_description="Sold out",
            description="Sold out",
            price=Decimal("45.00"),
            stock_qty=0,
            status=ProductStatus.PUBLISHED,
        )
        ProductImage.objects.create(
            product=self.product,
            image_desktop=_generate_test_image("vacuum.jpg"),
            is_primary=True,
            sort_order=1,
            alt_text="Vacuum image",
        )
        ProductImage.objects.create(
            product=self.out_of_stock_product,
            image_desktop=_generate_test_image("sold-out.jpg", color=(0, 255, 0)),
            is_primary=True,
            sort_order=1,
            alt_text="Sold out image",
        )
        self.recaptcha_patcher = patch("commerce.views.validate_recaptcha", return_value=True)
        self.recaptcha_patcher.start()
        self.addCleanup(self.recaptcha_patcher.stop)

    def _create_order(self, *, user, suffix, status=OrderStatus.NEW):
        order = Order.objects.create(
            user=user,
            order_number=f"ORD-20260315-{suffix:06d}",
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            status=status,
            subtotal=Decimal("120.00"),
            total=Decimal("120.00"),
            first_name="Test",
            last_name="Buyer",
            email="buyer@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Saburtalo 1",
            note="",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=self.product.price,
            quantity=1,
            line_total=self.product.price,
            primary_image_snapshot=build_product_primary_image_snapshot(self.product),
        )
        return order

    def _create_multi_quantity_order(self, *, user, suffix, quantity, status=OrderStatus.NEW):
        order = Order.objects.create(
            user=user,
            order_number=f"ORD-20260315-{suffix:06d}",
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            status=status,
            subtotal=self.product.price * quantity,
            total=self.product.price * quantity,
            first_name="Test",
            last_name="Buyer",
            email="buyer@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Saburtalo 1",
            note="",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=self.product.price,
            quantity=quantity,
            line_total=self.product.price * quantity,
            primary_image_snapshot=build_product_primary_image_snapshot(self.product),
        )
        return order

    def _checkout_payload(self):
        return {
            "first_name": "Nino",
            "last_name": "Beridze",
            "email": "nino@example.com",
            "phone": "555123456",
            "city": "Tbilisi",
            "address_line": "Saburtalo 1",
            "note": "",
            "terms_accepted": True,
            "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
        }

    def test_guest_get_cart_creates_cookie_and_empty_cart(self):
        response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_count"], 0)
        self.assertEqual(response.data["subtotal"], "0.00")
        self.assertIn(CART_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(Cart.objects.filter(user__isnull=True, is_active=True).count(), 1)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_authenticated_get_cart_is_bound_to_user(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Cart.objects.filter(user=self.user, is_active=True).exists())
        self.assertNotIn(CART_TOKEN_COOKIE_NAME, response.cookies)

    def test_guest_cart_merges_into_user_cart_on_authenticated_request(self):
        guest_add_response = self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        guest_cart_token = guest_add_response.cookies[CART_TOKEN_COOKIE_NAME].value

        user_cart = Cart.objects.create(user=self.user, is_active=True)
        CartItem.objects.create(cart=user_cart, product=self.product, quantity=4)

        self.client.cookies[CART_TOKEN_COOKIE_NAME] = guest_cart_token
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_count"], 5)
        self.assertEqual(response.data["items"][0]["quantity"], 5)
        self.assertFalse(Cart.objects.get(guest_token=guest_cart_token).is_active)
        self.assertIn(CART_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[CART_TOKEN_COOKIE_NAME].value, "")

    def test_authenticated_cart_request_clears_stale_guest_cart_cookie(self):
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = str(uuid.uuid4())
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(CART_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[CART_TOKEN_COOKIE_NAME].value, "")
        self.assertTrue(Cart.objects.filter(user=self.user, is_active=True).exists())

    def test_authenticated_cart_repeated_guest_cookie_requests_remain_safe(self):
        guest_add_response = self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        guest_cart_token = guest_add_response.cookies[CART_TOKEN_COOKIE_NAME].value

        user_cart = Cart.objects.create(user=self.user, is_active=True)
        CartItem.objects.create(cart=user_cart, product=self.product, quantity=4)

        self.client.cookies[CART_TOKEN_COOKIE_NAME] = guest_cart_token
        self.client.force_authenticate(user=self.user)

        first_response = self.client.get(reverse("commerce-cart"))
        self.client.cookies[CART_TOKEN_COOKIE_NAME] = guest_cart_token
        second_response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["item_count"], 5)
        self.assertEqual(second_response.data["item_count"], 5)
        self.assertEqual(CartItem.objects.get(cart=user_cart, product=self.product).quantity, 5)
        self.assertFalse(Cart.objects.get(guest_token=guest_cart_token).is_active)

    def test_add_to_cart_rejects_unavailable_product(self):
        response = self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.draft_product.id, "quantity": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["product_id"][0], "Product is not available.")

    def test_add_update_and_delete_cart_item(self):
        add_response = self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        item_id = add_response.data["items"][0]["id"]

        update_response = self.client.patch(
            reverse("commerce-cart-item-detail", kwargs={"pk": item_id}),
            {"quantity": 3},
            format="json",
        )
        delete_response = self.client.delete(
            reverse("commerce-cart-item-detail", kwargs={"pk": item_id}),
        )

        self.assertEqual(add_response.status_code, status.HTTP_200_OK)
        self.assertEqual(add_response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["items"][0]["quantity"], 3)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data["items"], [])

    def test_update_cart_item_rejects_quantity_above_stock(self):
        add_response = self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.second_product.id, "quantity": 1},
            format="json",
        )
        item_id = add_response.data["items"][0]["id"]

        response = self.client.patch(
            reverse("commerce-cart-item-detail", kwargs={"pk": item_id}),
            {"quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data["quantity"]), "Requested quantity exceeds available stock.")

    def test_cart_response_marks_price_changes_when_product_price_changes(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])

        response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_price_changes"])
        self.assertEqual(response.data["price_change_count"], 1)
        self.assertEqual(
            response.data["price_change_message"],
            "კალათაში არსებული პროდუქტის ფასი შეიცვალა. გადაამოწმეთ ახალი ფასი და დაადასტურეთ გაგრძელება.",
        )
        self.assertEqual(response.data["items"][0]["price_snapshot"], "120.00")
        self.assertEqual(response.data["items"][0]["price"], "135.00")
        self.assertTrue(response.data["items"][0]["price_changed"])
        self.assertEqual(response.data["items"][0]["price_change_direction"], "increase")

    def test_confirm_cart_prices_endpoint_updates_snapshots(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])

        response = self.client.post(reverse("commerce-cart-confirm-prices"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["has_price_changes"])
        self.assertEqual(response.data["price_change_count"], 0)
        self.assertIsNone(response.data["price_change_message"])
        self.assertEqual(response.data["items"][0]["price_snapshot"], "135.00")
        self.assertFalse(response.data["items"][0]["price_changed"])
        self.assertEqual(CartItem.objects.get().unit_price_snapshot, Decimal("135.00"))

    def test_checkout_rejects_empty_cart(self):
        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data["detail"]), "Cart is empty.")

    def test_checkout_rejects_when_cart_item_price_has_changed(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["detail"],
            "კალათაში არსებული პროდუქტის ფასი შეიცვალა. გადაამოწმეთ ახალი ფასი და დაადასტურეთ გაგრძელება.",
        )
        self.assertEqual(response.data["code"], "cart_price_changed")
        self.assertEqual(int(str(response.data["price_change_count"])), 1)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().unit_price_snapshot, Decimal("120.00"))
        self.assertEqual(self.product.stock_qty, 5)

    def test_checkout_uses_new_price_after_confirming_updated_cart_prices(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])
        self.client.post(reverse("commerce-cart-confirm-prices"))

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.subtotal, Decimal("270.00"))
        self.assertEqual(order.total, Decimal("270.00"))
        self.assertEqual(order.items.get().unit_price, Decimal("135.00"))
        self.assertEqual(order.items.get().line_total, Decimal("270.00"))

    def test_cart_response_exposes_current_item_availability_flags(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.second_product.id, "quantity": 1},
            format="json",
        )

        self.product.stock_qty = 0
        self.product.save(update_fields=["stock_qty", "updated_at"])
        self.second_product.status = ProductStatus.ARCHIVED
        self.second_product.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("commerce-cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items_by_product_id = {
            item["product_id"]: item
            for item in response.data["items"]
        }
        self.assertEqual(items_by_product_id[self.product.id]["availability_issue"], "out_of_stock")
        self.assertFalse(items_by_product_id[self.product.id]["is_purchasable"])
        self.assertEqual(items_by_product_id[self.second_product.id]["availability_issue"], "unavailable")
        self.assertFalse(items_by_product_id[self.second_product.id]["is_purchasable"])

    def test_checkout_rejects_when_product_is_no_longer_available(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        self.product.status = ProductStatus.ARCHIVED
        self.product.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], CHECKOUT_PRODUCT_UNAVAILABLE_DETAIL)
        self.assertEqual(response.data["code"], CART_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(
            response.data["cart_issues"],
            [
                {
                    "cart_item_id": CartItem.objects.get().id,
                    "product_id": self.product.id,
                    "issue_type": "unavailable",
                    "requested_quantity": 1,
                    "available_quantity": 0,
                }
            ],
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().quantity, 1)
        self.assertEqual(self.product.stock_qty, 5)

    def test_checkout_rejects_when_requested_quantity_exceeds_current_stock(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        self.product.stock_qty = 1
        self.product.save(update_fields=["stock_qty", "updated_at"])

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], CHECKOUT_STOCK_MISMATCH_DETAIL)
        self.assertEqual(response.data["code"], CART_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(
            response.data["cart_issues"],
            [
                {
                    "cart_item_id": CartItem.objects.get().id,
                    "product_id": self.product.id,
                    "issue_type": "quantity_adjusted",
                    "requested_quantity": 2,
                    "available_quantity": 1,
                }
            ],
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().quantity, 1)
        self.assertEqual(self.product.stock_qty, 1)

    def test_cash_on_delivery_checkout_creates_order_and_reduces_stock(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.second_product.id, "quantity": 1},
            format="json",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "Please call first",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.product.refresh_from_db()
        self.second_product.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.subtotal, Decimal("540.00"))
        self.assertEqual(order.total, Decimal("540.00"))
        self.assertTrue(order.order_number.startswith("ORD-"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(self.second_product.stock_qty, 1)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(response.data["items"][0]["product_name"], "Car Vacuum 53")
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")

    def test_guest_create_buy_now_session_sets_cookie_and_returns_summary(self):
        response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(BuyNowSession.objects.count(), 1)
        session = BuyNowSession.objects.get()
        self.assertIsNone(session.user)
        self.assertEqual(session.product, self.product)
        self.assertEqual(session.quantity, 2)
        self.assertEqual(session.unit_price_snapshot, Decimal("120.00"))
        self.assertEqual(response.data["product_id"], self.product.id)
        self.assertEqual(response.data["quantity"], 2)
        self.assertEqual(response.data["price_snapshot"], "120.00")
        self.assertEqual(response.data["total"], "240.00")
        self.assertEqual(response.data["issues"], [])
        self.assertTrue(response.data["is_checkout_available"])

    def test_authenticated_create_buy_now_session_binds_to_user_without_cookie(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(BuyNowSession.objects.filter(user=self.user).count(), 1)
        self.assertNotIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)

    def test_repeated_buy_now_create_replaces_existing_session(self):
        first_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = first_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        second_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.second_product.id, "quantity": 2},
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(BuyNowSession.objects.count(), 1)
        session = BuyNowSession.objects.get()
        self.assertEqual(session.product, self.second_product)
        self.assertEqual(session.quantity, 2)
        self.assertEqual(second_response.data["product_id"], self.second_product.id)

    def test_guest_buy_now_session_claims_into_user_and_replaces_existing_user_session(self):
        guest_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        guest_token = guest_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value

        BuyNowSession.objects.create(
            user=self.user,
            product=self.second_product,
            quantity=1,
            unit_price_snapshot=self.second_product.price,
        )

        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("commerce-buy-now-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(BuyNowSession.objects.filter(user=self.user).count(), 1)
        session = BuyNowSession.objects.get(user=self.user)
        self.assertEqual(session.product, self.product)
        self.assertEqual(session.quantity, 2)
        self.assertFalse(BuyNowSession.objects.filter(guest_token=guest_token).exists())
        self.assertIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value, "")

    def test_buy_now_get_returns_404_without_session(self):
        response = self.client.get(reverse("commerce-buy-now-session"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], BUY_NOW_SESSION_INACTIVE_DETAIL)
        self.assertEqual(response.data["code"], BUY_NOW_SESSION_NOT_FOUND_CODE)
        self.assertEqual(response.data["source"], "buy_now")
        self.assertEqual(response.data["recommended_action"], BUY_NOW_ACTION_RESTART)

    def test_expired_buy_now_session_returns_410_and_deletes_row(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        BuyNowSession.objects.update(
            updated_at=timezone.now() - timedelta(seconds=settings.BUY_NOW_SESSION_TTL_SECONDS + 1)
        )
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.get(reverse("commerce-buy-now-session"))

        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertEqual(response.data["code"], BUY_NOW_SESSION_EXPIRED_CODE)
        self.assertEqual(response.data["recommended_action"], BUY_NOW_ACTION_RESTART)
        self.assertEqual(BuyNowSession.objects.count(), 0)
        self.assertIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value, "")

    def test_delete_buy_now_session_removes_session_and_clears_cookie(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.delete(reverse("commerce-buy-now-session"))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(BuyNowSession.objects.count(), 0)
        self.assertIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value, "")

    def test_get_buy_now_session_reports_price_change_and_requires_confirmation(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.get(reverse("commerce-buy-now-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["price_changed"])
        self.assertEqual(response.data["issues"][0]["issue_type"], "price_changed")
        self.assertTrue(response.data["requires_confirmation"])
        self.assertFalse(response.data["is_checkout_available"])
        self.assertEqual(response.data["price_snapshot"], "120.00")
        self.assertEqual(response.data["price"], "135.00")

    def test_confirm_buy_now_session_updates_price_snapshot(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(reverse("commerce-buy-now-session-confirm"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["price_snapshot"], "135.00")
        self.assertFalse(response.data["price_changed"])
        self.assertEqual(response.data["issues"], [])
        self.assertFalse(response.data["requires_confirmation"])
        self.assertTrue(response.data["is_checkout_available"])
        self.assertEqual(BuyNowSession.objects.get().unit_price_snapshot, Decimal("135.00"))

    def test_confirm_buy_now_session_adjusts_quantity_down_to_stock(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.second_product.id, "quantity": 2},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.second_product.stock_qty = 1
        self.second_product.save(update_fields=["stock_qty", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(reverse("commerce-buy-now-session-confirm"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quantity"], 1)
        self.assertEqual(response.data["issues"], [])
        self.assertTrue(response.data["is_checkout_available"])
        self.assertEqual(BuyNowSession.objects.get().quantity, 1)

    def test_confirm_buy_now_session_updates_price_and_quantity_together(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.second_product.id, "quantity": 2},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.second_product.price = Decimal("350.00")
        self.second_product.stock_qty = 1
        self.second_product.save(update_fields=["price", "stock_qty", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(reverse("commerce-buy-now-session-confirm"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quantity"], 1)
        self.assertEqual(response.data["price_snapshot"], "350.00")
        self.assertEqual(response.data["issues"], [])
        session = BuyNowSession.objects.get()
        self.assertEqual(session.quantity, 1)
        self.assertEqual(session.unit_price_snapshot, Decimal("350.00"))

    def test_confirm_buy_now_session_rejects_unavailable_product(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.product.status = ProductStatus.ARCHIVED
        self.product.save(update_fields=["status", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(reverse("commerce-buy-now-session-confirm"))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["detail"], BUY_NOW_UNAVAILABLE_DETAIL)
        self.assertEqual(response.data["code"], BUY_NOW_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(response.data["recommended_action"], BUY_NOW_ACTION_RETURN_TO_PRODUCT)
        self.assertEqual(response.data["buy_now_issues"][0]["issue_type"], "unavailable")
        self.assertEqual(BuyNowSession.objects.get().quantity, 1)

    def test_buy_now_checkout_creates_order_and_deletes_session(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertIsNone(order.user)
        self.assertEqual(order.checkout_source, OrderCheckoutSource.BUY_NOW)
        self.assertEqual(order.total, Decimal("240.00"))
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(BuyNowSession.objects.count(), 0)
        self.assertIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value, "")

    def test_buy_now_checkout_rejects_when_price_has_changed(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.product.price = Decimal("135.00")
        self.product.save(update_fields=["price", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["detail"], BUY_NOW_PRICE_CHANGED_DETAIL)
        self.assertEqual(response.data["code"], BUY_NOW_PRICE_CHANGED_CODE)
        self.assertEqual(response.data["recommended_action"], BUY_NOW_ACTION_CONFIRM_UPDATES)
        self.assertEqual(response.data["buy_now_issues"][0]["issue_type"], "price_changed")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(BuyNowSession.objects.count(), 1)
        self.assertEqual(BuyNowSession.objects.get().unit_price_snapshot, Decimal("120.00"))
        self.assertEqual(self.product.stock_qty, 5)

    def test_buy_now_checkout_rejects_when_quantity_exceeds_current_stock(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.second_product.id, "quantity": 2},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.second_product.stock_qty = 1
        self.second_product.save(update_fields=["stock_qty", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["detail"], BUY_NOW_QUANTITY_MISMATCH_DETAIL)
        self.assertEqual(response.data["code"], BUY_NOW_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(response.data["recommended_action"], BUY_NOW_ACTION_CONFIRM_UPDATES)
        self.assertEqual(response.data["buy_now_issues"][0]["issue_type"], "quantity_adjusted")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(BuyNowSession.objects.get().quantity, 2)
        self.assertEqual(self.second_product.stock_qty, 1)

    def test_buy_now_checkout_rejects_when_product_is_unavailable(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.product.status = ProductStatus.ARCHIVED
        self.product.save(update_fields=["status", "updated_at"])
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["detail"], BUY_NOW_UNAVAILABLE_DETAIL)
        self.assertEqual(response.data["code"], BUY_NOW_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(response.data["recommended_action"], BUY_NOW_ACTION_RETURN_TO_PRODUCT)
        self.assertEqual(response.data["buy_now_issues"][0]["issue_type"], "unavailable")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(BuyNowSession.objects.count(), 1)

    def test_checkout_allows_empty_email(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        self.assertEqual(order.email, "")

    def test_checkout_requires_terms_acceptance(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": False,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["terms_accepted"][0],
            "შეკვეთის დასადასტურებლად დაეთანხმეთ წესებსა და პირობებს.",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_rejects_request_when_recaptcha_fails(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        with patch("commerce.views.validate_recaptcha", return_value=False):
            response = self.client.post(
                reverse("commerce-order-checkout"),
                {
                    "first_name": "Nino",
                    "last_name": "Beridze",
                    "phone": "555123456",
                    "city": "Tbilisi",
                    "address_line": "Saburtalo 1",
                    "note": "",
                    "terms_accepted": True,
                    "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "უსაფრთხოების შემოწმება ვერ გაიარა.")
        self.assertEqual(Order.objects.count(), 0)

    def test_card_checkout_returns_validation_error(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CARD,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["payment_method"][0], "Card payments are temporarily unavailable.")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 5)
        self.assertEqual(Order.objects.count(), 0)

    def test_order_summary_endpoint_returns_public_order_data(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        checkout_response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        response = self.client.get(
            reverse(
                "commerce-order-summary",
                kwargs={"public_token": checkout_response.data["public_token"]},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_number"], checkout_response.data["order_number"])
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")

    def test_order_summary_keeps_image_snapshot_after_product_image_changes(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        checkout_response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                "first_name": "Nino",
                "last_name": "Beridze",
                "email": "nino@example.com",
                "phone": "555123456",
                "city": "Tbilisi",
                "address_line": "Saburtalo 1",
                "note": "",
                "terms_accepted": True,
                "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
            },
            format="json",
        )

        original_image = self.product.images.get(is_primary=True)
        original_image.is_primary = False
        original_image.save(update_fields=["is_primary", "updated_at"])
        ProductImage.objects.create(
            product=self.product,
            image_desktop=_generate_test_image("replacement.jpg", color=(0, 0, 255)),
            is_primary=True,
            sort_order=2,
            alt_text="Replacement image",
        )

        response = self.client.get(
            reverse(
                "commerce-order-summary",
                kwargs={"public_token": checkout_response.data["public_token"]},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")

    def test_authenticated_order_list_returns_only_current_user_orders(self):
        own_new = self._create_order(user=self.user, suffix=1, status=OrderStatus.NEW)
        own_delivered = self._create_order(user=self.user, suffix=2, status=OrderStatus.DELIVERED)
        self._create_order(user=self.other_user, suffix=3, status=OrderStatus.SHIPPED)
        self._create_order(user=None, suffix=4, status=OrderStatus.CANCELLED)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("commerce-order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["summary"]["total_orders"], 2)
        self.assertEqual(response.data["summary"]["total_spent"], "240.00")
        self.assertIsNotNone(response.data["summary"]["last_order_at"])
        returned_tokens = {item["public_token"] for item in response.data["results"]}
        self.assertIn(str(own_new.public_token), returned_tokens)
        self.assertIn(str(own_delivered.public_token), returned_tokens)
        self.assertEqual(response.data["results"][0]["item_count"], 1)

    def test_authenticated_order_list_is_paginated(self):
        for suffix in range(1, 12):
            self._create_order(user=self.user, suffix=suffix, status=OrderStatus.NEW)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("commerce-order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 11)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(response.data["summary"]["total_orders"], 11)
        self.assertEqual(response.data["summary"]["total_spent"], "1320.00")
        self.assertIsNotNone(response.data["next"])

    def test_authenticated_order_list_returns_total_quantity_for_each_order(self):
        order = self._create_multi_quantity_order(
            user=self.user,
            suffix=50,
            quantity=4,
            status=OrderStatus.NEW,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("commerce-order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = next(
            item
            for item in response.data["results"]
            if item["public_token"] == str(order.public_token)
        )
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["total_quantity"], 4)

    def test_order_summary_excludes_cancelled_orders_from_total_spent(self):
        self._create_order(user=self.user, suffix=30, status=OrderStatus.NEW)
        self._create_order(user=self.user, suffix=31, status=OrderStatus.CANCELLED)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("commerce-order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_orders"], 2)
        self.assertEqual(response.data["summary"]["total_spent"], "120.00")

    def test_authenticated_order_detail_returns_owner_order(self):
        order = self._create_order(user=self.user, suffix=10, status=OrderStatus.SHIPPED)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse("commerce-order-detail", kwargs={"public_token": order.public_token})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_number"], order.order_number)
        self.assertEqual(response.data["status"], OrderStatus.SHIPPED)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")

    def test_authenticated_order_detail_returns_404_for_foreign_order(self):
        foreign_order = self._create_order(user=self.other_user, suffix=20, status=OrderStatus.NEW)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse("commerce-order-detail", kwargs={"public_token": foreign_order.public_token})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_guest_wishlist_returns_empty_results_and_sets_cookie(self):
        response = self.client.get(reverse("commerce-wishlist"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertIn(WISHLIST_TOKEN_COOKIE_NAME, response.cookies)

    def test_guest_add_wishlist_item_is_idempotent(self):
        first_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )
        guest_wishlist_token = first_response.cookies[WISHLIST_TOKEN_COOKIE_NAME].value
        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = guest_wishlist_token

        second_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            WishlistItem.objects.filter(user__isnull=True, guest_token=guest_wishlist_token, product=self.product)
            .count(),
            1,
        )
        self.assertEqual(second_response.data["count"], 1)

    def test_guest_remove_wishlist_item_is_idempotent(self):
        add_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )
        guest_wishlist_token = add_response.cookies[WISHLIST_TOKEN_COOKIE_NAME].value
        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = guest_wishlist_token

        first_response = self.client.delete(
            reverse("commerce-wishlist-item-detail", kwargs={"product_id": self.product.id})
        )
        second_response = self.client.delete(
            reverse("commerce-wishlist-item-detail", kwargs={"product_id": self.product.id})
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            WishlistItem.objects.filter(user__isnull=True, guest_token=guest_wishlist_token).count(),
            0,
        )
        self.assertEqual(second_response.data["count"], 0)

    def test_authenticated_wishlist_returns_only_current_user_public_items(self):
        WishlistItem.objects.create(user=self.user, product=self.product)
        WishlistItem.objects.create(user=self.user, product=self.out_of_stock_product)
        WishlistItem.objects.create(user=self.user, product=self.archived_product)
        WishlistItem.objects.create(user=self.user, product=self.inactive_category_product)
        WishlistItem.objects.create(user=self.other_user, product=self.second_product)
        WishlistItem.objects.create(guest_token=uuid.uuid4(), product=self.second_product)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("commerce-wishlist"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        returned_product_ids = {item["product_id"] for item in response.data["results"]}
        self.assertEqual(returned_product_ids, {self.product.id, self.out_of_stock_product.id})
        sold_out_item = next(
            item for item in response.data["results"] if item["product_id"] == self.out_of_stock_product.id
        )
        self.assertFalse(sold_out_item["in_stock"])
        self.assertEqual(sold_out_item["stock_qty"], 0)

    def test_guest_wishlist_merges_into_user_wishlist_on_authenticated_request(self):
        guest_add_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )
        guest_wishlist_token = guest_add_response.cookies[WISHLIST_TOKEN_COOKIE_NAME].value
        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = guest_wishlist_token
        self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.second_product.id},
            format="json",
        )

        WishlistItem.objects.create(user=self.user, product=self.product)

        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = guest_wishlist_token
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("commerce-wishlist"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        returned_product_ids = {item["product_id"] for item in response.data["results"]}
        self.assertEqual(returned_product_ids, {self.product.id, self.second_product.id})
        self.assertFalse(
            WishlistItem.objects.filter(user__isnull=True, guest_token=guest_wishlist_token).exists()
        )
        self.assertIn(WISHLIST_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[WISHLIST_TOKEN_COOKIE_NAME].value, "")

    def test_authenticated_wishlist_repeated_guest_cookie_requests_remain_safe(self):
        guest_add_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )
        guest_wishlist_token = guest_add_response.cookies[WISHLIST_TOKEN_COOKIE_NAME].value
        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = guest_wishlist_token
        self.client.force_authenticate(user=self.user)

        first_response = self.client.get(reverse("commerce-wishlist"))
        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = guest_wishlist_token
        second_response = self.client.get(reverse("commerce-wishlist"))

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["count"], 1)
        self.assertEqual(second_response.data["count"], 1)
        self.assertEqual(WishlistItem.objects.filter(user=self.user, product=self.product).count(), 1)
        self.assertFalse(
            WishlistItem.objects.filter(user__isnull=True, guest_token=guest_wishlist_token).exists()
        )

    def test_authenticated_wishlist_request_clears_stale_guest_wishlist_cookie(self):
        self.client.cookies[WISHLIST_TOKEN_COOKIE_NAME] = str(uuid.uuid4())
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("commerce-wishlist"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(WISHLIST_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[WISHLIST_TOKEN_COOKIE_NAME].value, "")

    def test_add_wishlist_item_is_idempotent(self):
        self.client.force_authenticate(user=self.user)

        first_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )
        second_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.product.id},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(WishlistItem.objects.filter(user=self.user, product=self.product).count(), 1)
        self.assertEqual(second_response.data["count"], 1)

    def test_add_wishlist_item_rejects_unavailable_product(self):
        self.client.force_authenticate(user=self.user)

        draft_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.draft_product.id},
            format="json",
        )
        archived_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.archived_product.id},
            format="json",
        )
        inactive_response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.inactive_category_product.id},
            format="json",
        )

        self.assertEqual(draft_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(archived_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(inactive_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(draft_response.data["product_id"][0], "Product is not available.")

    def test_add_wishlist_item_allows_out_of_stock_product(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            reverse("commerce-wishlist-item-list"),
            {"product_id": self.out_of_stock_product.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["product_id"], self.out_of_stock_product.id)
        self.assertFalse(response.data["results"][0]["in_stock"])

    def test_remove_wishlist_item_is_idempotent(self):
        WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_authenticate(user=self.user)

        first_response = self.client.delete(
            reverse("commerce-wishlist-item-detail", kwargs={"product_id": self.product.id})
        )
        second_response = self.client.delete(
            reverse("commerce-wishlist-item-detail", kwargs={"product_id": self.product.id})
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(WishlistItem.objects.filter(user=self.user).count(), 0)
        self.assertEqual(second_response.data["count"], 0)

    def test_deleted_product_disappears_from_wishlist(self):
        WishlistItem.objects.create(user=self.user, product=self.product)
        self.product.delete()

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("commerce-wishlist"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertFalse(WishlistItem.objects.filter(user=self.user).exists())


class CommerceLifecycleServiceTests(TestCase):
    def setUp(self):
        Category.objects.all().delete()
        Product.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()

        self.category = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.product = Product.objects.create(
            category=self.category,
            name="Car Vacuum 53",
            slug="car-vacuum-53",
            sku="CV-53",
            short_description="Daily cleaning",
            description="Long description",
            price=Decimal("120.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )

    def _create_order(self, *, status=OrderStatus.NEW, quantity=3, product=None):
        order = Order.objects.create(
            order_number=f"ORD-20260316-{Order.objects.count() + 1:06d}",
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            status=status,
            subtotal=Decimal("120.00") * quantity,
            total=Decimal("120.00") * quantity,
            first_name="Test",
            last_name="Buyer",
            email="buyer@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Saburtalo 1",
            note="",
        )
        OrderItem.objects.create(
            order=order,
            product=product if product is not None else self.product,
            product_name="Car Vacuum 53",
            sku="CV-53",
            unit_price=Decimal("120.00"),
            quantity=quantity,
            line_total=Decimal("120.00") * quantity,
            primary_image_snapshot=build_product_primary_image_snapshot(
                product if product is not None else self.product
            ),
        )
        return order

    def test_cancel_order_and_restore_stock_updates_status_and_stock(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=3)

        cancel_order_and_restore_stock(order)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.stock_restored_at)
        self.assertEqual(self.product.stock_qty, 5)

    def test_cancel_order_and_restore_stock_rejects_shipped_order(self):
        order = self._create_order(status=OrderStatus.SHIPPED)

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Only new, confirmed, or processing orders can be cancelled.",
        ):
            cancel_order_and_restore_stock(order)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SHIPPED)
        self.assertIsNone(order.stock_restored_at)
        self.assertEqual(self.product.stock_qty, 2)

    def test_cancel_order_and_restore_stock_cannot_restore_twice(self):
        order = self._create_order(status=OrderStatus.CONFIRMED, quantity=2)

        cancel_order_and_restore_stock(order)
        self.product.refresh_from_db()
        first_stock = self.product.stock_qty

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Only new, confirmed, or processing orders can be cancelled.",
        ):
            cancel_order_and_restore_stock(order)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, first_stock)

    def test_transition_order_status_allows_forward_transition(self):
        order = self._create_order(status=OrderStatus.NEW)

        transition_order_status(order, OrderStatus.PROCESSING)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PROCESSING)

    def test_transition_order_status_rejects_backward_transition(self):
        order = self._create_order(status=OrderStatus.DELIVERED)

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Cannot change status from 'Delivered' to 'Processing'.",
        ):
            transition_order_status(order, OrderStatus.PROCESSING)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DELIVERED)

    def test_cancel_order_and_restore_stock_fails_when_order_item_product_is_missing(self):
        order = self._create_order(status=OrderStatus.NEW, product=self.product)
        order_item = order.items.get()
        order_item.product = None
        order_item.save(update_fields=["product", "updated_at"])

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Cannot restore stock because one or more order items are no longer linked to a product.",
        ):
            cancel_order_and_restore_stock(order)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertIsNone(order.stock_restored_at)


class CommerceAdminTests(TestCase):
    def setUp(self):
        Category.objects.all().delete()
        Product.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        get_user_model().objects.filter(email="admin@example.com").delete()

        self.client = Client()
        self.superuser = get_user_model().objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="Password123!",
        )
        self.client.force_login(self.superuser)

        self.category = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.product = Product.objects.create(
            category=self.category,
            name="Car Vacuum 53",
            slug="car-vacuum-53",
            sku="CV-53",
            short_description="Daily cleaning",
            description="Long description",
            price=Decimal("120.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )

    def _create_order(self, *, status=OrderStatus.NEW, quantity=3):
        order = Order.objects.create(
            order_number=f"ORD-20260316-{Order.objects.count() + 1:06d}",
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            status=status,
            subtotal=Decimal("120.00") * quantity,
            total=Decimal("120.00") * quantity,
            first_name="Test",
            last_name="Buyer",
            email="buyer@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Saburtalo 1",
            note="",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=self.product.price,
            quantity=quantity,
            line_total=self.product.price * quantity,
            primary_image_snapshot=build_product_primary_image_snapshot(self.product),
        )
        return order

    def _build_admin_payload(self, order, **overrides):
        payload = {
            "payment_method": order.payment_method,
            "status": order.status,
            "first_name": order.first_name,
            "last_name": order.last_name,
            "email": order.email,
            "phone": order.phone,
            "city": order.city,
            "address_line": order.address_line,
            "note": order.note,
            "items-TOTAL_FORMS": str(order.items.count()),
            "items-INITIAL_FORMS": str(order.items.count()),
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
        }
        for index, item in enumerate(order.items.all()):
            payload[f"items-{index}-id"] = str(item.pk)
            payload[f"items-{index}-order"] = str(order.pk)
        payload.update(overrides)
        return payload

    def test_admin_change_form_shows_cancel_button_only_for_cancellable_orders(self):
        cancellable = self._create_order(status=OrderStatus.PROCESSING)
        shipped = self._create_order(status=OrderStatus.SHIPPED)

        eligible_response = self.client.get(
            reverse("admin:commerce_order_change", args=[cancellable.pk])
        )
        ineligible_response = self.client.get(
            reverse("admin:commerce_order_change", args=[shipped.pk])
        )

        self.assertContains(eligible_response, "_cancel_and_restore_stock")
        self.assertNotContains(ineligible_response, "_cancel_and_restore_stock")

    def test_admin_cancel_button_cancels_order_and_restores_stock(self):
        order = self._create_order(status=OrderStatus.CONFIRMED, quantity=3)

        response = self.client.post(
            reverse("admin:commerce_order_change", args=[order.pk]),
            self._build_admin_payload(order, _cancel_and_restore_stock="1"),
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.stock_restored_at)
        self.assertEqual(self.product.stock_qty, 5)

    def test_admin_rejects_manual_cancel_status_change(self):
        order = self._create_order(status=OrderStatus.NEW)

        response = self.client.post(
            reverse("admin:commerce_order_change", args=[order.pk]),
            self._build_admin_payload(order, status=OrderStatus.CANCELLED, _save="Save"),
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(
            response,
            "Use the &#x27;Cancel and restore stock&#x27; button to cancel this order.",
        )
        self.assertEqual(order.status, OrderStatus.NEW)


class CommerceAdminFormTests(TestCase):
    def setUp(self):
        Category.objects.all().delete()
        Product.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        self.category = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.product = Product.objects.create(
            category=self.category,
            name="Car Vacuum 53",
            slug="car-vacuum-53",
            sku="CV-53",
            short_description="Daily cleaning",
            description="Long description",
            price=Decimal("120.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )
        self.order = Order.objects.create(
            order_number="ORD-20260316-999999",
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            status=OrderStatus.DELIVERED,
            subtotal=Decimal("120.00"),
            total=Decimal("120.00"),
            first_name="Test",
            last_name="Buyer",
            email="buyer@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Saburtalo 1",
            note="",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=self.product.price,
            quantity=1,
            line_total=self.product.price,
            primary_image_snapshot=build_product_primary_image_snapshot(self.product),
        )

    def test_admin_form_rejects_invalid_backward_transition(self):
        admin_form_class = site._registry[Order].get_form(request=None, obj=self.order)
        form = admin_form_class(
            data={
                "payment_method": self.order.payment_method,
                "status": OrderStatus.PROCESSING,
                "first_name": self.order.first_name,
                "last_name": self.order.last_name,
                "email": self.order.email,
                "phone": self.order.phone,
                "city": self.order.city,
                "address_line": self.order.address_line,
                "note": self.order.note,
            },
            instance=self.order,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["status"][0],
            "Cannot change status from 'Delivered' to 'Processing'.",
        )
