from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from .easyway import EasywayClient, EasywayTransportError
from .easyway_reports import DETAIL_LIMIT, TrackingReport
from .easyway_tracking import sync_easyway_tracking
from .models import EasywaySyncReport, Order


def history(status):
    return [{"status": status, "created_at": "2026-07-15T14:39:35Z"}]


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class EasywayReportTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.enterClassContext(TemporaryDirectory())
        cls.enterClassContext(override_settings(STATIC_ROOT=root))

    def setUp(self):
        self.order = self.make_order(1)

    def make_order(self, number):
        return Order.objects.create(
            order_number=f"ORD-REPORT-{number}", subtotal=10, total=10,
            payment_status="paid", status="confirmed", delivery_provider="easyway",
            easyway_order_id=number, easyway_shipment_state="created",
        )

    def test_manual_change_report_and_unchanged_repeat(self):
        client = Mock(spec=EasywayClient)
        client.get_tracking.return_value = history("taken")
        sync_easyway_tracking(self.order.pk, client=client)
        report = EasywaySyncReport.objects.get()
        self.assertEqual(report.source, "manual")
        self.assertEqual(report.details["counts"]["changed"], 1)
        item = report.details["items"][0]
        self.assertEqual((item["order_before"], item["order_after"]), ("confirmed", "shipped"))
        self.assertEqual((item["carrier_before"], item["carrier_after"]), ("", "taken"))
        sync_easyway_tracking(self.order.pk, client=client)
        self.assertEqual(EasywaySyncReport.objects.count(), 1)

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_batch_report_combines_changes_unchanged_and_safe_failures(self, factory):
        unchanged = self.make_order(2)
        Order.objects.filter(pk=unchanged.pk).update(easyway_tracking_status="new")
        failed = self.make_order(3)
        factory.return_value.get_tracking.side_effect = [
            history("taken"), history("new"), EasywayTransportError("private-token"),
        ]
        with self.assertRaises(CommandError):
            call_command("sync_easyway_tracking", stdout=StringIO(), stderr=StringIO())
        report = EasywaySyncReport.objects.get()
        self.assertEqual(report.source, "scheduled")
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.details["counts"], {
            "checked": 3, "changed": 1, "failed": 1, "review": 0, "skipped": 0,
        })
        self.assertEqual(len(report.details["items"]), 2)
        self.assertEqual(report.details["items"][1]["order_id"], failed.pk)
        self.assertNotIn("private-token", str(report.details))

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_empty_dry_and_unchanged_runs_create_no_reports(self, factory):
        call_command("sync_easyway_tracking", dry_run=True, stdout=StringIO())
        factory.assert_not_called()
        Order.objects.filter(pk=self.order.pk).update(easyway_tracking_status="new")
        factory.return_value.get_tracking.return_value = history("new")
        call_command("sync_easyway_tracking", stdout=StringIO())
        # The next run has no due shipments.
        call_command("sync_easyway_tracking", stdout=StringIO())
        self.assertFalse(EasywaySyncReport.objects.exists())
        self.assertEqual(factory.return_value.get_tracking.call_count, 1)

    def test_unknown_status_review_and_admin_html_escaping(self):
        client = Mock(spec=EasywayClient)
        client.get_tracking.return_value = history("<script>alert(1)</script>")
        sync_easyway_tracking(self.order.pk, client=client)
        report = EasywaySyncReport.objects.get()
        self.assertEqual(report.status, "review")
        html = admin.site._registry[EasywaySyncReport].report_details(report)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn(reverse("admin:commerce_order_change", args=[self.order.pk]), html)

    def test_report_delete_does_not_touch_order_or_history(self):
        client = Mock(spec=EasywayClient)
        client.get_tracking.return_value = history("taken")
        sync_easyway_tracking(self.order.pk, client=client)
        self.order.refresh_from_db()
        before = self.order.easyway_tracking_history
        EasywaySyncReport.objects.all().delete()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")
        self.assertEqual(self.order.easyway_tracking_history, before)

    @patch("commerce.easyway_tracking.EasywayClient.from_settings")
    def test_interrupted_batch_keeps_committed_changes_and_failure_report(self, factory):
        self.make_order(2)
        factory.return_value.get_tracking.side_effect = [history("taken"), RuntimeError("secret")]
        with self.assertRaises(RuntimeError):
            call_command("sync_easyway_tracking", stdout=StringIO(), stderr=StringIO())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")
        report = EasywaySyncReport.objects.get()
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.details["counts"]["changed"], 1)
        self.assertTrue(report.details["run_error"])
        self.assertNotIn("secret", str(report.details))

    def test_bounded_details_keep_exact_totals(self):
        report = TrackingReport(source="scheduled")
        for number in range(DETAIL_LIMIT + 7):
            report.record("synced", {
                "order_id": number, "order_number": str(number),
                "carrier_before": "new", "carrier_after": "taking",
                "order_before": "confirmed", "order_after": "processing",
            })
        saved = report.save()
        self.assertEqual(saved.details["counts"]["changed"], DETAIL_LIMIT + 7)
        self.assertEqual(len(saved.details["items"]), DETAIL_LIMIT)

    def test_admin_view_only_permissions_and_delete_confirmation(self):
        client = Mock(spec=EasywayClient)
        client.get_tracking.return_value = history("taken")
        sync_easyway_tracking(self.order.pk, client=client)
        report = EasywaySyncReport.objects.get()
        user = get_user_model().objects.create_user(
            username="reports@example.com", email="reports@example.com", password="Test-only-123", is_staff=True,
        )
        user.user_permissions.add(Permission.objects.get(
            codename="view_easywaysyncreport", content_type__app_label="commerce",
        ))
        self.client.force_login(user)
        url = reverse("admin:commerce_easywaysyncreport_change", args=[report.pk])
        self.assertContains(self.client.get(url), self.order.order_number)
        self.assertEqual(self.client.post(url, {"summary": "overwrite"}).status_code, 403)
        delete_url = reverse("admin:commerce_easywaysyncreport_delete", args=[report.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)
        user.user_permissions.add(Permission.objects.get(
            codename="delete_easywaysyncreport", content_type__app_label="commerce",
        ))
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.assertTrue(EasywaySyncReport.objects.filter(pk=report.pk).exists())
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 302)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
