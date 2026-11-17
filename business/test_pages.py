from copy import deepcopy
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from .pages import build_page_report, page_request, parse_pages
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE, report

PERIOD = ReportPeriod(date(2026, 11, 1), date(2026, 11, 17))


class PagesContractTests(SimpleTestCase):
    def test_host_public_allowlist_and_duration_denominator(self):
        request = page_request(PERIOD)
        self.assertIn("flexdrive.ge", str(request["dimensionFilter"]))
        self.assertEqual(request["limit"], "20")
        body = report(request, [("/", 20, 8, 5, "125.5"), ("/catalog/part-1", 3, 2, 0, 0)])
        body["rowCount"] = 30
        parsed = parse_pages(body)
        self.assertEqual(parsed["row_count"], 30)
        self.assertEqual(parsed["rows"][0]["average_active_seconds"], 25.1)
        self.assertIsNone(parsed["rows"][1]["average_active_seconds"])

    def test_private_or_query_paths_and_invalid_metrics_never_escape(self):
        spec = page_request(PERIOD)
        for path in ("/checkout/success/secret", "/profile/orders/secret", "/business", "/catalog/part?token=secret", "/catalog/part%3Ftoken=secret", "//example.com", "/catalog/a/b"):
            with self.assertRaises(ValueError):
                parse_pages(report(spec, [(path, 1, 1, 1, 3)]))
        for bad in ("NaN", "Infinity", -1, 2**53):
            with self.assertRaises(ValueError):
                parse_pages(report(spec, [("/", 1, 1, 1, bad)]))
        with self.assertRaises(ValueError):
            parse_pages(report(spec, [("/", "1.5", 1, 1, 3)]))
        duplicate = report(spec, [("/", 1, 1, 1, 3), ("/", 1, 1, 1, 3)])
        with self.assertRaises(ValueError):
            parse_pages(duplicate)

    def test_empty_thresholded_and_malformed_responses(self):
        body = report(page_request(PERIOD), subjectToThresholding=True)
        self.assertEqual(parse_pages(body)["rows"], [])
        self.assertTrue(parse_pages(body)["warnings"])
        malformed = deepcopy(body)
        malformed["metricHeaders"][0] = {"name": "eventCount"}
        with self.assertRaises(ValueError):
            parse_pages(malformed)


@override_settings(CACHES=LOCAL_CACHE, BUSINESS_GA4_CREDENTIALS_JSON="reader", BUSINESS_GA4_CREDENTIALS_FILE="")
class PagesCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("business.pages._read", return_value={"rows": [], "row_count": 0})
    def test_cache_and_missing_config(self, read):
        first = build_page_report(PERIOD)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(build_page_report(PERIOD), first)
        read.assert_called_once()
        with override_settings(BUSINESS_GA4_CREDENTIALS_JSON=""):
            self.assertEqual(build_page_report(PERIOD)["status"], "not_configured")

    @patch("business.pages._read", side_effect=ValueError("PRIVATE CREDENTIAL"))
    def test_failures_are_not_zero_and_secrets_never_leak(self, read):
        answer = build_page_report(PERIOD)
        self.assertEqual(answer["status"], "unavailable")
        self.assertNotIn("rows", answer)
        self.assertNotIn("PRIVATE", str(answer))
        build_page_report(PERIOD)
        read.assert_called_once()

    @patch("business.pages._read", return_value={"rows": [{"path": "/", "views": 5}], "row_count": 1})
    def test_stale_page_report_keeps_original_timestamp(self, read):
        first = build_page_report(PERIOD)
        from .marketing import MetaUnavailable
        from django.core.cache import cache
        from hashlib import sha256
        identity = sha256("reader\0".encode()).hexdigest()[:16]
        cache.delete(f"business:pages:v1:{identity}:{PERIOD.start}:{PERIOD.end}")
        read.side_effect = MetaUnavailable("quota")
        stale = build_page_report(PERIOD)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["fetched_at"], first["fetched_at"])
        self.assertEqual(stale["rows"], first["rows"])
