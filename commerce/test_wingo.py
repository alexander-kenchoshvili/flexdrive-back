import copy
from io import StringIO
import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import WingoReferenceData
from .wingo import (
    MAX_REFERENCE_BYTES, WingoClient, WingoConfigurationError, WingoError,
    WingoResponseError, WingoTransportError,
)
from .wingo_references import refresh_wingo_references


def sample():
    return json.loads((Path(__file__).with_name("wingo_samples") / "references.json").read_text(encoding="utf-8"))


def reference_client(data=None):
    data = data or sample()
    client = Mock(spec=WingoClient)
    client.account_mode = "test"
    client.api_base_url = "https://wingo.example/api/v1"
    client.get_regions.return_value = data["regions"]
    client.get_weight_ranges.return_value = data["weight_ranges"]
    client.get_delivery_types.return_value = data["delivery_types"]
    client.get_merchant_tariffs.return_value = data["tariffs"]
    client.get_localities.side_effect = lambda name: data["localities"][name]
    return client


class WingoTransportTests(SimpleTestCase):
    def make_client(self, *, body=None, status=200, content_type="application/json", chunks=None):
        response = Mock(status_code=status)
        response.headers = {"Content-Type": content_type}
        response.iter_content.return_value = chunks if chunks is not None else [json.dumps(body or []).encode()]
        http = Mock()
        http.request.return_value = response
        return WingoClient(api_key="private-test-key", api_base_url="https://wingo.example/api/v1/",
                           http_client=http), http, response

    def test_uses_header_timeouts_and_streaming_without_redirects(self):
        client, http, response = self.make_client(body=sample()["regions"])
        self.assertEqual(len(client.get_regions()["regions"]), 4)
        http.request.assert_called_once_with(
            "GET", "https://wingo.example/api/v1/regions",
            headers={"X-API-Key": "private-test-key", "Accept": "application/json"},
            params={"includeLocalities": 1}, timeout=(5.0, 20.0), allow_redirects=False, stream=True)
        response.close.assert_called_once()

    def test_reference_operations_remain_read_only(self):
        client, http, _ = self.make_client()
        client.get_regions()
        client.get_localities("თბილისი")
        client.get_weight_ranges()
        client.get_delivery_types()
        client.get_merchant_tariffs()
        self.assertEqual(http.request.call_count, 5)
        self.assertTrue(all(call.args[0] == "GET" for call in http.request.call_args_list))
        self.assertEqual(http.request.call_args_list[1].kwargs["params"], {"regionGe": "თბილისი"})

    def test_http_failures_and_redirects_do_not_retry_or_expose_provider_body(self):
        for status in (301, 302, 401, 403, 429, 500):
            with self.subTest(status=status):
                client, http, response = self.make_client(status=status, chunks=[b'private-test-key phone'])
                with self.assertRaises(WingoResponseError) as caught:
                    client.get_merchant_tariffs()
                self.assertEqual(caught.exception.status_code, status)
                self.assertNotIn("private", str(caught.exception))
                response.iter_content.assert_not_called()
                response.close.assert_called_once()
                http.request.assert_called_once()

    def test_transport_failure_does_not_retry_or_leak_exception_details(self):
        client, http, _ = self.make_client()
        http.request.side_effect = requests.Timeout("private-test-key recipient@example.com")
        with self.assertRaises(WingoTransportError) as caught:
            client.get_merchant_tariffs()
        self.assertNotIn("private", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        http.request.assert_called_once()

    def test_stream_failure_closes_response_and_does_not_retry(self):
        client, http, response = self.make_client()
        response.iter_content.side_effect = requests.ConnectionError("private-test-key")
        with self.assertRaises(WingoTransportError):
            client.get_regions()
        response.close.assert_called_once()
        http.request.assert_called_once()

    def test_invalid_and_oversized_json_is_rejected(self):
        variants = [("text/html", [b"<html>login</html>"]), ("application/json", [b"not json"]),
                    ("application/json", [b"null"]), ("application/json", [b"true"]),
                    ("application/json", [b"[" + b" " * MAX_REFERENCE_BYTES])]
        for content_type, chunks in variants:
            with self.subTest(content_type=content_type, size=len(chunks[0])):
                client, _, response = self.make_client(content_type=content_type, chunks=chunks)
                with self.assertRaises(WingoResponseError):
                    client.get_regions()
                response.close.assert_called_once()

    def test_configuration_is_validated_before_any_request(self):
        for bad in ({"api_key": ""}, {"api_key": "private\nkey"},
                    {"api_base_url": "http://example.com/api/v1"},
                    {"api_base_url": "https://user:pass@example.com/api/v1"},
                    {"api_base_url": "https://example.com/api/v1?key=private"},
                    {"api_base_url": "https://example.com:invalid/api/v1"},
                    {"account_mode": "staging"}, {"account_mode": []}, {"connect_timeout": 0},
                    {"read_timeout": float("inf")}, {"read_timeout": "invalid"}):
            with self.subTest(bad=bad), self.assertRaises(WingoConfigurationError):
                WingoClient(**{"api_key": "private-test-key", "api_base_url": "https://wingo.example/api/v1", **bad})

    @override_settings(WINGO_API_KEY="configured-test-key", WINGO_API_BASE_URL="https://wingo.example/api/v1",
                       WINGO_ACCOUNT_MODE="production", WINGO_HTTP_CONNECT_TIMEOUT_SECONDS=3,
                       WINGO_HTTP_READ_TIMEOUT_SECONDS=9)
    def test_settings_select_connection_and_account_mode_without_connecting(self):
        with patch("requests.request") as request:
            client = WingoClient.from_settings()
        request.assert_not_called()
        self.assertEqual(client.account_mode, "production")
        self.assertEqual(client.timeout, (3.0, 9.0))

    def test_invalid_region_name_does_not_make_request(self):
        client, http, _ = self.make_client()
        for value in (None, "", " " * 2, 10, "x" * 201):
            with self.subTest(value=value), self.assertRaises(WingoConfigurationError):
                client.get_localities(value)
        http.request.assert_not_called()


class WingoReferenceTests(TestCase):
    def setUp(self):
        self.data = sample()
        self.carrier = reference_client(self.data)

    def stored(self):
        return WingoReferenceData.objects.values().get()

    def test_real_reference_shape_is_saved_with_prices_and_days(self):
        snapshot = refresh_wingo_references(client=self.carrier)
        self.assertEqual((snapshot.pk, len(snapshot.regions), len(snapshot.localities), len(snapshot.tariffs)), (1, 4, 4, 15))
        band = next(row for row in snapshot.tariffs if row["weight_range_id"] == 6)
        self.assertEqual(band["prices"]["standardTbilisi"], "46.00")
        self.assertEqual(band["prices"]["fastTbilisi"], "83.00")
        self.assertEqual(snapshot.weight_ranges[1]["min_weight"], "5.01")
        tbilisi = next(row for row in snapshot.localities if row["group_type"] == "tbilisi")
        self.assertEqual(tbilisi["region_id"], "Tbilisi")
        self.assertEqual(tbilisi["delivery_days"], ["monday", "tuesday", "wednesday", "thursday", "friday"])
        self.assertTrue(tbilisi["address_required"])
        self.assertEqual(len(snapshot.revision), 64)
        self.assertEqual(snapshot.account_mode, "test")

    def test_repeat_refresh_is_canonical_and_records_last_success(self):
        first = refresh_wingo_references(client=self.carrier)
        for key in ("weight_ranges", "delivery_types", "tariffs"):
            self.data[key].reverse()
        for key in ("regions", "localities"):
            self.data["regions"][key].reverse()
        second = refresh_wingo_references(client=reference_client(self.data))
        self.assertEqual(first.revision, second.revision)
        self.assertGreater(second.synced_at, first.synced_at)
        self.assertEqual(WingoReferenceData.objects.count(), 1)

    def test_account_mode_and_new_prices_replace_complete_snapshot(self):
        before = refresh_wingo_references(client=self.carrier)
        self.data["tariffs"][5]["standardTbilisi"] = 47
        self.carrier.account_mode = "production"
        after = refresh_wingo_references(client=self.carrier)
        self.assertNotEqual(before.revision, after.revision)
        self.assertEqual(after.account_mode, "production")
        self.assertEqual(after.tariffs[5]["prices"]["standardTbilisi"], "47.00")

    def test_unknown_unavailable_flags_and_weekdays_are_preserved_independently(self):
        locality = next(iter(self.data["localities"].values()))[0]
        locality.update(active=False, operational=False, addressRequired=None)
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            locality[day] = day == "saturday"
        self.data["tariffs"][0].update(hidden=True, isCustom=True)
        snapshot = refresh_wingo_references(client=self.carrier)
        stored = next(row for row in snapshot.localities if row["id"] == locality["id"])
        self.assertEqual(stored["delivery_days"], ["saturday"])
        self.assertFalse(stored["active"])
        self.assertFalse(stored["operational"])
        self.assertIsNone(stored["address_required"])
        self.assertTrue(snapshot.tariffs[0]["hidden"])
        self.assertTrue(snapshot.tariffs[0]["is_custom"])

    def test_invalid_prices_preserve_previous_snapshot_including_timestamp(self):
        refresh_wingo_references(client=self.carrier)
        before = self.stored()
        for value in (None, True, 0, -1, "NaN", "Infinity", "invalid", "1.234"):
            self.data["tariffs"][5]["standardTbilisi"] = value
            with self.subTest(value=value), self.assertRaises(WingoResponseError):
                refresh_wingo_references(client=self.carrier)
            self.assertEqual(self.stored(), before)

    def test_incomplete_or_mismatched_tariffs_never_replace_snapshot(self):
        refresh_wingo_references(client=self.carrier)
        before = self.stored()
        for kind in ("missing", "duplicate", "weight", "extra", "flag"):
            bad = sample()
            if kind == "missing":
                bad["tariffs"].pop()
            elif kind == "duplicate":
                bad["tariffs"].append(copy.deepcopy(bad["tariffs"][0]))
            elif kind == "weight":
                bad["tariffs"][0]["maxWeight"] = "4.00"
            elif kind == "extra":
                bad["tariffs"][0]["weightRangeId"] = 900
            else:
                bad["tariffs"][0]["hidden"] = "false"
            with self.subTest(kind=kind), self.assertRaises(WingoResponseError):
                refresh_wingo_references(client=reference_client(bad))
            self.assertEqual(self.stored(), before)

    def test_overlapping_gapped_or_duplicate_weight_bands_are_rejected(self):
        for kind in ("overlap", "gap", "duplicate", "mismatched_id", "first"):
            bad = sample()
            if kind == "overlap":
                bad["weight_ranges"][1]["minWeight"] = "5.00"
            elif kind == "gap":
                bad["weight_ranges"][1]["minWeight"] = "5.02"
            elif kind == "duplicate":
                bad["weight_ranges"].append(copy.deepcopy(bad["weight_ranges"][0]))
            elif kind == "mismatched_id":
                bad["weight_ranges"][0]["weightRangeId"] = 9
            else:
                bad["weight_ranges"][0]["minWeight"] = "0.01"
            with self.subTest(kind=kind), self.assertRaises(WingoResponseError):
                refresh_wingo_references(client=reference_client(bad))
        self.assertFalse(WingoReferenceData.objects.exists())

    def test_partial_duplicate_or_wrong_region_localities_preserve_snapshot(self):
        refresh_wingo_references(client=self.carrier)
        before = self.stored()
        for kind in ("missing", "duplicate", "region", "name", "group", "group_type", "weekday", "boolean", "address"):
            bad = sample()
            rows = bad["localities"]["თბილისი"]
            if kind == "missing":
                rows.clear()
            elif kind == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            elif kind == "region":
                rows[0]["regionGe"] = "აჭარა"
            elif kind == "name":
                rows[0]["nameGe"] = "შეცვლილი სახელი"
            elif kind == "group":
                rows[0]["groupType"] = "unknown"
            elif kind == "group_type":
                rows[0]["groupType"] = []
            elif kind == "weekday":
                del rows[0]["monday"]
            elif kind == "boolean":
                rows[0]["operational"] = "false"
            else:
                rows[0]["addressRequired"] = "true"
            with self.subTest(kind=kind), self.assertRaises(WingoResponseError):
                refresh_wingo_references(client=reference_client(bad))
            self.assertEqual(self.stored(), before)

    def test_invalid_region_and_delivery_type_references_are_rejected(self):
        for kind in ("duplicate_region", "unknown_region", "empty_region", "missing_type", "duplicate_type"):
            bad = sample()
            if kind == "duplicate_region":
                bad["regions"]["regions"].append(copy.deepcopy(bad["regions"]["regions"][0]))
            elif kind == "unknown_region":
                bad["regions"]["localities"][0]["regionGe"] = "უცნობი"
            elif kind == "empty_region":
                bad["regions"]["regions"][0]["id"] = ""
            elif kind == "missing_type":
                bad["delivery_types"].pop()
            else:
                bad["delivery_types"].append(copy.deepcopy(bad["delivery_types"][0]))
            with self.subTest(kind=kind), self.assertRaises(WingoResponseError):
                refresh_wingo_references(client=reference_client(bad))
        self.assertFalse(WingoReferenceData.objects.exists())

    def test_late_transport_failure_preserves_all_old_data(self):
        refresh_wingo_references(client=self.carrier)
        before = self.stored()
        self.data["tariffs"][0]["fastTbilisi"] = 20
        self.carrier.get_localities.side_effect = WingoTransportError()
        with self.assertRaises(WingoTransportError):
            refresh_wingo_references(client=self.carrier)
        self.assertEqual(self.stored(), before)

    def test_stale_refresh_cannot_overwrite_completed_refresh_even_if_revision_unchanged(self):
        refresh_wingo_references(client=self.carrier)
        before = self.stored()
        saved = {}

        def newer_refresh():
            refresh_wingo_references(client=reference_client())
            saved.update(self.stored())
            return self.data["tariffs"]

        self.carrier.get_merchant_tariffs.side_effect = newer_refresh
        with self.assertRaises(WingoError):
            refresh_wingo_references(client=self.carrier)
        self.assertEqual(self.stored(), saved)
        self.assertEqual(saved["revision"], before["revision"])
        self.assertGreater(saved["synced_at"], before["synced_at"])

    def test_concurrent_initial_refresh_cannot_overwrite_first_success(self):
        def newer_refresh():
            refresh_wingo_references(client=reference_client())
            return self.data["tariffs"]

        self.carrier.get_merchant_tariffs.side_effect = newer_refresh
        with self.assertRaises(WingoError):
            refresh_wingo_references(client=self.carrier)
        self.assertEqual(WingoReferenceData.objects.count(), 1)

    def test_only_reference_fields_are_persisted_without_sensitive_extra_fields(self):
        self.data["tariffs"][0]["apiKey"] = "private-echo"
        self.data["regions"]["regions"][0]["recipientPhone"] = "private-echo"
        self.data["localities"]["თბილისი"][0]["password"] = "private-echo"
        refresh_wingo_references(client=self.carrier)
        self.assertNotIn("private-echo", json.dumps(self.stored(), default=str))

    def test_singleton_constraint_rejects_another_id(self):
        refresh_wingo_references(client=self.carrier)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WingoReferenceData.objects.create(pk=2, account_mode="test", api_base_url="https://wingo.example/api/v1",
                                             synced_at="2026-11-01T12:00:00Z", revision="other")


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class WingoAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="wingo-test", email="wingo-test@example.com", password="Test-only-123")
        self.client.force_login(self.user)
        self.refresh_url = reverse("admin:commerce_wingoreferencedata_refresh")
        self.list_url = reverse("admin:commerce_wingoreferencedata_changelist")
        self.detail_url = reverse("admin:commerce_wingoreferencedata_change", args=[1])

    def make_read_only(self):
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(
            codename="view_wingoreferencedata", content_type__app_label="commerce"))

    @patch("commerce.wingo_admin.refresh_wingo_references")
    def test_empty_list_can_be_opened_and_confirmation_get_does_not_contact_provider(self, refresh):
        response = self.client.get(self.list_url)
        self.assertContains(response, f'href="{self.refresh_url}"')
        self.assertFalse(response.context["has_add_permission"])
        self.assertContains(self.client.get(self.refresh_url), "Wingo-ს მონაცემების განახლება")
        refresh.assert_not_called()
        self.assertFalse(WingoReferenceData.objects.exists())

    @patch("commerce.wingo_admin.refresh_wingo_references")
    def test_refresh_post_requires_csrf(self, refresh):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.refresh_url).status_code, 403)
        refresh.assert_not_called()

    @patch("commerce.wingo_admin.refresh_wingo_references")
    def test_view_permission_does_not_allow_refresh(self, refresh):
        refresh_wingo_references(client=reference_client())
        self.make_read_only()
        self.assertNotContains(self.client.get(self.list_url), f'href="{self.refresh_url}"')
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)
        self.assertEqual(self.client.get(self.refresh_url).status_code, 403)
        self.assertEqual(self.client.post(self.refresh_url).status_code, 403)
        refresh.assert_not_called()

    @patch("commerce.wingo_admin.refresh_wingo_references")
    def test_successful_refresh_redirects_and_readonly_detail_has_prices_without_save(self, refresh):
        snapshot = refresh_wingo_references(client=reference_client())
        refresh.return_value = snapshot
        response = self.client.post(self.refresh_url, follow=True)
        self.assertContains(response, "Wingo-ს მონაცემები განახლდა")
        refresh.assert_called_once_with()
        response = self.client.get(self.detail_url)
        self.assertContains(response, "46.00 ₾")
        self.assertContains(response, "83.00 ₾")
        self.assertContains(response, "სატესტო")
        self.assertContains(response, "თბილისი — სტანდარტული")
        for name in ("_save", "_continue", "_addanother", "tariffs", "localities"):
            self.assertNotContains(response, f'name="{name}"')
        self.assertNotContains(response, "დღგ-ს ჩათვლით")

    @patch("commerce.wingo_admin.refresh_wingo_references", side_effect=WingoTransportError())
    def test_failed_refresh_shows_safe_error_and_preserves_snapshot(self, refresh):
        refresh_wingo_references(client=reference_client())
        before = WingoReferenceData.objects.values().get()
        response = self.client.post(self.refresh_url, follow=True)
        self.assertContains(response, "არსებული მონაცემები შენარჩუნდა")
        self.assertEqual(WingoReferenceData.objects.values().get(), before)

    def test_direct_detail_post_and_delete_cannot_change_data(self):
        snapshot = refresh_wingo_references(client=reference_client())
        before = WingoReferenceData.objects.values().get()
        self.assertEqual(self.client.post(self.detail_url, {"account_mode": "production", "_save": "Save"}).status_code, 403)
        delete_url = reverse("admin:commerce_wingoreferencedata_delete", args=[snapshot.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)
        self.assertEqual(WingoReferenceData.objects.values().get(), before)

    def test_provider_names_are_escaped_and_gets_never_contact_provider(self):
        data = sample()
        data["regions"]["regions"][0]["nameGe"] = '<script>alert("test")</script>'
        old_name = next(name for name in data["localities"] if name == "აჭარა")
        data["localities"][data["regions"]["regions"][0]["nameGe"]] = data["localities"].pop(old_name)
        new_name = data["regions"]["regions"][0]["nameGe"]
        for row in data["regions"]["localities"]:
            if row["regionGe"] == old_name:
                row["regionGe"] = new_name
        for row in data["localities"][new_name]:
            row["regionGe"] = new_name
        refresh_wingo_references(client=reference_client(data))
        with patch("requests.request", side_effect=AssertionError("No HTTP on admin GET")):
            response = self.client.get(self.detail_url)
            self.assertNotContains(response, '<script>alert("test")</script>')
            self.assertContains(response, "&lt;script&gt;")
            self.assertEqual(self.client.get(self.list_url).status_code, 200)

    @patch("commerce.wingo_admin.refresh_wingo_references")
    def test_unsupported_http_method_cannot_refresh(self, refresh):
        self.assertEqual(self.client.put(self.refresh_url).status_code, 405)
        refresh.assert_not_called()


class WingoCommandTests(TestCase):
    @patch("commerce.management.commands.refresh_wingo_references.refresh_wingo_references")
    def test_command_reports_counts_from_same_refresh_service(self, refresh):
        refresh.return_value = refresh_wingo_references(client=reference_client())
        out = StringIO()
        call_command("refresh_wingo_references", stdout=out)
        refresh.assert_called_once_with()
        self.assertIn("15 წონის დიაპაზონი", out.getvalue())
        self.assertIn("სატესტო", out.getvalue())

    @patch("commerce.management.commands.refresh_wingo_references.refresh_wingo_references", side_effect=WingoTransportError())
    def test_command_failure_is_safe_and_creates_no_snapshot(self, refresh):
        with self.assertRaises(CommandError):
            call_command("refresh_wingo_references", stdout=StringIO())
        self.assertFalse(WingoReferenceData.objects.exists())

    @override_settings(WINGO_API_KEY="")
    def test_missing_credentials_fail_without_network_or_database_write(self):
        with patch("requests.request") as request, self.assertRaises(CommandError):
            call_command("refresh_wingo_references", stdout=StringIO())
        request.assert_not_called()
        self.assertFalse(WingoReferenceData.objects.exists())
