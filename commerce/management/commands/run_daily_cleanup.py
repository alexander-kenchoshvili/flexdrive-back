from django.core.management import call_command
from django.core.management.base import BaseCommand

from commerce.services import expire_stock_reservations


class Command(BaseCommand):
    help = "Run routine cleanup for carts, expired JWT tokens, and stock reservations."

    def handle(self, *args, **options):
        call_command("cleanup_carts", stdout=self.stdout, stderr=self.stderr)
        call_command("flushexpiredtokens", stdout=self.stdout, stderr=self.stderr)
        expired_reservations = expire_stock_reservations()
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired stock reservations updated: {expired_reservations}"
            )
        )
