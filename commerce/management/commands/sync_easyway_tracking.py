from datetime import timedelta
from time import monotonic

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from commerce.easyway_tracking import (
    TrackingError, due_tracking_orders, sync_easyway_tracking,
)
from commerce.easyway_reports import TrackingReport


class Command(BaseCommand):
    help = "Refresh existing EasyWay shipments only; never creates or cancels shipments."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--min-age-minutes", type=int, default=10)
        parser.add_argument("--max-seconds", type=int, default=600)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if min(options["limit"], options["min_age_minutes"], options["max_seconds"]) < 1:
            raise CommandError("Limit, minimum age and time budget must be positive.")
        before = timezone.now() - timedelta(minutes=options["min_age_minutes"])
        ids = list(due_tracking_orders(before=before).order_by(
            F("easyway_tracking_attempted_at").asc(nulls_first=True), "pk"
        ).values_list("pk", flat=True)[:options["limit"]])
        if options["dry_run"]:
            self.stdout.write(f"Eligible shipments in batch: {len(ids)}. No API calls or writes.")
            return
        counts = {"synced": 0, "review": 0, "skipped": 0, "failed": 0}
        started = monotonic()
        report = TrackingReport(source="scheduled")
        try:
            for order_id in ids:
                if monotonic() - started >= options["max_seconds"]:
                    self.stdout.write("Time budget reached; remaining shipments will be retried next run.")
                    break
                try:
                    result = sync_easyway_tracking(order_id, due_before=before, report=report)
                except TrackingError:
                    counts["failed"] += 1
                    self.stderr.write(f"Order {order_id}: tracking failed; see admin.")
                else:
                    counts[result] += 1
                    if result == "review":
                        self.stderr.write(f"Order {order_id}: tracking requires review; see admin.")
        except Exception:
            report.run_error = "Tracking interrupted by an unexpected error; check job logs."
            raise
        finally:
            report.save()
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
        if counts["failed"] or counts["review"]:
            raise CommandError("Some shipments require attention; remaining shipments were processed.")
