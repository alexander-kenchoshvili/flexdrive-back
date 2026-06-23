import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import (
    Client,
    TestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import Category, Product, ProductImage, ProductStatus
from pages.models import ContentItem
from common.models import OutboundTask

from .images import build_product_primary_image_snapshot
from .legal import TermsAcceptanceSnapshot
from .meta_conversions import (
    MARKETING_CONSENT_HEADER,
    build_meta_purchase_event_id,
    build_meta_purchase_payload,
    send_meta_purchase_event,
)
from .payment_providers import PaymentProviderResponse
from .models import (
    BuyNowSession,
    Cart,
    CartItem,
    CheckoutAttempt,
    Order,
    OrderBuyerType,
    OrderCheckoutSource,
    OrderItem,
    OrderPaymentMethod,
    OrderPaymentStatus,
    OrderStatus,
    PaymentProvider,
    PaymentTransaction,
    PaymentTransactionAction,
    PaymentTransactionStatus,
    StockReservation,
    StockReservationItem,
    StockReservationStatus,
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
    StockReservationError,
    apply_payment_provider_response,
    authorize_payment,
    cancel_payment,
    cancel_order_and_restore_stock,
    capture_payment,
    complete_stock_reservation,
    create_payment_transaction,
    create_stock_reservation_from_buy_now_session,
    create_stock_reservation_from_cart,
    build_checkout_owner_fingerprint,
    build_checkout_request_fingerprint,
    create_order_from_buy_now_session,
    create_order_from_cart,
    expire_stock_reservations,
    get_available_stock_quantity,
    refund_payment,
    release_stock_reservation,
    transition_order_status,
    transition_order_payment_status,
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
        PaymentTransaction.objects.all().hard_delete()
        StockReservationItem.objects.all().delete()
        StockReservation.objects.all().delete()
        CheckoutAttempt.objects.all().delete()
        CartItem.objects.all().delete()
        Cart.objects.all().delete()
        OrderItem.objects.all().hard_delete()
        Order.objects.all().hard_delete()
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

    def _order_lookup_payload(self, *, order_number, phone="555123456"):
        return {
            "order_number": order_number,
            "phone": phone,
            "recaptcha_token": "test-recaptcha-token",
        }

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
            REMOTE_ADDR="203.0.113.15",
            HTTP_USER_AGENT="FlexDrive checkout test",
        )

        self.product.refresh_from_db()
        self.second_product.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(order.subtotal, Decimal("540.00"))
        self.assertEqual(order.total, Decimal("540.00"))
        self.assertIsNotNone(order.terms_accepted_at)
        self.assertEqual(order.terms_version, settings.TERMS_DOCUMENT_VERSION)
        self.assertEqual(len(order.terms_content_hash), 64)
        self.assertEqual(order.terms_url, f"{settings.FRONTEND_BASE_URL}/terms")
        self.assertEqual(order.terms_ip_address, "203.0.113.15")
        self.assertEqual(order.terms_user_agent, "FlexDrive checkout test")
        self.assertTrue(order.terms_content_snapshot["components"])
        self.assertTrue(order.order_number.startswith("ORD-"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(self.second_product.stock_qty, 1)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(response.data["payment_status"], OrderPaymentStatus.PENDING)
        self.assertEqual(response.data["items"][0]["product_name"], "Car Vacuum 53")
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")

    def test_cart_checkout_respects_other_owner_active_reservation(self):
        reserved_cart = Cart.objects.create(user=self.other_user)
        CartItem.objects.create(
            cart=reserved_cart,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=self.product.stock_qty,
        )
        create_stock_reservation_from_cart(
            cart=reserved_cart,
            user=self.other_user,
        )
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], CART_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(
            response.data["cart_issues"][0]["issue_type"],
            "out_of_stock",
        )
        self.assertEqual(
            response.data["cart_issues"][0]["available_quantity"],
            0,
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.product.stock_qty, 5)

    def test_cart_checkout_consumes_own_active_reservation(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        cart = Cart.objects.get(user=self.user)
        reservation = create_stock_reservation_from_cart(
            cart=cart,
            user=self.user,
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
        )

        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reservation.status, StockReservationStatus.COMPLETED)
        self.assertEqual(reservation.completed_order, Order.objects.get())
        self.assertIsNotNone(reservation.completed_at)
        self.assertEqual(self.product.stock_qty, 3)

    def test_cart_checkout_releases_stale_own_reservation(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        cart = Cart.objects.get(user=self.user)
        reservation = create_stock_reservation_from_cart(
            cart=cart,
            user=self.user,
        )
        cart_item = cart.items.get()
        cart_item.quantity = 2
        cart_item.save(update_fields=["quantity", "updated_at"])

        response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
        )

        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reservation.status, StockReservationStatus.RELEASED)
        self.assertIsNone(reservation.completed_order)
        self.assertIsNotNone(reservation.released_at)
        self.assertEqual(self.product.stock_qty, 3)

    def test_checkout_does_not_queue_purchase_before_cod_delivery(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            OutboundTask.objects.filter(task_type="meta_purchase").exists()
        )

    def test_cart_checkout_replays_same_order_for_same_idempotency_key(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        idempotency_key = str(uuid.uuid4())

        first_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        second_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )

        self.product.refresh_from_db()
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response["Idempotency-Replayed"], "true")
        self.assertEqual(
            second_response.data["public_token"],
            first_response.data["public_token"],
        )
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CheckoutAttempt.objects.count(), 1)
        self.assertEqual(self.product.stock_qty, 3)

    def test_cart_checkout_with_second_key_does_not_create_duplicate_order(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        first_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        second_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.product.refresh_from_db()
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(second_response.data["detail"]), "Cart is empty.")
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CheckoutAttempt.objects.count(), 1)
        self.assertEqual(self.product.stock_qty, 4)

    def test_cart_checkout_rejects_reused_key_with_different_payload(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        idempotency_key = str(uuid.uuid4())

        first_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        second_response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                **self._checkout_payload(),
                "city": "Batumi",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            second_response.data["code"],
            "checkout_idempotency_conflict",
        )
        self.assertEqual(Order.objects.count(), 1)

    def test_checkout_rejects_invalid_idempotency_key(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY="not-a-uuid",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data["idempotency_key"]),
            "Idempotency-Key must be a valid UUID.",
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_cors_preflight_allows_idempotency_key_header(self):
        response = self.client.options(
            reverse("commerce-order-checkout"),
            HTTP_ORIGIN="http://localhost:3000",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=(
                "content-type, idempotency-key, x-csrftoken"
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        allowed_headers = {
            header.strip().lower()
            for header in response["Access-Control-Allow-Headers"].split(",")
        }
        self.assertIn("idempotency-key", allowed_headers)

    def test_cart_checkout_replay_does_not_queue_purchase_event(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        idempotency_key = str(uuid.uuid4())

        self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )

        self.assertFalse(
            OutboundTask.objects.filter(task_type="meta_purchase").exists()
        )

    @override_settings(
        FRONTEND_BASE_URL="https://flexdrive.ge",
        META_CAPI_TEST_EVENT_CODE="TEST12345",
    )
    def test_meta_purchase_payload_uses_matching_event_id_and_hashed_customer_data(self):
        order = self._create_order(user=self.user, suffix=42)

        payload = build_meta_purchase_payload(order=order)
        event = payload["data"][0]

        self.assertEqual(payload["test_event_code"], "TEST12345")
        self.assertEqual(event["event_name"], "Purchase")
        self.assertEqual(event["event_id"], build_meta_purchase_event_id(order))
        self.assertEqual(
            event["event_source_url"],
            f"https://flexdrive.ge/checkout/success/{order.public_token}",
        )
        self.assertEqual(event["custom_data"]["currency"], "GEL")
        self.assertEqual(event["custom_data"]["value"], 120.0)
        self.assertEqual(event["custom_data"]["order_id"], order.order_number)
        self.assertEqual(event["custom_data"]["content_ids"], ["CV-53"])
        self.assertNotIn("buyer@example.com", str(payload))
        self.assertNotIn("555123456", str(payload))

    @override_settings(
        META_CAPI_ENABLED=True,
        META_PIXEL_ID="1020718363721235",
        META_CAPI_ACCESS_TOKEN="test-token",
        META_CAPI_TEST_EVENT_CODE="",
        META_CAPI_TIMEOUT_SECONDS=1,
    )
    @patch("commerce.meta_conversions.requests.post")
    def test_meta_purchase_event_requires_marketing_consent(self, requests_post):
        order = self._create_order(user=self.user, suffix=43)
        request = SimpleNamespace(COOKIES={}, META={})

        sent = send_meta_purchase_event(order=order, request=request)

        self.assertFalse(sent)
        requests_post.assert_not_called()

    @override_settings(
        META_CAPI_ENABLED=True,
        META_PIXEL_ID="1020718363721235",
        META_CAPI_ACCESS_TOKEN="test-token",
        META_CAPI_TEST_EVENT_CODE="",
        META_CAPI_TIMEOUT_SECONDS=1,
    )
    @patch("commerce.meta_conversions.requests.post")
    def test_meta_purchase_event_sends_with_marketing_consent(self, requests_post):
        order = self._create_order(user=self.user, suffix=44)
        request = SimpleNamespace(
            COOKIES={},
            META={"HTTP_X_FLEXDRIVE_MARKETING_CONSENT": "granted"},
            headers={MARKETING_CONSENT_HEADER: "granted"},
        )
        requests_post.return_value.raise_for_status.return_value = None

        sent = send_meta_purchase_event(order=order, request=request)

        self.assertTrue(sent)
        requests_post.assert_called_once()

    def test_checkout_stores_legal_entity_snapshot(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        payload = {
            **self._checkout_payload(),
            "buyer_type": OrderBuyerType.LEGAL_ENTITY,
            "company_name": "Flex Parts LLC",
            "company_identification_code": "123456789",
        }
        response = self.client.post(
            reverse("commerce-order-checkout"),
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        self.assertEqual(order.buyer_type, OrderBuyerType.LEGAL_ENTITY)
        self.assertEqual(order.company_name, "Flex Parts LLC")
        self.assertEqual(order.company_identification_code, "123456789")
        self.assertEqual(response.data["buyer_type"], OrderBuyerType.LEGAL_ENTITY)
        self.assertEqual(response.data["company_name"], "Flex Parts LLC")

    def test_legal_entity_checkout_requires_company_fields(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )

        response = self.client.post(
            reverse("commerce-order-checkout"),
            {
                **self._checkout_payload(),
                "buyer_type": OrderBuyerType.LEGAL_ENTITY,
                "company_identification_code": "123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("company_name", response.data)
        self.assertIn("company_identification_code", response.data)
        self.assertEqual(Order.objects.count(), 0)

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
        self.assertEqual(order.payment_status, OrderPaymentStatus.PENDING)
        self.assertIsNotNone(order.terms_accepted_at)
        self.assertEqual(order.terms_version, settings.TERMS_DOCUMENT_VERSION)
        self.assertEqual(len(order.terms_content_hash), 64)
        self.assertTrue(order.terms_content_snapshot["components"])
        self.assertEqual(order.total, Decimal("240.00"))
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(self.product.stock_qty, 3)
        self.assertEqual(BuyNowSession.objects.count(), 0)
        self.assertEqual(response.data["payment_status"], OrderPaymentStatus.PENDING)
        self.assertIn(BUY_NOW_TOKEN_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value, "")

    def test_buy_now_checkout_does_not_queue_purchase_before_cod_delivery(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            OutboundTask.objects.filter(task_type="meta_purchase").exists()
        )

    def test_buy_now_checkout_replays_order_after_session_is_consumed(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        idempotency_key = str(uuid.uuid4())
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        first_response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token
        second_response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )

        self.product.refresh_from_db()
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response["Idempotency-Replayed"], "true")
        self.assertEqual(
            second_response.data["public_token"],
            first_response.data["public_token"],
        )
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(BuyNowSession.objects.count(), 0)
        self.assertEqual(self.product.stock_qty, 3)

    def test_buy_now_checkout_stores_legal_entity_snapshot(self):
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        guest_token = create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = guest_token

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            {
                **self._checkout_payload(),
                "buyer_type": OrderBuyerType.LEGAL_ENTITY,
                "company_name": "Auto Mirror LLC",
                "company_identification_code": "987654321",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        self.assertEqual(order.checkout_source, OrderCheckoutSource.BUY_NOW)
        self.assertEqual(order.buyer_type, OrderBuyerType.LEGAL_ENTITY)
        self.assertEqual(order.company_name, "Auto Mirror LLC")
        self.assertEqual(order.company_identification_code, "987654321")

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

    def test_checkout_terms_hash_tracks_current_cms_content(self):
        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        first_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        first_order = Order.objects.get(public_token=first_response.data["public_token"])

        terms_item = (
            ContentItem.objects.filter(content__name="terms_sections")
            .order_by("position", "id")
            .first()
        )
        self.assertIsNotNone(terms_item)
        terms_item.description = f"{terms_item.description or ''} Updated terms."
        terms_item.save(update_fields=["description", "updated_at"])

        self.client.post(
            reverse("commerce-cart-item-list"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        second_response = self.client.post(
            reverse("commerce-order-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        second_order = Order.objects.get(public_token=second_response.data["public_token"])
        self.assertNotEqual(
            second_order.terms_content_hash,
            first_order.terms_content_hash,
        )

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

    def test_buy_now_checkout_respects_other_owner_active_reservation(self):
        reserved_cart = Cart.objects.create(user=self.other_user)
        CartItem.objects.create(
            cart=reserved_cart,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=self.product.stock_qty,
        )
        create_stock_reservation_from_cart(
            cart=reserved_cart,
            user=self.other_user,
        )
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 1},
            format="json",
        )
        self.client.cookies[BUY_NOW_TOKEN_COOKIE_NAME] = (
            create_response.cookies[BUY_NOW_TOKEN_COOKIE_NAME].value
        )

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        self.product.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], BUY_NOW_AVAILABILITY_CHANGED_CODE)
        self.assertEqual(
            response.data["buy_now_issues"][0]["issue_type"],
            "out_of_stock",
        )
        self.assertEqual(
            response.data["buy_now_issues"][0]["available_quantity"],
            0,
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.product.stock_qty, 5)

    def test_buy_now_checkout_consumes_own_active_reservation(self):
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(
            reverse("commerce-buy-now-session"),
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        session = BuyNowSession.objects.get(user=self.user)
        reservation = create_stock_reservation_from_buy_now_session(
            session=session,
            user=self.user,
        )

        response = self.client.post(
            reverse("commerce-buy-now-checkout"),
            self._checkout_payload(),
            format="json",
        )

        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(create_response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reservation.status, StockReservationStatus.COMPLETED)
        self.assertEqual(reservation.completed_order, Order.objects.get())
        self.assertIsNotNone(reservation.completed_at)
        self.assertEqual(self.product.stock_qty, 3)

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
        self.assertEqual(response.data["payment_status"], OrderPaymentStatus.PENDING)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")
        for private_key in (
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "address_line",
            "note",
            "company_name",
            "company_identification_code",
        ):
            self.assertNotIn(private_key, response.data)

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

    def test_order_lookup_returns_safe_summary_for_matching_order_number_and_phone(self):
        order = self._create_order(user=None, suffix=70, status=OrderStatus.SHIPPED)

        response = self.client.post(
            reverse("commerce-order-lookup"),
            self._order_lookup_payload(order_number=order.order_number),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_number"], order.order_number)
        self.assertEqual(response.data["status"], OrderStatus.SHIPPED)
        self.assertEqual(response.data["payment_status"], OrderPaymentStatus.PENDING)
        self.assertEqual(response.data["payment_method"], OrderPaymentMethod.CASH_ON_DELIVERY)
        self.assertEqual(response.data["checkout_source"], OrderCheckoutSource.CART)
        self.assertEqual(response.data["total"], "120.00")
        self.assertEqual(response.data["item_count"], 1)
        self.assertEqual(response.data["total_quantity"], 1)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(
            set(response.data["items"][0].keys()),
            {"product_name", "sku", "unit_price", "quantity", "line_total", "primary_image"},
        )
        self.assertEqual(response.data["items"][0]["primary_image"]["alt_text"], "Vacuum image")
        for private_key in ("public_token", "email", "phone", "city", "address_line", "note"):
            self.assertNotIn(private_key, response.data)

    def test_order_lookup_matches_normalized_georgian_phone_number(self):
        order = self._create_order(user=None, suffix=71, status=OrderStatus.NEW)
        order.phone = "+995 598-784-500"
        order.save(update_fields=["phone", "updated_at"])

        response = self.client.post(
            reverse("commerce-order-lookup"),
            self._order_lookup_payload(order_number=order.order_number, phone="598784500"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_number"], order.order_number)

    def test_order_lookup_returns_generic_404_for_wrong_phone(self):
        order = self._create_order(user=None, suffix=72, status=OrderStatus.NEW)

        response = self.client.post(
            reverse("commerce-order-lookup"),
            self._order_lookup_payload(order_number=order.order_number, phone="555000000"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["detail"],
            "შეკვეთა ვერ მოიძებნა. გადაამოწმეთ შეკვეთის ნომერი და ტელეფონის ნომერი.",
        )

    def test_order_lookup_returns_generic_404_for_unknown_order_number(self):
        response = self.client.post(
            reverse("commerce-order-lookup"),
            self._order_lookup_payload(order_number="ORD-20260515-999999"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["detail"],
            "შეკვეთა ვერ მოიძებნა. გადაამოწმეთ შეკვეთის ნომერი და ტელეფონის ნომერი.",
        )

    def test_order_lookup_rejects_request_when_recaptcha_fails(self):
        order = self._create_order(user=None, suffix=74, status=OrderStatus.NEW)

        with patch("commerce.views.validate_recaptcha", return_value=False):
            response = self.client.post(
                reverse("commerce-order-lookup"),
                self._order_lookup_payload(order_number=order.order_number),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "უსაფრთხოების შემოწმება ვერ გაიარა.")

    def test_order_lookup_allows_authenticated_user_without_owner_filter(self):
        order = self._create_order(user=self.other_user, suffix=73, status=OrderStatus.DELIVERED)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            reverse("commerce-order-lookup"),
            self._order_lookup_payload(order_number=order.order_number),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_number"], order.order_number)
        self.assertEqual(response.data["status"], OrderStatus.DELIVERED)

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
        self.assertEqual(response.data["results"][0]["payment_status"], OrderPaymentStatus.PENDING)

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
        self.assertEqual(response.data["payment_status"], OrderPaymentStatus.PENDING)
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
        PaymentTransaction.objects.all().hard_delete()
        StockReservationItem.objects.all().delete()
        StockReservation.objects.all().delete()
        Category.objects.all().delete()
        Product.objects.all().delete()
        OrderItem.objects.all().hard_delete()
        Order.objects.all().hard_delete()
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
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )

    def _create_order(
        self,
        *,
        status=OrderStatus.NEW,
        quantity=3,
        product=None,
        payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
        payment_status=OrderPaymentStatus.PENDING,
    ):
        order = Order.objects.create(
            order_number=f"ORD-20260316-{Order.objects.count() + 1:06d}",
            payment_method=payment_method,
            payment_status=payment_status,
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

    def _create_cart(self, *, user, quantity=1, product=None):
        cart = Cart.objects.create(user=user)
        selected_product = product if product is not None else self.product
        CartItem.objects.create(
            cart=cart,
            product=selected_product,
            unit_price_snapshot=selected_product.price,
            quantity=quantity,
        )
        return cart

    def assert_database_rejects(self, operation):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                operation()

    def test_database_rejects_zero_checkout_quantities(self):
        cart = self._create_cart(user=self.user, quantity=1)
        cart_item = cart.items.get()
        buy_now_session = BuyNowSession.objects.create(
            user=self.user,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=1,
        )

        self.assert_database_rejects(
            lambda: CartItem.objects.filter(pk=cart_item.pk).update(quantity=0)
        )
        self.assert_database_rejects(
            lambda: CartItem.objects.filter(pk=cart_item.pk).update(
                unit_price_snapshot=Decimal("-0.01")
            )
        )
        self.assert_database_rejects(
            lambda: BuyNowSession.objects.filter(
                pk=buy_now_session.pk
            ).update(quantity=0)
        )
        self.assert_database_rejects(
            lambda: BuyNowSession.objects.filter(
                pk=buy_now_session.pk
            ).update(unit_price_snapshot=Decimal("-0.01"))
        )

    def test_database_rejects_negative_order_amounts_and_zero_item_quantity(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)
        order_item = order.items.get()

        self.assert_database_rejects(
            lambda: Order.objects.filter(pk=order.pk).update(
                subtotal=Decimal("-0.01")
            )
        )
        self.assert_database_rejects(
            lambda: Order.objects.filter(pk=order.pk).update(
                total=Decimal("-0.01")
            )
        )
        self.assert_database_rejects(
            lambda: OrderItem.objects.filter(pk=order_item.pk).update(
                quantity=0
            )
        )
        self.assert_database_rejects(
            lambda: OrderItem.objects.filter(pk=order_item.pk).update(
                unit_price=Decimal("-0.01")
            )
        )
        self.assert_database_rejects(
            lambda: OrderItem.objects.filter(pk=order_item.pk).update(
                line_total=Decimal("-0.01")
            )
        )

    def test_database_rejects_invalid_reservation_item_values(self):
        cart = self._create_cart(user=self.user, quantity=1)
        reservation = create_stock_reservation_from_cart(
            cart=cart,
            user=self.user,
        )
        reservation_item = reservation.items.get()

        self.assert_database_rejects(
            lambda: StockReservationItem.objects.filter(
                pk=reservation_item.pk
            ).update(quantity=0)
        )
        self.assert_database_rejects(
            lambda: StockReservationItem.objects.filter(
                pk=reservation_item.pk
            ).update(unit_price_snapshot=Decimal("-0.01"))
        )

    def test_database_rejects_negative_payment_amount(self):
        payment_transaction = create_payment_transaction(
            order=self._create_order(status=OrderStatus.NEW, quantity=1),
            amount=Decimal("120.00"),
        )

        self.assert_database_rejects(
            lambda: PaymentTransaction.objects.filter(
                pk=payment_transaction.pk
            ).update(amount=Decimal("-0.01"))
        )

    def test_database_rejects_zero_payment_amount(self):
        payment_transaction = create_payment_transaction(
            order=self._create_order(status=OrderStatus.NEW, quantity=1),
            amount=Decimal("120.00"),
        )

        self.assert_database_rejects(
            lambda: PaymentTransaction.objects.filter(
                pk=payment_transaction.pk
            ).update(amount=Decimal("0.00"))
        )

    def test_database_rejects_payment_without_order_or_reservation(self):
        self.assert_database_rejects(
            lambda: PaymentTransaction.objects.create(
                amount=Decimal("1.00"),
            )
        )

    def test_database_rejects_duplicate_provider_action_id(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)
        create_payment_transaction(
            order=order,
            amount=order.total,
            provider_action_id="provider-action-1",
        )

        self.assert_database_rejects(
            lambda: create_payment_transaction(
                order=order,
                amount=order.total,
                provider_action_id="provider-action-1",
            )
        )

    def test_database_rejects_duplicate_payment_idempotency_key(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)
        idempotency_key = uuid.uuid4()
        create_payment_transaction(
            order=order,
            amount=order.total,
            idempotency_key=idempotency_key,
        )

        self.assert_database_rejects(
            lambda: create_payment_transaction(
                order=order,
                amount=order.total,
                idempotency_key=idempotency_key,
            )
        )

    def test_database_allows_same_provider_order_id_for_sale_and_refund(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PAID,
        )

        PaymentTransaction.objects.create(
            order=order,
            provider=PaymentProvider.BOG,
            payment_method=OrderPaymentMethod.CARD,
            action=PaymentTransactionAction.SALE,
            status=PaymentTransactionStatus.PAID,
            amount=order.total,
            currency="GEL",
            provider_order_id="bog-shared-order-1",
            provider_transaction_id="bog-sale-transaction-1",
        )
        PaymentTransaction.objects.create(
            order=order,
            provider=PaymentProvider.BOG,
            payment_method=OrderPaymentMethod.CARD,
            action=PaymentTransactionAction.REFUND,
            status=PaymentTransactionStatus.REFUND_PENDING,
            amount=order.total,
            currency="GEL",
            provider_order_id="bog-shared-order-1",
            provider_action_id="bog-refund-action-1",
        )

        self.assertEqual(
            PaymentTransaction.objects.filter(
                provider=PaymentProvider.BOG,
                provider_order_id="bog-shared-order-1",
            ).count(),
            2,
        )

    def test_order_instance_and_queryset_hard_delete_are_disabled(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Hard deletion is disabled for orders. Cancel the order instead.",
        ):
            order.delete()

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Hard deletion is disabled for financial records.",
        ):
            Order.objects.filter(pk=order.pk).delete()

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_order_database_relations_protect_financial_history(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)

        with self.assertRaises(ProtectedError):
            Order.objects.filter(pk=order.pk).hard_delete()

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(order.items.count(), 1)

    def test_order_item_hard_delete_is_disabled(self):
        order_item = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
        ).items.get()

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Hard deletion is disabled for order items.",
        ):
            order_item.delete()

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Hard deletion is disabled for financial records.",
        ):
            OrderItem.objects.filter(pk=order_item.pk).delete()

        self.assertTrue(OrderItem.objects.filter(pk=order_item.pk).exists())

    def test_payment_transaction_hard_delete_is_disabled(self):
        payment_transaction = create_payment_transaction(
            order=self._create_order(status=OrderStatus.NEW, quantity=1),
            amount=Decimal("120.00"),
        )

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Hard deletion is disabled for payment transactions.",
        ):
            payment_transaction.delete()

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Hard deletion is disabled for financial records.",
        ):
            PaymentTransaction.objects.filter(
                pk=payment_transaction.pk
            ).delete()

        self.assertTrue(
            PaymentTransaction.objects.filter(pk=payment_transaction.pk).exists()
        )

    def test_payment_transaction_protects_order_and_reservation(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)
        cart = self._create_cart(user=self.user, quantity=1)
        reservation = create_stock_reservation_from_cart(
            cart=cart,
            user=self.user,
        )
        create_payment_transaction(
            order=order,
            reservation=reservation,
            amount=order.total,
        )
        order.items.all().hard_delete()
        reservation.items.all().delete()

        with self.assertRaises(ProtectedError):
            Order.objects.filter(pk=order.pk).hard_delete()
        with self.assertRaises(ProtectedError):
            reservation.delete()

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertTrue(StockReservation.objects.filter(pk=reservation.pk).exists())

    def test_completed_reservation_protects_order_history(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)
        cart = self._create_cart(user=self.user, quantity=1)
        reservation = create_stock_reservation_from_cart(
            cart=cart,
            user=self.user,
        )
        complete_stock_reservation(reservation=reservation, order=order)
        order.items.all().hard_delete()

        with self.assertRaises(ProtectedError):
            Order.objects.filter(pk=order.pk).hard_delete()

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_cart_stock_reservation_creates_active_items_without_reducing_stock(self):
        cart = self._create_cart(user=self.user, quantity=1)

        reservation = create_stock_reservation_from_cart(
            cart=cart,
            user=self.user,
            ttl_seconds=900,
        )

        self.product.refresh_from_db()
        reservation_item = reservation.items.get()
        self.assertEqual(reservation.status, StockReservationStatus.ACTIVE)
        self.assertEqual(reservation.source, OrderCheckoutSource.CART)
        self.assertEqual(reservation_item.product, self.product)
        self.assertEqual(reservation_item.quantity, 1)
        self.assertEqual(reservation_item.unit_price_snapshot, self.product.price)
        self.assertEqual(self.product.stock_qty, 2)
        self.assertEqual(get_available_stock_quantity(product=self.product), 1)

    def test_cart_stock_reservation_blocks_other_owner_when_reserved_stock_is_exhausted(self):
        first_cart = self._create_cart(user=self.user, quantity=2)
        second_cart = self._create_cart(user=self.other_user, quantity=1)
        create_stock_reservation_from_cart(cart=first_cart, user=self.user)

        with self.assertRaises(StockReservationError) as context:
            create_stock_reservation_from_cart(cart=second_cart, user=self.other_user)

        self.assertEqual(context.exception.detail, CHECKOUT_PRODUCT_UNAVAILABLE_DETAIL)
        self.assertEqual(context.exception.issues[0]["issue_type"], "out_of_stock")
        self.assertEqual(context.exception.issues[0]["available_quantity"], 0)

    def test_replacing_same_owner_cart_reservation_releases_previous_reservation(self):
        cart = self._create_cart(user=self.user, quantity=1)
        first_reservation = create_stock_reservation_from_cart(cart=cart, user=self.user)
        cart_item = cart.items.get()
        cart_item.quantity = 2
        cart_item.save(update_fields=["quantity", "updated_at"])

        second_reservation = create_stock_reservation_from_cart(cart=cart, user=self.user)

        first_reservation.refresh_from_db()
        self.assertEqual(first_reservation.status, StockReservationStatus.RELEASED)
        self.assertEqual(second_reservation.status, StockReservationStatus.ACTIVE)
        self.assertEqual(second_reservation.items.get().quantity, 2)
        self.assertEqual(get_available_stock_quantity(product=self.product), 0)

    def test_expired_stock_reservation_no_longer_counts_against_available_stock(self):
        cart = self._create_cart(user=self.user, quantity=2)
        reservation = create_stock_reservation_from_cart(cart=cart, user=self.user)
        reservation.expires_at = timezone.now() - timedelta(minutes=1)
        reservation.save(update_fields=["expires_at", "updated_at"])

        expired_count = expire_stock_reservations()

        reservation.refresh_from_db()
        self.assertEqual(expired_count, 1)
        self.assertEqual(reservation.status, StockReservationStatus.EXPIRED)
        self.assertEqual(get_available_stock_quantity(product=self.product), 2)

    def test_release_stock_reservation_frees_reserved_quantity(self):
        cart = self._create_cart(user=self.user, quantity=2)
        reservation = create_stock_reservation_from_cart(cart=cart, user=self.user)

        release_stock_reservation(reservation)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, StockReservationStatus.RELEASED)
        self.assertIsNotNone(reservation.released_at)
        self.assertEqual(get_available_stock_quantity(product=self.product), 2)

    def test_complete_stock_reservation_links_order(self):
        cart = self._create_cart(user=self.user, quantity=1)
        reservation = create_stock_reservation_from_cart(cart=cart, user=self.user)
        order = self._create_order(status=OrderStatus.NEW, quantity=1)

        complete_stock_reservation(reservation=reservation, order=order)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, StockReservationStatus.COMPLETED)
        self.assertEqual(reservation.completed_order, order)
        self.assertIsNotNone(reservation.completed_at)

    def test_expired_stock_reservation_cannot_be_completed(self):
        cart = self._create_cart(user=self.user, quantity=1)
        reservation = create_stock_reservation_from_cart(cart=cart, user=self.user)
        reservation.expires_at = timezone.now() - timedelta(seconds=1)
        reservation.save(update_fields=["expires_at", "updated_at"])
        order = self._create_order(status=OrderStatus.NEW, quantity=1)

        with self.assertRaisesMessage(
            StockReservationError,
            "Expired reservations cannot be completed.",
        ):
            complete_stock_reservation(reservation=reservation, order=order)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, StockReservationStatus.ACTIVE)
        self.assertIsNone(reservation.completed_order)

    def test_buy_now_stock_reservation_uses_session_snapshot(self):
        session = BuyNowSession.objects.create(
            user=self.user,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=1,
        )

        reservation = create_stock_reservation_from_buy_now_session(session=session)

        self.assertEqual(reservation.source, OrderCheckoutSource.BUY_NOW)
        self.assertEqual(reservation.items.get().quantity, 1)

    def test_mock_authorize_and_capture_create_transactions_and_update_order_payment_status(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )

        authorized = authorize_payment(order=order, amount=order.total)
        order.refresh_from_db()
        captured = capture_payment(order=order, amount=order.total)
        order.refresh_from_db()

        self.assertEqual(authorized.provider, PaymentProvider.MOCK)
        self.assertEqual(authorized.action, PaymentTransactionAction.AUTHORIZE)
        self.assertEqual(authorized.status, PaymentTransactionStatus.AUTHORIZED)
        self.assertTrue(authorized.provider_transaction_id.startswith("mock-authorize-"))
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(captured.action, PaymentTransactionAction.CAPTURE)
        self.assertEqual(captured.status, PaymentTransactionStatus.PAID)

    def test_mock_refund_updates_order_payment_status(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        authorize_payment(order=order, amount=order.total)
        capture_payment(order=order, amount=order.total)

        refunded = refund_payment(order=order, amount=order.total)
        order.refresh_from_db()

        self.assertEqual(refunded.status, PaymentTransactionStatus.REFUNDED)
        self.assertEqual(order.payment_status, OrderPaymentStatus.REFUNDED)

    def test_stale_failed_response_cannot_regress_paid_order(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        authorize_payment(order=order, amount=order.total)
        capture_payment(order=order, amount=order.total)
        stale_transaction = create_payment_transaction(
            order=order,
            amount=order.total,
            action=PaymentTransactionAction.AUTHORIZE,
        )

        apply_payment_provider_response(
            stale_transaction,
            PaymentProviderResponse(
                status=PaymentTransactionStatus.FAILED,
                provider_transaction_id="stale-failed-1",
                provider_reference={"event": "stale"},
                error_code="declined",
                error_message="Late failure",
            ),
        )

        order.refresh_from_db()
        stale_transaction.refresh_from_db()
        self.assertEqual(stale_transaction.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)

    def test_refunded_order_is_terminal_for_late_paid_response(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        authorize_payment(order=order, amount=order.total)
        capture_payment(order=order, amount=order.total)
        refund_payment(order=order, amount=order.total)
        stale_transaction = create_payment_transaction(
            order=order,
            amount=order.total,
            action=PaymentTransactionAction.CAPTURE,
        )

        apply_payment_provider_response(
            stale_transaction,
            PaymentProviderResponse(
                status=PaymentTransactionStatus.PAID,
                provider_transaction_id="stale-paid-after-refund-1",
                provider_reference={"event": "stale"},
            ),
        )

        order.refresh_from_db()
        self.assertEqual(order.payment_status, OrderPaymentStatus.REFUNDED)

    def test_duplicate_provider_response_reuses_existing_transaction(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        first_transaction = create_payment_transaction(
            order=order,
            amount=order.total,
            action=PaymentTransactionAction.CAPTURE,
        )
        response = PaymentProviderResponse(
            status=PaymentTransactionStatus.PAID,
            provider_transaction_id="provider-payment-1",
            provider_reference={"event": "paid"},
        )
        applied_transaction = apply_payment_provider_response(
            first_transaction,
            response,
        )
        duplicate_transaction = create_payment_transaction(
            order=order,
            amount=order.total,
            action=PaymentTransactionAction.CAPTURE,
        )

        replayed_transaction = apply_payment_provider_response(
            duplicate_transaction,
            response,
        )

        order.refresh_from_db()
        duplicate_transaction.refresh_from_db()
        self.assertEqual(replayed_transaction.pk, applied_transaction.pk)
        self.assertEqual(PaymentTransaction.objects.count(), 2)
        self.assertEqual(
            duplicate_transaction.status,
            PaymentTransactionStatus.CANCELLED,
        )
        self.assertEqual(
            duplicate_transaction.error_code,
            "duplicate_provider_response",
        )
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)

    def test_provider_order_id_can_be_shared_by_payment_and_refund_actions(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )

        payment = create_payment_transaction(
            order=order,
            amount=order.total,
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.SALE,
            provider_order_id="bog-order-1",
            checkout_snapshot={"source": "cart"},
        )
        refund = create_payment_transaction(
            order=order,
            amount=order.total,
            provider=PaymentProvider.BOG,
            action=PaymentTransactionAction.REFUND,
            provider_order_id="bog-order-1",
            provider_action_id="bog-refund-action-1",
        )

        self.assertNotEqual(payment.pk, refund.pk)
        self.assertEqual(payment.provider_order_id, refund.provider_order_id)
        self.assertNotEqual(payment.public_token, refund.public_token)
        self.assertNotEqual(payment.idempotency_key, refund.idempotency_key)
        self.assertEqual(payment.checkout_snapshot["source"], "cart")

    def test_second_active_payment_attempt_is_rejected(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        authorize_payment(order=order, amount=order.total)

        with self.assertRaisesMessage(
            DjangoValidationError,
            "An active payment attempt already exists for this checkout.",
        ):
            authorize_payment(order=order, amount=order.total)

    def test_successful_payment_cancel_allows_a_new_attempt(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        authorize_payment(order=order, amount=order.total)
        cancel_payment(order=order, amount=order.total)

        retried = authorize_payment(order=order, amount=order.total)

        order.refresh_from_db()
        self.assertEqual(
            retried.status,
            PaymentTransactionStatus.AUTHORIZED,
        )
        self.assertEqual(order.payment_status, OrderPaymentStatus.AUTHORIZED)

    def test_capture_requires_matching_authorized_transaction(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.AUTHORIZED,
        )

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Capture requires a matching authorized payment transaction.",
        ):
            capture_payment(order=order, amount=order.total)

    def test_partial_refund_is_rejected_until_partial_state_is_supported(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        authorize_payment(order=order, amount=order.total)
        capture_payment(order=order, amount=order.total)

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Partial refunds are not enabled for this payment flow.",
        ):
            refund_payment(order=order, amount=Decimal("10.00"))

    def test_older_failed_response_cannot_regress_newer_authorized_transaction(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
        )
        older_transaction = create_payment_transaction(
            order=order,
            amount=order.total,
            action=PaymentTransactionAction.AUTHORIZE,
        )
        newer_transaction = create_payment_transaction(
            order=order,
            amount=order.total,
            action=PaymentTransactionAction.AUTHORIZE,
            status=PaymentTransactionStatus.AUTHORIZED,
        )
        order.payment_status = OrderPaymentStatus.AUTHORIZED
        order.save(update_fields=["payment_status", "updated_at"])

        apply_payment_provider_response(
            older_transaction,
            PaymentProviderResponse(
                status=PaymentTransactionStatus.FAILED,
                provider_transaction_id="older-failed-transaction",
                provider_reference={"event": "late_failure"},
            ),
        )

        order.refresh_from_db()
        newer_transaction.refresh_from_db()
        self.assertEqual(
            newer_transaction.status,
            PaymentTransactionStatus.AUTHORIZED,
        )
        self.assertEqual(order.payment_status, OrderPaymentStatus.AUTHORIZED)

    def test_unpaid_card_order_cannot_move_to_processing(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PENDING,
        )

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Cannot change status from 'New' to 'Processing'.",
        ):
            transition_order_status(order, OrderStatus.PROCESSING)

    def test_paid_card_order_requires_refund_flow_before_cancellation(self):
        order = self._create_order(
            status=OrderStatus.NEW,
            quantity=1,
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PAID,
        )

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Authorized or paid card orders require the payment refund/cancel flow.",
        ):
            cancel_order_and_restore_stock(order)

    def test_payment_status_transition_rejects_paid_to_failed(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=1)
        order.payment_status = OrderPaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])

        with self.assertRaisesMessage(
            DjangoValidationError,
            "Cannot change payment status from 'Paid' to 'Failed'.",
        ):
            transition_order_payment_status(
                order,
                OrderPaymentStatus.FAILED,
            )

        order.refresh_from_db()
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)

    def test_cancel_order_and_restore_stock_updates_status_and_stock(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=3)

        cancel_order_and_restore_stock(order)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.stock_restored_at)
        self.assertEqual(self.product.stock_qty, 5)

    def test_cancel_order_and_restore_stock_aggregates_duplicate_product_items(self):
        order = self._create_order(status=OrderStatus.NEW, quantity=2)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=self.product.price,
            quantity=3,
            line_total=self.product.price * 3,
            primary_image_snapshot=build_product_primary_image_snapshot(
                self.product
            ),
        )

        cancel_order_and_restore_stock(order)

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 7)
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.stock_restored_at)

    def test_cancel_order_and_restore_stock_restores_multiple_products(self):
        second_product = Product.objects.create(
            category=self.category,
            name="Second Product",
            slug="second-product",
            sku="SECOND-1",
            price=Decimal("80.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        order = self._create_order(status=OrderStatus.PROCESSING, quantity=2)
        OrderItem.objects.create(
            order=order,
            product=second_product,
            product_name=second_product.name,
            sku=second_product.sku,
            unit_price=second_product.price,
            quantity=3,
            line_total=second_product.price * 3,
            primary_image_snapshot=build_product_primary_image_snapshot(
                second_product
            ),
        )

        cancel_order_and_restore_stock(order)

        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 4)
        self.assertEqual(second_product.stock_qty, 7)

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

    @override_settings(
        META_CAPI_ENABLED=True,
        META_PIXEL_ID="pixel-id",
        META_CAPI_ACCESS_TOKEN="access-token",
    )
    @patch("commerce.services.send_meta_purchase_event", return_value=True)
    def test_cod_purchase_is_sent_when_order_is_delivered(self, send_meta_event):
        order = self._create_order(status=OrderStatus.SHIPPED)
        order.marketing_consent = True
        order.save(update_fields=["marketing_consent", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            transition_order_status(order, OrderStatus.DELIVERED)

        send_meta_event.assert_called_once()
        self.assertEqual(send_meta_event.call_args.kwargs["order"].pk, order.pk)

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


class PaymentProviderTransactionBoundaryTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.category = Category.objects.create(
            name="Payment boundary",
            slug="payment-boundary",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Payment Boundary Product",
            slug="payment-boundary-product",
            sku="PAYMENT-BOUNDARY-1",
            price=Decimal("100.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        self.order = Order.objects.create(
            order_number="ORD-PAYMENT-BOUNDARY",
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PENDING,
            status=OrderStatus.NEW,
            subtotal=self.product.price,
            total=self.product.price,
            first_name="Payment",
            last_name="Boundary",
            email="payment-boundary@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Payment Street 1",
            note="",
        )

    @patch("commerce.services.get_provider_method_for_action")
    def test_provider_call_runs_after_pending_transaction_is_committed(
        self,
        get_provider_method_for_action,
    ):
        def provider_call(*, transaction):
            self.assertFalse(connection.in_atomic_block)
            persisted = PaymentTransaction.objects.get(pk=transaction.pk)
            self.assertEqual(persisted.status, PaymentTransactionStatus.PENDING)
            return PaymentProviderResponse(
                status=PaymentTransactionStatus.AUTHORIZED,
                provider_transaction_id="provider-authorized-boundary-1",
                provider_reference={"result": "authorized"},
            )

        get_provider_method_for_action.return_value = provider_call

        payment_transaction = authorize_payment(
            order=self.order,
            amount=self.order.total,
        )

        self.assertEqual(
            payment_transaction.status,
            PaymentTransactionStatus.AUTHORIZED,
        )

    @patch("commerce.services.get_provider_method_for_action")
    def test_provider_exception_keeps_pending_transaction_for_reconciliation(
        self,
        get_provider_method_for_action,
    ):
        def provider_call(*, transaction):
            self.assertFalse(connection.in_atomic_block)
            raise TimeoutError("Provider timed out")

        get_provider_method_for_action.return_value = provider_call

        with self.assertRaisesMessage(TimeoutError, "Provider timed out"):
            authorize_payment(
                order=self.order,
                amount=self.order.total,
            )

        payment_transaction = PaymentTransaction.objects.get()
        self.assertEqual(
            payment_transaction.status,
            PaymentTransactionStatus.PENDING,
        )
        self.assertEqual(
            payment_transaction.error_code,
            "provider_exception",
        )
        self.assertEqual(
            payment_transaction.error_message,
            "Provider timed out",
        )

    @patch("commerce.services.apply_payment_provider_response")
    @patch("commerce.services.get_provider_method_for_action")
    def test_response_apply_exception_keeps_pending_transaction_for_reconciliation(
        self,
        get_provider_method_for_action,
        apply_payment_provider_response,
    ):
        get_provider_method_for_action.return_value = lambda *, transaction: (
            PaymentProviderResponse(
                status=PaymentTransactionStatus.AUTHORIZED,
                provider_transaction_id="provider-authorized-apply-failure-1",
                provider_reference={"result": "authorized"},
            )
        )
        apply_payment_provider_response.side_effect = RuntimeError(
            "Database response apply failed"
        )

        with self.assertRaisesMessage(
            RuntimeError,
            "Database response apply failed",
        ):
            authorize_payment(
                order=self.order,
                amount=self.order.total,
            )

        payment_transaction = PaymentTransaction.objects.get()
        self.assertEqual(
            payment_transaction.status,
            PaymentTransactionStatus.PENDING,
        )
        self.assertEqual(
            payment_transaction.error_code,
            "provider_response_apply_exception",
        )


@skipUnlessDBFeature("has_select_for_update")
class PaymentAttemptConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.order = Order.objects.create(
            order_number="ORD-PAYMENT-ATTEMPT-RACE-1",
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PENDING,
            status=OrderStatus.NEW,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            first_name="Payment",
            last_name="Attempt Race",
            email="payment-attempt-race@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Payment Street 2",
            note="",
        )

    def _authorize(self, *, barrier):
        close_old_connections()
        try:
            order = Order.objects.get(pk=self.order.pk)
            barrier.wait(timeout=10)
            payment_transaction = authorize_payment(
                order=order,
                amount=order.total,
            )
            return ("success", payment_transaction.pk)
        except Exception as error:
            return ("error", type(error).__name__, str(error))
        finally:
            close_old_connections()

    def test_parallel_payment_starts_create_one_active_attempt(self):
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: self._authorize(barrier=barrier),
                    range(2),
                )
            )

        self.order.refresh_from_db()
        self.assertEqual(
            sorted(result[0] for result in results),
            ["error", "success"],
        )
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(
            self.order.payment_status,
            OrderPaymentStatus.AUTHORIZED,
        )


@skipUnlessDBFeature("has_select_for_update")
class CheckoutConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="concurrent-buyer@example.com",
            email="concurrent-buyer@example.com",
            password="Password123!",
            is_active=True,
        )
        self.category = Category.objects.create(
            name="Concurrency",
            slug="concurrency",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Concurrent Product",
            slug="concurrent-product",
            sku="CONCURRENT-1",
            price=Decimal("100.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )
        self.cart = Cart.objects.create(user=self.user, is_active=True)
        CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=1,
        )
        self.validated_data = {
            "buyer_type": OrderBuyerType.INDIVIDUAL,
            "company_name": "",
            "company_identification_code": "",
            "first_name": "Concurrent",
            "last_name": "Buyer",
            "email": self.user.email,
            "phone": "555123456",
            "city": "Tbilisi",
            "address_line": "Concurrency Street 1",
            "note": "",
            "terms_accepted": True,
            "payment_method": OrderPaymentMethod.CASH_ON_DELIVERY,
        }
        self.terms_acceptance = TermsAcceptanceSnapshot(
            accepted_at=timezone.now(),
            version="test-version",
            content_hash="a" * 64,
            content_snapshot={"page": {"slug": "terms"}, "components": []},
            url="https://example.test/terms",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    def _checkout(self, *, idempotency_key, barrier):
        close_old_connections()
        try:
            user = get_user_model().objects.get(pk=self.user.pk)
            cart = Cart.objects.get(pk=self.cart.pk)
            owner_fingerprint = build_checkout_owner_fingerprint(user=user)
            request_fingerprint = build_checkout_request_fingerprint(
                source=OrderCheckoutSource.CART,
                validated_data=self.validated_data,
            )
            barrier.wait(timeout=10)
            result = create_order_from_cart(
                cart=cart,
                user=user,
                validated_data=self.validated_data,
                terms_acceptance=self.terms_acceptance,
                idempotency_key=idempotency_key,
                owner_fingerprint=owner_fingerprint,
                request_fingerprint=request_fingerprint,
            )
            return ("success", result.created, result.order.pk)
        except Exception as error:
            return ("error", type(error).__name__, str(error))
        finally:
            close_old_connections()

    def test_parallel_checkout_requests_with_same_key_create_one_order(self):
        idempotency_key = uuid.uuid4()
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: self._checkout(
                        idempotency_key=idempotency_key,
                        barrier=barrier,
                    ),
                    range(2),
                )
            )

        self.product.refresh_from_db()
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CheckoutAttempt.objects.count(), 1)
        self.assertEqual(self.product.stock_qty, 1)
        self.assertEqual(
            sorted(result[1] for result in results if result[0] == "success"),
            [False, True],
        )

    def test_buy_now_checkout_with_idempotency_key_supports_nullable_order(self):
        guest_token = uuid.uuid4()
        session = BuyNowSession.objects.create(
            guest_token=guest_token,
            product=self.product,
            unit_price_snapshot=self.product.price,
            quantity=1,
        )
        owner_fingerprint = build_checkout_owner_fingerprint(
            guest_token=guest_token,
        )
        request_fingerprint = build_checkout_request_fingerprint(
            source=OrderCheckoutSource.BUY_NOW,
            validated_data=self.validated_data,
        )

        result = create_order_from_buy_now_session(
            session=session,
            user=None,
            validated_data=self.validated_data,
            terms_acceptance=self.terms_acceptance,
            idempotency_key=uuid.uuid4(),
            owner_fingerprint=owner_fingerprint,
            request_fingerprint=request_fingerprint,
        )

        self.assertTrue(result.created)
        self.assertEqual(result.order.checkout_source, OrderCheckoutSource.BUY_NOW)
        self.assertFalse(BuyNowSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(CheckoutAttempt.objects.get().order, result.order)


@skipUnlessDBFeature("has_select_for_update")
class OrderCancellationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.category = Category.objects.create(
            name="Cancellation",
            slug="cancellation",
            sort_order=1,
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Cancellation Product",
            slug="cancellation-product",
            sku="CANCEL-1",
            price=Decimal("100.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )
        self.orders = [
            self._create_order(quantity=1, suffix="A"),
            self._create_order(quantity=2, suffix="B"),
        ]

    def _create_order(self, *, quantity, suffix):
        order = Order.objects.create(
            order_number=f"ORD-CANCEL-{suffix}",
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            status=OrderStatus.NEW,
            subtotal=self.product.price * quantity,
            total=self.product.price * quantity,
            first_name="Concurrent",
            last_name="Cancellation",
            email="cancel@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Cancellation Street 1",
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
        )
        return order

    def _cancel(self, *, order_id, barrier):
        close_old_connections()
        try:
            order = Order.objects.get(pk=order_id)
            barrier.wait(timeout=10)
            cancelled_order = cancel_order_and_restore_stock(order)
            return ("success", cancelled_order.pk)
        except Exception as error:
            return ("error", type(error).__name__, str(error))
        finally:
            close_old_connections()

    def test_parallel_cancellations_restore_all_stock_without_lost_update(self):
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda order: self._cancel(
                        order_id=order.pk,
                        barrier=barrier,
                    ),
                    self.orders,
                )
            )

        self.product.refresh_from_db()
        self.assertEqual(
            sorted(result[0] for result in results),
            ["success", "success"],
        )
        self.assertEqual(self.product.stock_qty, 5)
        self.assertEqual(
            Order.objects.filter(status=OrderStatus.CANCELLED).count(),
            2,
        )


@skipUnlessDBFeature("has_select_for_update")
class PaymentStatusConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.order = Order.objects.create(
            order_number="ORD-PAYMENT-RACE-1",
            payment_method=OrderPaymentMethod.CARD,
            payment_status=OrderPaymentStatus.PENDING,
            status=OrderStatus.NEW,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            first_name="Payment",
            last_name="Race",
            email="payment-race@example.com",
            phone="555123456",
            city="Tbilisi",
            address_line="Payment Street 1",
            note="",
        )
        self.paid_transaction = create_payment_transaction(
            order=self.order,
            amount=self.order.total,
            action=PaymentTransactionAction.CAPTURE,
        )
        self.failed_transaction = create_payment_transaction(
            order=self.order,
            amount=self.order.total,
            action=PaymentTransactionAction.AUTHORIZE,
        )

    def _apply_response(self, *, transaction_id, response, barrier):
        close_old_connections()
        try:
            payment_transaction = PaymentTransaction.objects.get(
                pk=transaction_id
            )
            barrier.wait(timeout=10)
            applied = apply_payment_provider_response(
                payment_transaction,
                response,
            )
            return ("success", applied.status)
        except Exception as error:
            return ("error", type(error).__name__, str(error))
        finally:
            close_old_connections()

    def test_parallel_paid_and_failed_responses_finish_paid(self):
        barrier = Barrier(2)
        operations = [
            (
                self.paid_transaction.pk,
                PaymentProviderResponse(
                    status=PaymentTransactionStatus.PAID,
                    provider_transaction_id="race-paid-1",
                    provider_reference={"event": "paid"},
                ),
            ),
            (
                self.failed_transaction.pk,
                PaymentProviderResponse(
                    status=PaymentTransactionStatus.FAILED,
                    provider_transaction_id="race-failed-1",
                    provider_reference={"event": "failed"},
                ),
            ),
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda operation: self._apply_response(
                        transaction_id=operation[0],
                        response=operation[1],
                        barrier=barrier,
                    ),
                    operations,
                )
            )

        self.order.refresh_from_db()
        self.assertEqual(
            sorted(result[0] for result in results),
            ["success", "success"],
        )
        self.assertEqual(self.order.payment_status, OrderPaymentStatus.PAID)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CommerceAdminTests(TestCase):
    def setUp(self):
        PaymentTransaction.objects.all().hard_delete()
        StockReservationItem.objects.all().delete()
        StockReservation.objects.all().delete()
        Category.objects.all().delete()
        Product.objects.all().delete()
        OrderItem.objects.all().hard_delete()
        Order.objects.all().hard_delete()
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
            "buyer_type": order.buyer_type,
            "company_name": order.company_name,
            "company_identification_code": order.company_identification_code,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
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
            "payment_transactions-TOTAL_FORMS": "0",
            "payment_transactions-INITIAL_FORMS": "0",
            "payment_transactions-MIN_NUM_FORMS": "0",
            "payment_transactions-MAX_NUM_FORMS": "1000",
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

    def test_admin_keeps_payment_status_read_only(self):
        order = self._create_order(status=OrderStatus.NEW)

        response = self.client.post(
            reverse("admin:commerce_order_change", args=[order.pk]),
            self._build_admin_payload(
                order,
                payment_status=OrderPaymentStatus.PAID,
                _save="Save",
            ),
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PENDING)

    def test_admin_ignores_manual_payment_status_regression(self):
        order = self._create_order(status=OrderStatus.NEW)
        order.payment_status = OrderPaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])

        response = self.client.post(
            reverse("admin:commerce_order_change", args=[order.pk]),
            self._build_admin_payload(
                order,
                payment_status=OrderPaymentStatus.FAILED,
                _save="Save",
            ),
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)

    def test_payment_safety_models_are_registered_in_admin(self):
        self.assertIn(StockReservation, site._registry)
        self.assertIn(PaymentTransaction, site._registry)

    def test_admin_disables_financial_record_deletion(self):
        order_admin = site._registry[Order]
        payment_admin = site._registry[PaymentTransaction]

        self.assertFalse(order_admin.has_delete_permission(None))
        self.assertFalse(payment_admin.has_add_permission(None))
        self.assertFalse(payment_admin.has_delete_permission(None))


class CommerceAdminFormTests(TestCase):
    def setUp(self):
        PaymentTransaction.objects.all().hard_delete()
        StockReservationItem.objects.all().delete()
        StockReservation.objects.all().delete()
        Category.objects.all().delete()
        Product.objects.all().delete()
        OrderItem.objects.all().hard_delete()
        Order.objects.all().hard_delete()
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
                "buyer_type": self.order.buyer_type,
                "company_name": self.order.company_name,
                "company_identification_code": self.order.company_identification_code,
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
