from datetime import timedelta
from time import monotonic, sleep

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from commerce.credo_reconciliation import due_credo_applications, reconcile_credo_application
from commerce.credo_payments import CredoPaymentError
from commerce.credo_submission import configured_credo_client
from commerce.credo_testing import require_local_credo_test_environment


class Command(BaseCommand):
    help = "Watch LOCAL Credo test applications only. GET status only, bounded lifetime, Ctrl+C to stop."

    def add_arguments(self, parser):
        parser.add_argument("--interval-seconds", type=int, default=30)
        parser.add_argument("--max-seconds", type=int, default=14400)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        interval = options["interval_seconds"]
        if not 15 <= interval <= 300 or not 1 <= options["max_seconds"] <= 43200:
            raise CommandError("Use a 15–300 second interval and a 1–43200 second lifetime.")
        try:
            require_local_credo_test_environment()
        except ValidationError:
            raise CommandError("Local development SQLite and Credo test mode are required.") from None
        if not getattr(settings, "CREDO_STATUS_CHECK_ENABLED", False):
            raise CommandError("Credo status checks are disabled.")
        # Building this client does not call a bank. No application means no HTTP.
        try:
            client = configured_credo_client()
        except CredoPaymentError:
            raise CommandError("Complete the Credo local connection configuration first.") from None
        deadline = monotonic() + options["max_seconds"]
        self.stdout.write("Watching local test applications; no application means no bank requests.")
        try:
            while monotonic() < deadline:
                close_old_connections()
                now = timezone.now()
                timing = {"created_before": now-timedelta(seconds=1), "attempted_before": now-timedelta(seconds=interval)}
                ids = list(due_credo_applications(**timing).filter(is_test=True).order_by("pk").values_list("pk", flat=True)[:10])
                for application_id in ids:
                    if monotonic() >= deadline:
                        break
                    result = reconcile_credo_application(application_id, client=client, **timing)
                    self.stdout.write(f"Application {application_id}: {result}.")
                    self.stdout.flush()
                if options["once"]:
                    break
                sleep(min(interval, max(0, deadline-monotonic())))
        except KeyboardInterrupt:
            self.stdout.write("Stopped; applications are retained.")
