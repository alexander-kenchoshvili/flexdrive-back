from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from .pages import _read, build_page_report, detail_requests, is_public_path, page_request, parse_detail, parse_pages
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE, report

PERIOD = ReportPeriod(date(2026, 11, 1), date(2026, 11, 17))


class PagesContractTests(SimpleTestCase):
    def test_host_public_allowlist_and_duration_denominator(self):
        request = page_request(PERIOD)
        self.assertIn("flexdrive.ge", str(request["dimensionFilter"]))
        self.assertEqual(request["limit"], "20")
        body = report(request, [("/", 20, 8, 5, "125.5", 9), ("/catalog/part-1", 3, 2, 0, 0, 2)])
        body["rowCount"] = 30
        parsed = parse_pages(body)
        self.assertEqual(parsed["row_count"], 30)
        self.assertEqual(parsed["rows"][0]["average_active_seconds"], 25.1)
        self.assertIsNone(parsed["rows"][1]["average_active_seconds"])

    def test_private_or_query_paths_and_invalid_metrics_never_escape(self):
        spec = page_request(PERIOD)
        for path in ("/checkout/success/secret", "/profile/orders/secret", "/business", "/catalog/part?token=secret", "/catalog/part%3Ftoken=secret", "//example.com", "/catalog/a/b"):
            with self.assertRaises(ValueError):
                parse_pages(report(spec, [(path, 1, 1, 1, 3, 1)]))
        for bad in ("NaN", "Infinity", -1, 2**53):
            with self.assertRaises(ValueError):
                parse_pages(report(spec, [("/", 1, 1, 1, bad, 1)]))
        with self.assertRaises(ValueError):
            parse_pages(report(spec, [("/", "1.5", 1, 1, 3, 1)]))
        duplicate = report(spec, [("/", 1, 1, 1, 3, 1), ("/", 1, 1, 1, 3, 1)])
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
        identity = sha256("reader\0".encode()).hexdigest()[:16]
        filters = sha256(json.dumps(["", 1, ""], ensure_ascii=True).encode()).hexdigest()[:20]
        cache.delete(f"business:pages:v2:{identity}:{PERIOD.start}:{PERIOD.end}:{filters}")
        read.side_effect = MetaUnavailable("quota")
        stale = build_page_report(PERIOD)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["fetched_at"], first["fetched_at"])
        self.assertEqual(stale["rows"], first["rows"])

    @patch("business.pages._read", return_value={"rows": [], "row_count": 0})
    def test_filter_page_path_and_credential_caches_are_independent(self, read):
        for options in ({}, {"query": "Subaru"}, {"page": 2}, {"path": "/blogs/106-subaru"}):
            build_page_report(PERIOD, **options)
            build_page_report(PERIOD, **options)
        self.assertEqual(read.call_count, 4)
        with override_settings(BUSINESS_GA4_CREDENTIALS_JSON="different-reader"):
            build_page_report(PERIOD)
        self.assertEqual(read.call_count, 5)


class PageDetailTests(SimpleTestCase):
    def test_public_blog_list_article_and_categories_only(self):
        for path in ("/blogs", "/blogs/", "/blogs/106-subaru", "/catalog/category/body", "/catalog/part"):
            self.assertTrue(is_public_path(path), path)
        for path in ("/blogs/secret", "/blogs/106-secret?token=x", "/catalog/%25253Ftoken=x", "/catalog/%2e%2e",
                     "/blogs/106-x%2Fy", "/catalog/category%2Fa", "/catalog/x%0A", "/business", "/profile", "https://evil.test/"):
            self.assertFalse(is_public_path(path), path)
            with self.assertRaises(ValueError):
                detail_requests(PERIOD, path)

    def test_summary_and_facebook_users_are_not_summed_from_sources_or_days(self):
        specs = detail_requests(PERIOD, "/blogs/106-subaru")
        for spec in specs:
            self.assertIn("flexdrive.ge", str(spec["dimensionFilter"]))
            self.assertIn("/blogs/106-subaru", str(spec["dimensionFilter"]))
        bodies = [report(specs[0], [(28, 20, 19, 1484, 22)]),
                  report(specs[1], [("20261101", 20, 18, 17, 1000, 18), ("20261102", 8, 8, 8, 484, 8)]),
                  report(specs[2], [("facebook.com / referral", 16, 12, 11, 700, 12),
                                    ("l.facebook.com / referral", 10, 10, 9, 492, 10)]),
                  report(specs[3], [(26, 18, 17, 1192, 20)])]
        parsed = parse_detail(bodies, PERIOD)
        self.assertEqual(parsed["summary"]["users"], 20)
        self.assertEqual(parsed["facebook"]["users"], 18)
        self.assertEqual(parsed["summary"]["sessions"], 22)
        self.assertEqual(len(parsed["daily"]), 17)
        self.assertEqual(parsed["daily"][2]["views"], 0)
        self.assertIsNone(parsed["daily"][2]["average_active_seconds"])
        self.assertAlmostEqual(parsed["summary"]["average_active_seconds"], 1484 / 19)

    def test_successful_empty_detail_zero_is_distinct_from_missing_or_malformed(self):
        specs = detail_requests(PERIOD, "/blogs/106-subaru")
        bodies = [report(spec) for spec in specs]
        bodies[0] = {"kind": "analyticsData#runReport", "metadata": {"timeZone": "Asia/Tbilisi"}}
        self.assertEqual(parse_detail(bodies, PERIOD)["summary"]["users"], 0)
        for index, bad in ((0, {}), (1, report(specs[1], [("20271201", 1, 1, 1, 1, 1)])),
                           (2, report(specs[2], [("google / organic", -1, 1, 1, 1, 1)]))):
            with self.subTest(index=index), self.assertRaises((ValueError, KeyError)):
                changed = deepcopy(bodies); changed[index] = bad
                parse_detail(changed, PERIOD)


