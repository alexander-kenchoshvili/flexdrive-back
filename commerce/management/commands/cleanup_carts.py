from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.utils import timezone

from commerce.models import Cart


class Command(BaseCommand):
    help = "Delete stale carts using inactivity-based retention windows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matching carts without deleting them.",
        )
        parser.add_argument(
            "--empty-ttl-seconds",
            type=int,
            default=None,
            help="Override the empty-cart retention window in seconds.",
        )
        parser.add_argument(
            "--guest-ttl-seconds",
            type=int,
            default=None,
            help="Override the guest-cart retention window in seconds.",
        )
        parser.add_argument(
            "--user-ttl-seconds",
            type=int,
            default=None,
            help="Override the authenticated-user cart retention window in seconds.",
        )

    def handle(self, *args, **options):
        empty_ttl_seconds = self._resolve_ttl(
            label="empty",
            override_value=options["empty_ttl_seconds"],
            default_value=settings.CART_EMPTY_TTL_SECONDS,
        )
        guest_ttl_seconds = self._resolve_ttl(
            label="guest",
            override_value=options["guest_ttl_seconds"],
            default_value=settings.CART_GUEST_TTL_SECONDS,
        )
        user_ttl_seconds = self._resolve_ttl(
            label="user",
            override_value=options["user_ttl_seconds"],
            default_value=settings.CART_USER_TTL_SECONDS,
        )

        now = timezone.now()
        empty_cutoff = now - timedelta(seconds=empty_ttl_seconds)
        guest_cutoff = now - timedelta(seconds=guest_ttl_seconds)
        user_cutoff = now - timedelta(seconds=user_ttl_seconds)

        base_queryset = Cart.objects.annotate(item_count=Count("items"))

        empty_cart_ids = base_queryset.filter(
            item_count=0,
            updated_at__lt=empty_cutoff,
        ).values("pk")
        guest_cart_ids = base_queryset.filter(
            item_count__gt=0,
            user__isnull=True,
            updated_at__lt=guest_cutoff,
        ).values("pk")
        user_cart_ids = base_queryset.filter(
            item_count__gt=0,
            user__isnull=False,
            updated_at__lt=user_cutoff,
        ).values("pk")

        empty_count = Cart.objects.filter(pk__in=empty_cart_ids).count()
        guest_count = Cart.objects.filter(pk__in=guest_cart_ids).count()
        user_count = Cart.objects.filter(pk__in=user_cart_ids).count()
        total_matched = empty_count + guest_count + user_count

        self.stdout.write(f"Empty carts matched: {empty_count}")
        self.stdout.write(f"Guest carts matched: {guest_count}")
        self.stdout.write(f"User carts matched: {user_count}")
        self.stdout.write(f"Total matched: {total_matched}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Total would delete: {total_matched}"))
            return

        matched_carts = Cart.objects.filter(
            Q(pk__in=empty_cart_ids)
            | Q(pk__in=guest_cart_ids)
            | Q(pk__in=user_cart_ids)
        )
        _, deleted_details = matched_carts.delete()
        deleted_count = deleted_details.get("commerce.Cart", 0)
        self.stdout.write(self.style.SUCCESS(f"Total deleted: {deleted_count}"))

    def _resolve_ttl(self, *, label, override_value, default_value):
        ttl_seconds = default_value if override_value is None else override_value
        if ttl_seconds < 0:
            raise CommandError(f"--{label}-ttl-seconds must be greater than or equal to 0.")
        return ttl_seconds
