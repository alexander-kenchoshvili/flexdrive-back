from datetime import timedelta
from decimal import Decimal
from io import StringIO
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Category, Product, ProductStatus

from commerce.models import Cart, CartItem


@override_settings(
    CART_EMPTY_TTL_SECONDS=60 * 60 * 24,
    CART_GUEST_TTL_SECONDS=60 * 60 * 24 * 30,
    CART_USER_TTL_SECONDS=60 * 60 * 24 * 60,
)
class CleanupCartsCommandTests(TestCase):
    def setUp(self):
        CartItem.objects.all().delete()
        Cart.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        get_user_model().objects.filter(username__startswith="cleanup-user-").delete()

        self.category = Category.objects.create(name="Interior", slug="cleanup-interior", sort_order=1)
        self.product = Product.objects.create(
            category=self.category,
            name="Cleanup Vacuum",
            slug="cleanup-vacuum",
            sku="CLEAN-001",
            short_description="Daily cleaning",
            description="Cleanup test product",
            price=Decimal("120.00"),
            stock_qty=20,
            status=ProductStatus.PUBLISHED,
        )
        self.user_index = 0

    def _create_cart(self, *, updated_at, user=None, guest_token=None, quantity=None, is_active=True):
        cart = Cart.objects.create(
            user=user,
            guest_token=guest_token,
            is_active=is_active,
        )
        if quantity is not None:
            CartItem.objects.create(cart=cart, product=self.product, quantity=quantity)
        Cart.objects.filter(pk=cart.pk).update(updated_at=updated_at)
        return Cart.objects.get(pk=cart.pk)

    def _create_user(self):
        self.user_index += 1
        username = f"cleanup-user-{self.user_index}@example.com"
        return get_user_model().objects.create_user(
            username=username,
            email=username,
            password="Password123!",
            is_active=True,
        )

    def _run_command(self, *args):
        stdout = StringIO()
        call_command("cleanup_carts", *args, stdout=stdout)
        return stdout.getvalue()

    def test_deletes_old_empty_carts(self):
        stale_cart = self._create_cart(updated_at=timezone.now() - timedelta(days=2), guest_token=uuid.uuid4())

        output = self._run_command()

        self.assertFalse(Cart.objects.filter(pk=stale_cart.pk).exists())
        self.assertIn("Empty carts matched: 1", output)
        self.assertIn("Total deleted: 1", output)

    def test_does_not_delete_recent_empty_carts(self):
        recent_cart = self._create_cart(updated_at=timezone.now() - timedelta(hours=2), guest_token=uuid.uuid4())

        output = self._run_command()

        self.assertTrue(Cart.objects.filter(pk=recent_cart.pk).exists())
        self.assertIn("Empty carts matched: 0", output)
        self.assertIn("Total deleted: 0", output)

    def test_deletes_old_guest_carts_with_items(self):
        stale_guest_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=31),
            guest_token=uuid.uuid4(),
            quantity=2,
        )

        output = self._run_command()

        self.assertFalse(Cart.objects.filter(pk=stale_guest_cart.pk).exists())
        self.assertIn("Guest carts matched: 1", output)
        self.assertIn("Total deleted: 1", output)

    def test_does_not_delete_recent_guest_carts_with_items(self):
        recent_guest_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=5),
            guest_token=uuid.uuid4(),
            quantity=1,
        )

        output = self._run_command()

        self.assertTrue(Cart.objects.filter(pk=recent_guest_cart.pk).exists())
        self.assertIn("Guest carts matched: 0", output)
        self.assertIn("Total deleted: 0", output)

    def test_deletes_old_authenticated_user_carts(self):
        user = self._create_user()
        stale_user_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=61),
            user=user,
            quantity=3,
        )

        output = self._run_command()

        self.assertFalse(Cart.objects.filter(pk=stale_user_cart.pk).exists())
        self.assertIn("User carts matched: 1", output)
        self.assertIn("Total deleted: 1", output)

    def test_does_not_delete_recent_authenticated_user_carts(self):
        user = self._create_user()
        recent_user_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=10),
            user=user,
            quantity=1,
        )

        output = self._run_command()

        self.assertTrue(Cart.objects.filter(pk=recent_user_cart.pk).exists())
        self.assertIn("User carts matched: 0", output)
        self.assertIn("Total deleted: 0", output)

    def test_dry_run_reports_matches_without_deleting(self):
        stale_empty = self._create_cart(
            updated_at=timezone.now() - timedelta(days=2),
            guest_token=uuid.uuid4(),
        )
        stale_guest = self._create_cart(
            updated_at=timezone.now() - timedelta(days=31),
            guest_token=uuid.uuid4(),
            quantity=1,
        )

        output = self._run_command("--dry-run")

        self.assertTrue(Cart.objects.filter(pk=stale_empty.pk).exists())
        self.assertTrue(Cart.objects.filter(pk=stale_guest.pk).exists())
        self.assertIn("Empty carts matched: 1", output)
        self.assertIn("Guest carts matched: 1", output)
        self.assertIn("Total matched: 2", output)
        self.assertIn("Total would delete: 2", output)

    def test_override_flags_change_behavior_without_changing_settings(self):
        guest_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=10),
            guest_token=uuid.uuid4(),
            quantity=1,
        )

        output = self._run_command("--guest-ttl-seconds=86400")

        self.assertFalse(Cart.objects.filter(pk=guest_cart.pk).exists())
        self.assertIn("Guest carts matched: 1", output)
        self.assertIn("Total deleted: 1", output)

    def test_mixed_dataset_reports_category_counts_and_total(self):
        user = self._create_user()
        empty_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=2),
            guest_token=uuid.uuid4(),
        )
        guest_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=31),
            guest_token=uuid.uuid4(),
            quantity=1,
        )
        user_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=61),
            user=user,
            quantity=2,
        )
        recent_user_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=3),
            user=self._create_user(),
            quantity=1,
        )

        output = self._run_command()

        self.assertFalse(Cart.objects.filter(pk=empty_cart.pk).exists())
        self.assertFalse(Cart.objects.filter(pk=guest_cart.pk).exists())
        self.assertFalse(Cart.objects.filter(pk=user_cart.pk).exists())
        self.assertTrue(Cart.objects.filter(pk=recent_user_cart.pk).exists())
        self.assertIn("Empty carts matched: 1", output)
        self.assertIn("Guest carts matched: 1", output)
        self.assertIn("User carts matched: 1", output)
        self.assertIn("Total matched: 3", output)
        self.assertIn("Total deleted: 3", output)

    def test_exact_cutoff_is_not_deleted(self):
        fixed_now = timezone.now()
        cutoff_cart = self._create_cart(
            updated_at=fixed_now - timedelta(days=30),
            guest_token=uuid.uuid4(),
            quantity=1,
        )

        with patch("commerce.management.commands.cleanup_carts.timezone.now", return_value=fixed_now):
            output = self._run_command()

        self.assertTrue(Cart.objects.filter(pk=cutoff_cart.pk).exists())
        self.assertIn("Guest carts matched: 0", output)
        self.assertIn("Total deleted: 0", output)

    def test_carts_with_items_are_not_treated_as_empty(self):
        guest_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=10),
            guest_token=uuid.uuid4(),
            quantity=1,
        )
        user_cart = self._create_cart(
            updated_at=timezone.now() - timedelta(days=20),
            user=self._create_user(),
            quantity=1,
        )

        output = self._run_command()

        self.assertTrue(Cart.objects.filter(pk=guest_cart.pk).exists())
        self.assertTrue(Cart.objects.filter(pk=user_cart.pk).exists())
        self.assertIn("Empty carts matched: 0", output)
        self.assertIn("Total deleted: 0", output)

    def test_negative_ttl_override_fails_clearly(self):
        with self.assertRaisesMessage(
            CommandError,
            "--guest-ttl-seconds must be greater than or equal to 0.",
        ):
            self._run_command("--guest-ttl-seconds=-1")
