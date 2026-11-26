from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from commerce.credo_testing import close_cancelled_credo_test, require_local_credo_test_environment
from commerce.models import CredoApplication


class Command(BaseCommand):
    help = "Close an unshipped LOCAL test after the BANK cancelled it. Defaults to dry run; never calls a provider."

    def add_arguments(self, parser):
        parser.add_argument("application_token")
        parser.add_argument("--actor-id", type=int, required=True)
        parser.add_argument("--bank-reference", required=True)
        parser.add_argument("--confirm-unshipped", action="store_true")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        try:
            require_local_credo_test_environment()
            application = CredoApplication.objects.get(public_token=options["application_token"])
            actor = get_user_model().objects.get(pk=options["actor_id"])
            result = close_cancelled_credo_test(application_id=application.pk, actor=actor,
                bank_reference=options["bank_reference"], confirmed_unshipped=options["confirm_unshipped"], commit=options["commit"])
        except (CredoApplication.DoesNotExist, get_user_model().DoesNotExist, ValidationError, PermissionDenied):
            raise CommandError("Test closure refused. Check local scope, permissions, fresh bank cancellation and absence of shipping/payment.") from None
        self.stdout.write("Test closed; no provider request." if result["closed"] else "Dry run passed; no changes or provider request.")
