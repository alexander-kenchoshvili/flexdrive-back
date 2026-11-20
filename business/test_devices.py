from copy import deepcopy
from datetime import date
from hashlib import sha256
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .devices import build_device_report, device_request, parse_devices
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE, report

PERIOD = ReportPeriod(date(2026, 11, 1), date(2026, 11, 20))


class DeviceContractTests(SimpleTestCase):
    def test_fixed_host_and_categories_counts_and_independent_shares(self):
        spec = device_request(PERIOD)
        self.assertIn("flexdrive.ge", str(spec["dimensionFilter"]))
        self.assertIn("notExpression", str(spec["dimensionFilter"]))
        self.assertIn("manager-fd", str(spec["dimensionFilter"]))
        self.assertEqual(spec["limit"], "10")
        parsed = parse_devices(report(spec, [("mobile", 75, 2), ("desktop", 25, 2)]))
        mobile, desktop, tablet, other = parsed["rows"]
        self.assertEqual(parsed["totals"], {"sessions": 100, "purchases": 4})
        self.assertEqual((mobile["session_share"], mobile["purchase_share"]), (75, 50))
        self.assertEqual((desktop["session_share"], desktop["purchase_share"]), (25, 50))
        self.assertEqual((tablet["sessions"], other["purchases"]), (0, 0))

    def test_unknown_categories_are_grouped_without_raw_labels_and_zero_has_no_share(self):
        spec = device_request(PERIOD)
        parsed = parse_devices(report(spec, [("PRIVATE LABEL", 2, 0), ("(not set)", 3, 0)]))
        self.assertNotIn("PRIVATE", str(parsed))
        self.assertEqual(parsed["rows"][3]["sessions"], 5)
        self.assertEqual(parsed["rows"][3]["session_share"], 100)
        self.assertTrue(all(row["purchase_share"] is None for row in parsed["rows"]))
        empty = parse_devices(report(spec, subjectToThresholding=True))
        self.assertTrue(empty["warnings"])
        self.assertEqual(empty["totals"], {"sessions": 0, "purchases": 0})
        self.assertTrue(all(row["session_share"] is None for row in empty["rows"]))

    def test_invalid_metrics_headers_duplicates_and_truncated_rows_are_rejected(self):
        spec = device_request(PERIOD)
        for bad in ("NaN", "Infinity", -1, "1.5", 2**53):
            with self.assertRaises((ValueError, ArithmeticError)):
                parse_devices(report(spec, [("mobile", bad, 1)]))
        with self.assertRaises(ValueError):
            parse_devices(report(spec, [("mobile", 1, 0), ("mobile", 1, 0)]))
        body = report(spec, [("mobile", 1, 0)])
        incomplete = deepcopy(body)
        incomplete["rowCount"] = 11
        wrong = deepcopy(body)
        wrong["metricHeaders"][1]["name"] = "eventCount"
        for malformed in (incomplete, wrong):
            with self.assertRaises(ValueError):
                parse_devices(malformed)


@override_settings(CACHES=LOCAL_CACHE, BUSINESS_GA4_CREDENTIALS_JSON="reader", BUSINESS_GA4_CREDENTIALS_FILE="")
class DeviceCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("business.devices._read")
    def test_cache_configuration_and_failure_distinct_from_zero(self, read):
        read.return_value = parse_devices(report(device_request(PERIOD)))
        first = build_device_report(PERIOD)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(build_device_report(PERIOD), first)
        read.assert_called_once_with(PERIOD)
        with override_settings(BUSINESS_GA4_CREDENTIALS_JSON=""):
            self.assertEqual(build_device_report(PERIOD)["status"], "not_configured")
        cache.clear()
        read.side_effect = ValueError("PRIVATE CREDENTIAL")
        failed = build_device_report(PERIOD)
        self.assertEqual(failed["status"], "unavailable")
        self.assertNotIn("rows", failed)
        self.assertNotIn("PRIVATE", str(failed))
        self.assertNotIn("Meta", str(failed))
        build_device_report(PERIOD)
        self.assertEqual(read.call_count, 2)

    @patch("business.devices._read")
    def test_stale_retains_original_counts_and_timestamp(self, read):
        read.return_value = parse_devices(report(device_request(PERIOD), [("mobile", 10, 1)]))
        first = build_device_report(PERIOD)
        identity = sha256("reader\0".encode()).hexdigest()[:16]
        cache.delete(f"business:devices:v1:{identity}:{PERIOD.start}:{PERIOD.end}")
        read.side_effect = ValueError("bad response")
        stale = build_device_report(PERIOD)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["fetched_at"], first["fetched_at"])
        self.assertEqual(stale["rows"], first["rows"])


@override_settings(CACHES=LOCAL_CACHE)
class DeviceAccessTests(TestCase):
    def setUp(self):
        caches["throttling"].clear()
        self.client = APIClient()
        self.owner = get_user_model().objects.create_superuser("device-owner", "device@example.test", "test-password")

    @patch("business.devices.build_device_report", return_value={"status": "ready"})
    def test_private_business_session_dates_and_no_store(self, build):
        url = reverse("business:devices")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 401)
        build.assert_not_called()
        with patch("business.views.validate_recaptcha", return_value=True):
            self.client.post(reverse("business:login"), {"username": "device-owner", "password": "test-password", "recaptcha_token": "mock"})
        for query in ({"start": "bad", "end": "bad"}, {"start": "2026-01-01"},
                      {"start": "2027-01-01", "end": "2027-01-02"},
                      {"start": "2025-01-01", "end": "2026-11-01"}):
            self.assertEqual(self.client.get(url, query).status_code, 400)
        build.assert_not_called()
        answer = self.client.get(url, {"start": str(PERIOD.start), "end": str(PERIOD.end), "hostname": "attacker", "property_id": "1"})
        self.assertEqual(answer.status_code, 200)
        self.assertIn("no-store", answer["Cache-Control"])
        build.assert_called_once_with(PERIOD)
