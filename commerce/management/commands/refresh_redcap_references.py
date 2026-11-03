from django.core.management.base import BaseCommand, CommandError

from commerce.redcap import RedcapError
from commerce.redcap_references import refresh_redcap_references


class Command(BaseCommand):
    help = "Manually refresh RedCap reference tables only; never creates shipments."

    def handle(self, *args, **options):
        try:
            snapshot = refresh_redcap_references()
        except RedcapError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"RedCap: {len(snapshot.weights)} weight bands, {len(snapshot.locations)} zones."
        ))
