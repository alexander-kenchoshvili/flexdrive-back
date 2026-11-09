from django.core.management.base import BaseCommand, CommandError

from commerce.wingo import WingoError
from commerce.wingo_references import refresh_wingo_references


class Command(BaseCommand):
    help = "Manually refresh Wingo references and tariffs only; never creates shipments."

    def handle(self, *args, **options):
        try:
            snapshot = refresh_wingo_references()
        except WingoError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS(
            f"Wingo ({snapshot.get_account_mode_display()}): {len(snapshot.tariffs)} წონის დიაპაზონი, "
            f"{len(snapshot.regions)} რეგიონი, {len(snapshot.localities)} დასახლება."
        ))
