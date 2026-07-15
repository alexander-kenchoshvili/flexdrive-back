from django.core.management.base import BaseCommand, CommandError

from commerce.easyway import EasywayClient, EasywayError


class Command(BaseCommand):
    help = "Check EasyWay credentials using read-only API endpoints."

    def handle(self, *args, **options):
        try:
            client = EasywayClient.from_settings()
            checks = (
                ("time", client.get_server_time),
                ("regions", client.get_regions),
                ("packages", client.get_packages),
                ("legal forms", client.get_legal_forms),
            )
            for label, callback in checks:
                result = callback()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"EasyWay {label}: OK ({self._describe(result)})"
                    )
                )
        except EasywayError as error:
            raise CommandError(str(error)) from error

    @staticmethod
    def _describe(result):
        if isinstance(result, list):
            return f"{len(result)} items"
        if isinstance(result, dict):
            return f"object with {len(result)} fields"
        return type(result).__name__
