from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from commerce.redcap_tracking import due_shipments, sync_shipments


class Command(BaseCommand):
    help = "Read active RedCap tracking in one batch; never books or cancels shipments."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--min-age-minutes", type=int, default=10)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000 or options["min_age_minutes"] < 1:
            raise CommandError("Limit must be 1–1000; minimum age must be positive.")
        before = timezone.now() - timedelta(minutes=options["min_age_minutes"])
        ids = list(due_shipments(before).order_by(F("tracking_attempted_at").asc(nulls_first=True), "pk")
                   .values_list("order_id", flat=True)[:options["limit"]])
        if options["dry_run"]:
            self.stdout.write(f"Eligible shipments: {len(ids)}. No API calls or writes.")
            return
        counts = sync_shipments(ids, source="scheduled", before=before)
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
        if counts["failed"] or counts["review"]:
            raise CommandError("Some RedCap shipments require attention; see admin reports.")
