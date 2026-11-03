"""Fail closed when an old deployed scheduler still invokes EasyWay commands."""

from django.core.management.base import BaseCommand, CommandError


class RetiredEasywayCommand(BaseCommand):
    help = "Retired: EasyWay integration has been replaced by RedCap."

    def add_arguments(self, parser):
        # Accept old scheduler flags so the actionable retirement message is shown.
        parser.add_argument("--limit", type=int)
        parser.add_argument("--min-age-minutes", type=int)
        parser.add_argument("--max-seconds", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        raise CommandError(
            "EasyWay is retired. Remove its scheduled job. Use sync_redcap_tracking "
            "for RedCap tracking; tariffs are refreshed manually. No carrier request was sent."
        )
