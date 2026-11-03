import copy
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import RedcapReferenceData
from .redcap import (
    MAX_LABEL_BYTES, RedcapClient, RedcapConfigurationError,
    RedcapError, RedcapResponseError, RedcapTransportError, STANDARD_SERVICES,
)
from .redcap_references import refresh_redcap_references, tariff_price


SAMPLES = Path(__file__).with_name("redcap_samples")


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def reference_client():
    client = Mock(spec=RedcapClient)
    client.get_weight_options.return_value = sample("weights.json")
    references = {row["path"]: row["body"] for row in sample("references.json")}
    client.get_locations.return_value = references["/locations"]
    client.get_payment_options.return_value = references["/payment-options"]
    client.get_statuses.return_value = references["/statuses"]
    return client


class RedcapTransportTests(SimpleTestCase):
    def make_client(self, *, body=None, status=200, headers=None, chunks=None):
        response = Mock(status_code=status)
        response.json.return_value = body if body is not None else {"success": True}
        response.headers = headers or {}
        response.iter_content.return_value = chunks or []
        http = Mock()
        http.request.return_value = response
        client = RedcapClient(api_key="private-test-key", api_base_url="https://redcap.example/api/v1",
                              http_client=http)
        return client, http, response

    def test_reference_request_uses_header_timeouts_and_disables_redirects(self):
        client, http, _ = self.make_client(body=sample("weights.json"))
        self.assertEqual(len(client.get_weight_options()["weights"]), 14)
        http.request.assert_called_once_with(
            "GET", "https://redcap.example/api/v1/weight-options",
            headers={"X-API-Key": "private-test-key", "Accept": "application/json"},
            params=None, timeout=(5.0, 15.0), allow_redirects=False,
        )

    def test_redirect_does_not_send_key_to_another_destination(self):
        client, http, response = self.make_client(status=302)
        with self.assertRaises(RedcapResponseError):
            client.get_locations()
        self.assertEqual(http.request.call_count, 1)
        response.close.assert_called_once()

    def test_transport_failure_has_no_automatic_retry_or_private_details(self):
        client, http, _ = self.make_client()
        http.request.side_effect = requests.Timeout("private-test-key user@example.com")
        with self.assertRaises(RedcapTransportError) as caught:
            client.create_order({"delivery_type": "same_day", "payment_type": "transfer",
                                 "delivery_payer": "sender", "item_price": 0})
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertNotIn("private", str(caught.exception))
        http.request.assert_called_once()

    def test_bad_success_response_blocks_resubmission_assumption(self):
        client, _, _ = self.make_client(body={"success": True, "order": {"tracking_number": 123}})
        with self.assertRaises(RedcapResponseError) as caught:
            client.create_order({"delivery_type": "same_day", "payment_type": "transfer",
                                 "delivery_payer": "sender"})
        self.assertTrue(caught.exception.outcome_unknown)

    def test_creation_preserves_tracking_leading_zeroes(self):
        client, _, _ = self.make_client(body={"success": True, "order": {"tracking_number": "000123"}})
        order = client.create_order({"delivery_type": "same_day", "payment_type": "transfer",
                                     "delivery_payer": "sender", "item_price": 0})
        self.assertEqual(order["tracking_number"], "000123")

    def test_cod_extras_and_premium_service_are_not_sent(self):
        for change in ({"item_price": 100}, {"delivery_type": "3hour"},
                       {"additional_services": [1]}, {"delivery_payer": "receiver"}):
            with self.subTest(change=change):
                client, http, _ = self.make_client()
                payload = {"delivery_type": "same_day", "payment_type": "transfer", "delivery_payer": "sender"}
                payload.update(change)
                with self.assertRaises(RedcapConfigurationError):
                    client.create_order(payload)
                http.request.assert_not_called()

    def test_carrier_error_body_is_never_in_staff_error(self):
        client, _, _ = self.make_client(status=422, body={"error": "private phone/key"})
        with self.assertRaises(RedcapResponseError) as caught:
            client.get_weight_options()
        self.assertEqual(caught.exception.status_code, 422)
        self.assertNotIn("private", str(caught.exception))

    def test_batch_statuses_are_read_only_and_require_unique_text_references(self):
        client, http, _ = self.make_client()
        client.get_tracking_statuses(["000001", "000002"])
        self.assertEqual(http.request.call_args.kwargs["json"], {"tracking_numbers": ["000001", "000002"]})
        for values in ([], ["000001", "000001"], [1], [[]], ["x"] * 1001):
            with self.subTest(values=values[:2]):
                with self.assertRaises(RedcapConfigurationError):
                    client.get_tracking_statuses(values)

    def test_pdf_stream_is_validated_and_reference_is_encoded(self):
        client, http, response = self.make_client(
            headers={"Content-Type": "application/pdf"}, chunks=[b"%PDF-1.7\n", b"test"])
        self.assertTrue(client.get_label("ORDER/0001", size="zebra").startswith(b"%PDF-"))
        self.assertTrue(http.request.call_args.args[1].endswith("/ORDER%2F0001/label"))
        self.assertEqual(http.request.call_args.kwargs["params"], {"size": "zebra"})
        response.close.assert_called_once()

    def test_html_json_fake_pdf_and_oversized_labels_are_rejected(self):
        for content_type, chunks in (("text/html", [b"<html>"]),
                                     ("application/json", [b"{}"]),
                                     ("application/pdf", [b"not PDF"]),
                                     ("application/pdf", [b"%PDF-" + b"x" * MAX_LABEL_BYTES])):
            with self.subTest(content_type=content_type, length=len(chunks[0])):
                client, _, response = self.make_client(headers={"Content-Type": content_type}, chunks=chunks)
                with self.assertRaises(RedcapResponseError):
                    client.get_label("000123")
                response.close.assert_called_once()

    def test_configuration_rejects_insecure_url_or_nonfinite_timeouts(self):
        for values in ({"api_base_url": "http://example.com"}, {"api_key": ""},
                       {"api_base_url": "https://user:password@example.com/api"},
                       {"read_timeout": float("nan")}, {"connect_timeout": 0}):
            config = {"api_key": "private", "api_base_url": "https://example.com/api"}
            config.update(values)
            with self.subTest(values=values), self.assertRaises(RedcapConfigurationError):
                RedcapClient(**config)


