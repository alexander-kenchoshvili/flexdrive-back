"""One existing scheduled job, two independent provider checks. No daemon."""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run Credo and BOG checks independently in one scheduled job; never starts a payment."

    def add_arguments(self, parser):
        # Preserve the existing BOG cron's option names/defaults.
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--min-age-minutes", type=int, default=10)
        parser.add_argument("--retry-minutes", type=int, default=15)
        parser.add_argument("--max-seconds", type=int, default=600)
        parser.add_argument("--credo-limit", type=int, default=50)
        parser.add_argument("--credo-max-seconds", type=int, default=120)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if (min(options[k] for k in ("limit", "min_age_minutes", "retry_minutes", "max_seconds")) < 1
            or not 1 <= options["credo_limit"] <= 100 or not 1 <= options["credo_max_seconds"] <= 3600):
            raise CommandError("Batch sizes, ages and time budgets must be positive and bounded.")
        failures = []
        # Credo has no callback, so do its bounded batch before BOG's backup work.
        if options["dry_run"] or getattr(settings, "CREDO_STATUS_CHECK_ENABLED", False):
            try:
                self.stdout.write("Credo status check:")
                call_command("reconcile_credo_applications", limit=options["credo_limit"],
                    min_age_seconds=1, retry_seconds=30, max_seconds=options["credo_max_seconds"],
                    dry_run=options["dry_run"], stdout=self.stdout, stderr=self.stderr)
            except Exception:
                failures.append("Credo")
                self.stderr.write("Credo check needs attention; continuing with BOG. See private payment administration.")
        else:
            self.stdout.write("Credo status checks disabled; BOG continues.")
        try:
            self.stdout.write("BOG payment check:")
            call_command("reconcile_bog_payments", **{k: options[k] for k in (
                "limit", "min_age_minutes", "retry_minutes", "max_seconds", "dry_run",
            )}, stdout=self.stdout, stderr=self.stderr)
        except Exception:
            failures.append("BOG")
            self.stderr.write("BOG check needs attention; other provider checks were not skipped.")
        if failures:
            # Preserve nonzero exit for the existing job's failure alert.
            raise CommandError("Payment checks need attention: " + ", ".join(failures))
