from datetime import timedelta
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from commerce.credo_payments import CredoPaymentError, CredoPaymentsClient
from commerce.credo_reconciliation import due_credo_applications, reconcile_credo_application


class Command(BaseCommand):
    help = "Read Credo statuses. Never creates/cancels a loan. Not scheduled automatically."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        # Explicit operator inputs; neither value claims a bank expiry/rate limit.
        parser.add_argument("--min-age-seconds", type=int, required=True)
        parser.add_argument("--retry-seconds", type=int, required=True)
        parser.add_argument("--max-seconds", type=int, default=120)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if (not 1 <= options["limit"] <= 100 or not 1 <= options["max_seconds"] <= 3600
                or not all(1 <= options[key] <= 7 * 86400 for key in ("min_age_seconds", "retry_seconds"))):
            raise CommandError("Batch, intervals and time budget must be positive and bounded.")
        now = timezone.now()
        created_before = now-timedelta(seconds=options["min_age_seconds"])
        attempted_before = now-timedelta(seconds=options["retry_seconds"])
        ids = list(due_credo_applications(created_before=created_before, attempted_before=attempted_before).order_by(
            F("bank_check_attempted_at").asc(nulls_first=True), "pk",
        ).values_list("pk", flat=True)[:options["limit"]])
        if options["dry_run"]:
            self.stdout.write(f"Eligible applications: {len(ids)}. No API calls or writes.")
            return
        if not ids:
            self.stdout.write("No eligible applications.")
            return
        # Independent from the future flag controlling NEW financing requests.
        # Turning off new checkout choices must not silently stop old cases.
        if not getattr(settings, "CREDO_STATUS_CHECK_ENABLED", False):
            raise CommandError("Credo status checks are disabled; configure them explicitly.")
        try:
            client = CredoPaymentsClient(
                merchant_id=getattr(settings, "CREDO_MERCHANT_ID", ""),
                secret_key=getattr(settings, "CREDO_SECRET_KEY", ""),
                order_url=getattr(settings, "CREDO_ORDER_URL", ""),
                status_url=getattr(settings, "CREDO_STATUS_URL", ""),
                redirect_origin=getattr(settings, "CREDO_REDIRECT_ORIGIN", ""),
                connect_timeout=getattr(settings, "CREDO_HTTP_CONNECT_TIMEOUT_SECONDS", 5),
                read_timeout=getattr(settings, "CREDO_HTTP_READ_TIMEOUT_SECONDS", 15),
            )
        except CredoPaymentError:
            raise CommandError("Credo status client is not configured correctly.") from None
        counts = dict.fromkeys(("resolved", "ready", "pending", "review", "failed", "skipped"), 0)
        started = monotonic()
        for application_id in ids:
            if monotonic()-started >= options["max_seconds"]:
                break
            try:
                result = reconcile_credo_application(
                    application_id, client=client, created_before=created_before, attempted_before=attempted_before,
                )
            except Exception:
                # No bank payload, query hash, borrower data or exception text.
                result = "failed"
            counts[result] += 1
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
        if counts["failed"] or counts["review"]:
            raise CommandError("Credo applications need attention; inspect private operations.")
