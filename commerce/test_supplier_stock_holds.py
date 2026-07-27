from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.crossmotors_import import (
    build_crossmotors_report,
    import_crossmotors_report,
    import_crossmotors_report_bulk,
)
from catalog.models import (
    Category,
    Product,
    ProductStatus,
    ProductSupplierSource,
)

from .models import (
    Order,
    OrderItem,
    OrderPaymentMethod,
    OrderPaymentStatus,
    SupplierStockHold,
    SupplierStockHoldStatus,
)
from .services import (
    cancel_order_and_restore_stock,
    cancel_refunded_order_and_restore_stock,
)
from .supplier_stock import (
    create_supplier_stock_holds_for_order,
    release_supplier_stock_hold,
)


@override_settings(
    CROSSMOTORS_SALE_HOLD_SECONDS=60 * 60 * 24,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class SupplierStockHoldTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Lighting",
            slug="supplier-hold-lighting",
        )

    def _product(
        self,
        *,
        sku="CM-000015",
        stock_qty=10,
        supplier_stock_qty=10,
        supplier_source=ProductSupplierSource.CROSS_MOTORS,
    ):
        return Product.objects.create(
            category=self.category,
            name=f"Product {sku}",
            slug=f"product-{sku.lower()}",
            sku=sku,
            price=Decimal("100.00"),
            supplier_price=Decimal("80.00"),
            stock_qty=stock_qty,
            supplier_source=supplier_source,
            supplier_stock_qty=(
                supplier_stock_qty
                if supplier_source == ProductSupplierSource.CROSS_MOTORS
                else None
            ),
            supplier_stock_synced_at=(
                timezone.now()
                if supplier_source == ProductSupplierSource.CROSS_MOTORS
                else None
            ),
            status=ProductStatus.PUBLISHED,
        )

    def _order_with_item(
        self,
        product,
        *,
        quantity=1,
        order_number="ORD-HOLD-0001",
        payment_method=OrderPaymentMethod.CARD,
        payment_status=OrderPaymentStatus.PAID,
    ):
        line_total = product.price * quantity
        order = Order.objects.create(
            order_number=order_number,
            payment_method=payment_method,
            payment_status=payment_status,
            subtotal=line_total,
            total=line_total,
            first_name="Test",
            last_name="Customer",
            phone="+995555000000",
            city="თბილისი",
            address_line="Test address",
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price=product.price,
            quantity=quantity,
            line_total=line_total,
        )
        return order, item

    def _report(self, *, qty):
        return build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": qty,
                    "dealer_price": 80.0,
                    "currency": "GEL",
                }
            ],
            synced_at=timezone.now().isoformat(),
            product_queryset=Product.objects.all(),
        )

    def _create_paid_sale_hold(self, product, *, quantity=1):
        order, item = self._order_with_item(product, quantity=quantity)
        Product.objects.filter(pk=product.pk).update(
            stock_qty=product.stock_qty - quantity
        )
        holds = create_supplier_stock_holds_for_order(order=order)
        product.refresh_from_db()
        return order, item, holds[0]

    def test_paid_supplier_item_creates_one_idempotent_hold(self):
        product = self._product()
        order, item = self._order_with_item(product, quantity=2)

        first = create_supplier_stock_holds_for_order(order=order)
        second = create_supplier_stock_holds_for_order(order=order)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(SupplierStockHold.objects.count(), 1)
        hold = SupplierStockHold.objects.get(order_item=item)
        self.assertEqual(hold.quantity, 2)
        self.assertEqual(hold.supplier_stock_at_sale, 10)
        self.assertEqual(hold.status, SupplierStockHoldStatus.ACTIVE)

    def test_manual_product_does_not_create_supplier_hold(self):
        product = self._product(
            sku="LOCAL-1",
            supplier_source=ProductSupplierSource.MANUAL,
        )
        order, _ = self._order_with_item(product)

        self.assertEqual(
            create_supplier_stock_holds_for_order(order=order),
            [],
        )

    def test_regular_import_keeps_unreported_local_sale_deducted(self):
        product = self._product()
        self._create_paid_sale_hold(product)

        import_crossmotors_report(self._report(qty=10))

        product.refresh_from_db()
        self.assertEqual(product.supplier_stock_qty, 10)
        self.assertEqual(product.stock_qty, 9)
        self.assertEqual(product.customer_available_stock_qty, 4)

    def test_bulk_import_keeps_unreported_local_sale_deducted(self):
        product = self._product()
        self._create_paid_sale_hold(product)

        import_crossmotors_report_bulk(self._report(qty=10))

        product.refresh_from_db()
        self.assertEqual(product.supplier_stock_qty, 10)
        self.assertEqual(product.stock_qty, 9)
        self.assertEqual(product.customer_available_stock_qty, 4)

    def test_supplier_decrease_and_active_hold_are_temporarily_conservative(self):
        product = self._product()
        self._create_paid_sale_hold(product)

        import_crossmotors_report_bulk(self._report(qty=8))

        product.refresh_from_db()
        self.assertEqual(product.supplier_stock_qty, 8)
        self.assertEqual(product.stock_qty, 7)
        self.assertEqual(product.customer_available_stock_qty, 2)

    def test_expired_hold_stops_deducting_after_successful_import(self):
        product = self._product()
        _, _, hold = self._create_paid_sale_hold(product)
        SupplierStockHold.objects.filter(pk=hold.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        import_crossmotors_report_bulk(self._report(qty=9))

        product.refresh_from_db()
        hold.refresh_from_db()
        self.assertEqual(product.supplier_stock_qty, 9)
        self.assertEqual(product.stock_qty, 9)
        self.assertEqual(product.customer_available_stock_qty, 4)
        self.assertEqual(hold.status, SupplierStockHoldStatus.EXPIRED)
        self.assertIsNotNone(hold.released_at)

    def test_manual_release_is_audited_and_recalculates_stock_once(self):
        product = self._product()
        _, _, hold = self._create_paid_sale_hold(product)
        admin_user = get_user_model().objects.create_superuser(
            username="hold-admin",
            email="hold-admin@example.com",
            password="test-password",
        )

        released_hold, released = release_supplier_stock_hold(
            hold=hold,
            released_by=admin_user,
            note="Supplier confirmed.",
        )
        replayed_hold, replayed = release_supplier_stock_hold(
            hold=released_hold,
            released_by=admin_user,
        )

        product.refresh_from_db()
        self.assertTrue(released)
        self.assertFalse(replayed)
        self.assertEqual(product.stock_qty, 10)
        self.assertEqual(
            replayed_hold.status,
            SupplierStockHoldStatus.MANUALLY_RELEASED,
        )
        self.assertEqual(replayed_hold.released_by, admin_user)
        self.assertEqual(replayed_hold.release_note, "Supplier confirmed.")

    def test_supplier_order_cancel_releases_hold_without_blind_increment(self):
        product = self._product(stock_qty=8, supplier_stock_qty=9)
        order, _, hold = self._create_paid_sale_hold(product)
        order.payment_method = OrderPaymentMethod.CASH_ON_DELIVERY
        order.payment_status = OrderPaymentStatus.PENDING
        order.save(update_fields=["payment_method", "payment_status", "updated_at"])

        cancel_order_and_restore_stock(order)

        product.refresh_from_db()
        hold.refresh_from_db()
        self.assertEqual(product.stock_qty, 9)
        self.assertEqual(hold.status, SupplierStockHoldStatus.ORDER_CANCELLED)
        self.assertIsNotNone(hold.released_at)

    def test_refunded_card_order_releases_supplier_hold_safely(self):
        product = self._product(stock_qty=8, supplier_stock_qty=9)
        order, _, hold = self._create_paid_sale_hold(product)
        order.payment_status = OrderPaymentStatus.REFUNDED
        order.save(update_fields=["payment_status", "updated_at"])

        cancel_refunded_order_and_restore_stock(order)

        product.refresh_from_db()
        hold.refresh_from_db()
        self.assertEqual(product.stock_qty, 9)
        self.assertEqual(hold.status, SupplierStockHoldStatus.ORDER_CANCELLED)
        self.assertIsNotNone(hold.released_at)

    def test_manual_product_cancel_keeps_existing_stock_restore_behavior(self):
        product = self._product(
            sku="LOCAL-2",
            stock_qty=9,
            supplier_source=ProductSupplierSource.MANUAL,
        )
        order, _ = self._order_with_item(
            product,
            payment_method=OrderPaymentMethod.CASH_ON_DELIVERY,
            payment_status=OrderPaymentStatus.PENDING,
        )

        cancel_order_and_restore_stock(order)

        product.refresh_from_db()
        self.assertEqual(product.stock_qty, 10)

    def test_admin_lists_stock_summary_and_manual_release_button(self):
        product = self._product()
        _, _, hold = self._create_paid_sale_hold(product)
        admin_user = get_user_model().objects.create_superuser(
            username="stock-admin",
            email="stock-admin@example.com",
            password="test-password",
        )
        self.client.force_login(admin_user)

        product_list = self.client.get(reverse("admin:catalog_product_changelist"))
        hold_change = self.client.get(
            reverse(
                "admin:commerce_supplierstockhold_change",
                args=[hold.pk],
            )
        )

        self.assertContains(product_list, "Cross Motors-ის ნაშთი")
        self.assertContains(product_list, "დაკავებული")
        self.assertContains(product_list, "გასაყიდი")
        self.assertContains(product_list, "დაცვა მოქმედებს")
        self.assertContains(hold_change, "დროებითი ჩამოკლების ხელით მოხსნა")

    def test_admin_manual_release_requires_confirmation_post(self):
        product = self._product()
        _, _, hold = self._create_paid_sale_hold(product)
        admin_user = get_user_model().objects.create_superuser(
            username="release-admin",
            email="release-admin@example.com",
            password="test-password",
        )
        self.client.force_login(admin_user)
        release_url = reverse(
            "admin:commerce_supplierstockhold_release",
            args=[hold.pk],
        )

        confirmation = self.client.get(release_url)
        hold.refresh_from_db()
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(hold.status, SupplierStockHoldStatus.ACTIVE)

        response = self.client.post(release_url)
        hold.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            hold.status,
            SupplierStockHoldStatus.MANUALLY_RELEASED,
        )
        self.assertEqual(hold.released_by, admin_user)