class RedcapReferenceTests(TestCase):
    def setUp(self):
        self.carrier = reference_client()

    def test_live_reference_shape_is_saved_without_zero_priced_extra_services(self):
        snapshot = refresh_redcap_references(client=self.carrier)
        self.assertEqual((snapshot.pk, len(snapshot.weights), len(snapshot.locations)), (1, 14, 5))
        self.assertEqual(set(snapshot.weights[0]["prices"]), STANDARD_SERVICES)
        self.assertEqual(snapshot.weights[0]["prices"]["same_day"], "10.00")
        self.assertNotIn("cod_enabled", snapshot.payment_options)
        self.assertEqual(len(snapshot.revision), 64)

    def test_refresh_is_repeatable_and_changed_prices_replace_snapshot(self):
        old = refresh_redcap_references(client=self.carrier)
        same = refresh_redcap_references(client=self.carrier)
        self.assertEqual(old.revision, same.revision)
        self.carrier.get_weight_options.return_value["weights"][0]["prices"]["same_day"] = 11
        new = refresh_redcap_references(client=self.carrier)
        self.assertNotEqual(old.revision, new.revision)
        self.assertEqual(RedcapReferenceData.objects.count(), 1)

    def test_incomplete_or_unsafe_tariff_never_overwrites_existing_data(self):
        snapshot = refresh_redcap_references(client=self.carrier)
        before = RedcapReferenceData.objects.values().get()
        original = sample("weights.json")
        variants = []
        for value in (None, 0, -1, "NaN", "Infinity", "1.234", True):
            bad = copy.deepcopy(original)
            bad["weights"][3]["prices"]["same_day"] = value
            variants.append(bad)
        for lower, upper in (("5.01", 10), (4, 10), (5, 5)):
            bad = copy.deepcopy(original)
            bad["weights"][1].update({"from": lower, "to": upper})
            variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad["weights"][1]):
                self.carrier.get_weight_options.return_value = bad
                with self.assertRaises(RedcapResponseError):
                    refresh_redcap_references(client=self.carrier)
                self.assertEqual(RedcapReferenceData.objects.values().get(pk=snapshot.pk), before)

    def test_later_reference_failure_does_not_partially_replace_tariffs(self):
        refresh_redcap_references(client=self.carrier)
        before = RedcapReferenceData.objects.values().get()
        self.carrier.get_weight_options.return_value["weights"][0]["prices"]["same_day"] = 11
        self.carrier.get_statuses.side_effect = RedcapTransportError()
        with self.assertRaises(RedcapTransportError):
            refresh_redcap_references(client=self.carrier)
        self.assertEqual(RedcapReferenceData.objects.values().get(), before)

    def test_older_refresh_cannot_overwrite_another_completed_refresh(self):
        refresh_redcap_references(client=self.carrier)
        another = reference_client()
        another.get_weight_options.return_value["weights"][0]["prices"]["same_day"] = 11
        statuses = self.carrier.get_statuses.return_value

        def concurrent_refresh():
            refresh_redcap_references(client=another)
            return statuses

        self.carrier.get_statuses.side_effect = concurrent_refresh
        with self.assertRaises(RedcapError):
            refresh_redcap_references(client=self.carrier)
        self.assertEqual(RedcapReferenceData.objects.get().weights[0]["prices"]["same_day"], "11.00")

    def test_zone_changes_or_missing_invoice_sender_support_require_review(self):
        for target in ("zone", "payment"):
            carrier = reference_client()
            if target == "zone":
                carrier.get_locations.return_value["locations"][0]["zone_slug"] = "unrecognized"
            else:
                carrier.get_payment_options.return_value["payment_types"] = [{"key": "cash", "name": "Cash"}]
            with self.subTest(target=target), self.assertRaises(RedcapResponseError):
                refresh_redcap_references(client=carrier)
        self.assertFalse(RedcapReferenceData.objects.exists())

    @patch("commerce.redcap.RedcapClient.from_settings", side_effect=AssertionError("No checkout HTTP"))
    def test_local_prices_match_observed_api_boundaries_without_http(self, _):
        snapshot = refresh_redcap_references(client=self.carrier)
        comparisons = [row for row in sample("references.json") if row["path"].startswith("/delivery-options")]
        comparisons = [{"weight": 5, "body": comparisons[0]["body"]}] + sample("boundaries.json")
        for row in comparisons:
            for option in row["body"]["options"]:
                with self.subTest(weight=row["weight"], service=option["slug"]):
                    price = tariff_price(snapshot=snapshot, location_id=1, service=option["slug"], weight=row["weight"])
                    self.assertEqual(price, Decimal(str(option["price"])))

    def test_regional_prices_and_invalid_routes_or_weights(self):
        snapshot = refresh_redcap_references(client=self.carrier)
        for location, service, amount in ((4, "RegionCity", "12"), (5, "sofeli", "13"),
                                          (7, "Magalmtiani", "15"), (6, "Dgesshemog", "12")):
            self.assertEqual(tariff_price(snapshot=snapshot, location_id=location, service=service, weight=3), Decimal(amount))
        for location, service, weight in ((1, "RegionCity", 3), (5, "same_day", 3), (1, "3hour", 3),
                                          (1, "same_day", 0), (1, "same_day", 1001), (1, "same_day", "NaN")):
            with self.subTest(location=location, service=service, weight=weight), self.assertRaises(RedcapConfigurationError):
                tariff_price(snapshot=snapshot, location_id=location, service=service, weight=weight)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class RedcapAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="redcap-test", email="redcap-test@example.com", password="Test-only-123")
        self.client.force_login(self.user)
        self.url = reverse("admin:commerce_redcapreferencedata_refresh")

    def test_empty_list_has_refresh_button_without_add_or_delete(self):
        response = self.client.get(reverse("admin:commerce_redcapreferencedata_changelist"))
        self.assertContains(response, f'href="{self.url}"')
        self.assertFalse(response.context["has_add_permission"])
        self.assertFalse(RedcapReferenceData.objects.exists())

    @patch("commerce.redcap_admin.refresh_redcap_references")
    def test_confirmation_get_never_calls_carrier_and_post_requires_csrf(self, refresh):
        self.assertContains(self.client.get(self.url), "ტარიფების განახლება")
        refresh.assert_not_called()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url).status_code, 403)
        refresh.assert_not_called()

    @patch("commerce.redcap_admin.refresh_redcap_references")
    def test_read_only_staff_cannot_refresh(self, refresh):
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename="view_redcapreferencedata", content_type__app_label="commerce"))
        self.assertEqual(self.client.get(reverse("admin:commerce_redcapreferencedata_changelist")).status_code, 200)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        refresh.assert_not_called()

    @patch("commerce.redcap_admin.refresh_redcap_references")
    def test_post_refresh_and_readonly_tariff_table(self, refresh):
        snapshot = refresh_redcap_references(client=reference_client())
        refresh.return_value = snapshot
        self.assertEqual(self.client.post(self.url).status_code, 302)
        refresh.assert_called_once_with()
        response = self.client.get(reverse("admin:commerce_redcapreferencedata_change", args=[1]))
        self.assertContains(response, "10.00 ₾")
        self.assertNotContains(response, 'name="weights"')
