from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class CombinedReconciliationTests(SimpleTestCase):
    def run_job(self, **options):
        call_command("reconcile_payments", stdout=StringIO(), stderr=StringIO(), **options)

    @override_settings(CREDO_STATUS_CHECK_ENABLED=True)
    def test_both_providers_run_with_separate_budgets_and_existing_bog_arguments(self):
        with patch("commerce.management.commands.reconcile_payments.call_command") as run:
            self.run_job(limit=75, max_seconds=400)
        self.assertEqual([c.args[0] for c in run.call_args_list], ["reconcile_credo_applications", "reconcile_bog_payments"])
        self.assertEqual(run.call_args_list[0].kwargs["retry_seconds"], 30)
        self.assertEqual(run.call_args_list[0].kwargs["max_seconds"], 120)
        self.assertEqual(run.call_args_list[1].kwargs["limit"], 75)
        self.assertEqual(run.call_args_list[1].kwargs["max_seconds"], 400)

    @override_settings(CREDO_STATUS_CHECK_ENABLED=True)
    def test_either_provider_failure_does_not_skip_the_other_and_still_fails_job_alert(self):
        for failed in ("reconcile_credo_applications", "reconcile_bog_payments"):
            def fail(name, **kwargs):
                if name == failed: raise CommandError("private error")
            with self.subTest(failed=failed), patch("commerce.management.commands.reconcile_payments.call_command", side_effect=fail) as run:
                with self.assertRaises(CommandError): self.run_job()
                self.assertEqual(run.call_count, 2)

    @override_settings(CREDO_STATUS_CHECK_ENABLED=False)
    def test_disabled_credo_never_blocks_bog(self):
        with patch("commerce.management.commands.reconcile_payments.call_command") as run:
            self.run_job()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], "reconcile_bog_payments")

    @override_settings(CREDO_STATUS_CHECK_ENABLED=False)
    def test_dry_run_passes_dry_run_to_both_even_before_activation(self):
        with patch("commerce.management.commands.reconcile_payments.call_command") as run:
            self.run_job(dry_run=True)
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all(c.kwargs["dry_run"] for c in run.call_args_list))

    def test_invalid_limits_abort_before_any_provider_work(self):
        with patch("commerce.management.commands.reconcile_payments.call_command") as run:
            with self.assertRaises(CommandError): self.run_job(credo_limit=101)
        run.assert_not_called()
