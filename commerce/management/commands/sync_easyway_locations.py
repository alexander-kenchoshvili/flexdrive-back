from django.core.management.base import BaseCommand, CommandError

from commerce.easyway import EasywayClient, EasywayError
from commerce.easyway_locations import sync_easyway_locations


class Command(BaseCommand):
    help = "Synchronize EasyWay regions and cities into the FlexDrive database."

    def handle(self, *args, **options):
        try:
            result = sync_easyway_locations(EasywayClient.from_settings())
        except EasywayError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "EasyWay locations synchronized: "
                f"regions created={result.regions_created}, "
                f"updated={result.regions_updated}, "
                f"deactivated={result.regions_deactivated}; "
                f"cities created={result.cities_created}, "
                f"updated={result.cities_updated}, "
                f"deactivated={result.cities_deactivated}."
            )
        )