class PageReaderTests(SimpleTestCase):
    @patch("business.pages._credentials", return_value=object())
    @patch("business.pages.AuthorizedSession")
    @patch("business.pages._batch")
    def test_title_search_discovers_paths_then_reads_all_events_and_keeps_counts(self, batch, session, credentials):
        path = "/blogs/106-subaru"
        def answer(connection, specs):
            spec = specs[0]
            dimensions = [item["name"] for item in spec["dimensions"]]
            scope = str(spec["dimensionFilter"])
            self.assertIn("flexdrive.ge", scope)
            if "pageTitle" in scope:
                return [report(spec, [(path, 3)])]
            if dimensions == ["pagePath", "pageTitle"]:
                return [report(spec, [(path, "Subaru <img src=x>", 20), (path, "Old title", 8)])]
            self.assertNotIn("pageTitle", scope)
            self.assertIn(path, scope)
            return [report(spec, [(path, 28, 20, 19, 1484, 22)])]
        batch.side_effect = answer
        result = _read(PERIOD, query="Subaru")
        self.assertEqual(batch.call_count, 3)
        self.assertEqual(result["rows"][0]["users"], 20)
        self.assertEqual(result["rows"][0]["title"], "Subaru <img src=x>")

    @patch("business.pages._credentials", return_value=object())
    @patch("business.pages.AuthorizedSession")
    @patch("business.pages._batch")
    def test_broad_empty_and_private_searches_do_not_become_partial_results(self, batch, session, credentials):
        def empty(connection, specs):
            return [report(specs[0])]
        batch.side_effect = empty
        self.assertEqual(_read(PERIOD, query="missing")["row_count"], 0)
        self.assertEqual(batch.call_count, 1)
        def broad(connection, specs):
            result = report(specs[0]); result["rowCount"] = 501; return [result]
        batch.side_effect = broad
        result = _read(PERIOD, query="a")
        self.assertTrue(result["search_too_broad"])
        self.assertNotIn("row_count", result)
        batch.side_effect = lambda connection, specs: [report(specs[0], [("/checkout/success/secret", 1)])]
        with self.assertRaises(ValueError):
            _read(PERIOD, query="secret")

    @patch("business.pages._credentials", return_value=object())
    @patch("business.pages.AuthorizedSession")
    @patch("business.pages._batch")
    def test_pagination_is_remote_and_optional_title_failure_keeps_valid_metrics(self, batch, session, credentials):
        def answer(connection, specs):
            spec = specs[0]
            if len(spec["dimensions"]) == 2:
                from .analytics import AnalyticsUnavailable
                raise AnalyticsUnavailable("quota")
            self.assertEqual(spec["offset"], "20")
            result = report(spec, [("/blogs/106-subaru", 28, 20, 19, 1484, 22)])
            result["rowCount"] = 21
            return [result]
        batch.side_effect = answer
        result = _read(PERIOD, page=2)
        self.assertEqual(result["row_count"], 21)
        self.assertIsNone(result["rows"][0]["title"])


@override_settings(CACHES=LOCAL_CACHE)
class PageInputAccessTests(SimpleTestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory
        self.factory = APIRequestFactory()
        from django.core.cache import caches
        caches["throttling"].clear()
        self.user = SimpleNamespace(pk=101, is_authenticated=True, is_active=True, is_staff=True, has_perm=lambda permission: True)

    def call_view(self, values, *, user=True):
        from rest_framework.test import force_authenticate
        from .views import BusinessPagesView
        request = self.factory.get("/api/business/pages/", values)
        if user:
            force_authenticate(request, user=self.user)
        return BusinessPagesView.as_view()(request)

    @patch("business.pages.build_page_report", return_value={"status": "ready"})
    def test_access_validation_and_selected_path_contract(self, build):
        self.assertEqual(self.call_view({}, user=False).status_code, 401)
        self.user.has_perm = lambda permission: False
        self.assertEqual(self.call_view({}).status_code, 403)
        self.user.has_perm = lambda permission: True
        for invalid in ({"path": "/checkout/success/secret"}, {"q": "x" * 121}, {"page": 0}, {"page": "bad"},
                        {"start": "2026-11-01"}, {"start": "2027-01-01", "end": "2027-01-02"}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.call_view(invalid).status_code, 400)
        build.assert_not_called()
        self.assertEqual(self.call_view({"start": str(PERIOD.start), "end": str(PERIOD.end), "q": "Subaru", "page": 2}).status_code, 200)
        build.assert_called_once_with(PERIOD, query="Subaru", page=2, path="")
        build.reset_mock()
        self.assertEqual(self.call_view({"path": "/blogs/106-subaru"}).status_code, 200)
        self.assertEqual(build.call_args.kwargs["path"], "/blogs/106-subaru")
