from datetime import timedelta
from time import monotonic

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db.models import F
from django.utils import timezone

from commerce.payment_reconciliation import due_payments, reconcile_scheduled_payment


class Command(BaseCommand):
    help = "Reconcile stale BOG payments; never initiates a charge or refund. Not scheduled automatically."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--min-age-minutes", type=int, default=10)
        parser.add_argument("--retry-minutes", type=int, default=15)
        parser.add_argument("--max-seconds", type=int, default=600)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if min(options[k] for k in (
            "limit", "min_age_minutes", "retry_minutes", "max_seconds",
        )) < 1:
            raise CommandError("Batch limit, ages and time budget must be positive.")
        recipient = getattr(settings, "BOG_RECONCILIATION_ALERT_EMAIL", "").strip()
        if recipient:
            try:
                validate_email(recipient)
            except ValidationError:
                raise CommandError("BOG_RECONCILIATION_ALERT_EMAIL is invalid.") from None
        now = timezone.now()
        created_before = now - timedelta(minutes=options["min_age_minutes"])
        attempted_before = now - timedelta(minutes=options["retry_minutes"])
        ids = list(due_payments(
            created_before=created_before, attempted_before=attempted_before,
        ).order_by(
            F("reconciliation_attempted_at").asc(nulls_first=True), "pk",
        ).values_list("pk", flat=True)[:options["limit"]])
        if options["dry_run"]:
            self.stdout.write(f"Eligible payments in batch: {len(ids)}. No API calls, writes or emails.")
            return
        counts = dict.fromkeys(("resolved", "pending", "review", "failed", "skipped"), 0)
        started = monotonic()
        for payment_id in ids:
            if monotonic() - started >= options["max_seconds"]:
                self.stdout.write("Time budget reached; remaining payments are deferred to the next run.")
                break
            try:
                result = reconcile_scheduled_payment(
                    payment_id, created_before=created_before, attempted_before=attempted_before,
                    notify_email=recipient,
                )
            except Exception:
                # Including DB/email failures: do not leak exception payloads in cron logs.
                result = "failed"
            counts[result] += 1
            if result in {"failed", "review"}:
                self.stderr.write(f"Payment {payment_id}: {result}; check payment admin and job configuration.")
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
        if counts["failed"] or counts["review"]:
            raise CommandError("Payments require attention. Check admin; configure job failure alerts before activation.")
