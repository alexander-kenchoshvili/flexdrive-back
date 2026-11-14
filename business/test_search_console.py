from datetime import date, datetime, timezone as utc
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests.exceptions import Timeout
from rest_framework.test import APIClient

from .marketing import MetaUnavailable
from .reports import ReportPeriod
from .search_console import (PROPERTY, SCOPE, URL, _credentials_for_search, _query, _read,
                             available_period, build_search_console_report, parse_rows, query_body)
from .test_analytics import LOCAL_CACHE, response

PERIOD = ReportPeriod(date(2026, 11, 1), date(2026, 11, 14))
NOW = datetime(2026, 11, 14, 12, tzinfo=utc.utc)


def row(keys=(), **values):
    return {"keys": list(keys), "clicks": 2, "impressions": 100, "ctr": 0.02, "position": 12.5, **values}


class SearchContractTests(SimpleTestCase):
    @patch("business.search_console.timezone.now", return_value=NOW)
    def test_final_dates_pt_lag_retention_and_empty_range(self, now):
        effective, first, last = available_period(PERIOD)
        self.assertEqual(effective, ReportPeriod(date(2026, 11, 1), date(2026, 11, 11)))
        self.assertEqual(first, date(2025, 7, 14))
        self.assertEqual(last, date(2026, 11, 11))
        self.assertIsNone(available_period(ReportPeriod(date(2026, 11, 13), date(2026, 11, 14)))[0])
        now.return_value = datetime(2026, 11, 14, 1, tzinfo=utc.utc)  # Still Nov13 PT.
        self.assertEqual(available_period(PERIOD)[2], date(2026, 11, 10))

    @patch("business.search_console._credentials")
    def test_existing_identity_uses_only_readonly_search_scope(self, credentials):
        _credentials_for_search()
        credentials.return_value.with_scopes.assert_called_once_with([SCOPE])
        self.assertEqual(PROPERTY, "sc-domain:flexdrive.ge")
        self.assertIn("sc-domain%3Aflexdrive.ge", URL)
        for dimensions, aggregation, limit in [((), "byProperty", 1), (("date",), "byProperty", 366), (("query",), "byProperty", 50), (("page",), "byPage", 50)]:
            body = query_body(PERIOD, dimensions)
            self.assertEqual((body["dataState"], body["type"], body["aggregationType"], body["rowLimit"]), ("final", "web", aggregation, limit))

    def test_counts_ctr_position_and_valid_empty(self):
        body = query_body(PERIOD)
        self.assertEqual(parse_rows({"rows": [row()]}, body)[0]["position"], 12.5)
        self.assertEqual(parse_rows({"rows": [row(impressions=0, clicks=0, ctr=0, position=0)]}, body)[0]["position"], None)
        self.assertEqual(parse_rows({}, body), [])
        for values in ({"ctr": 2}, {"position": 0}, {"clicks": "NaN"}, {"clicks": -1}, {"clicks": True}, {"impressions": 1.5}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                parse_rows({"rows": [row(**values)]}, body)

    def test_rows_cannot_expand_to_foreign_or_unsafe_page_and_duplicate_dates(self):
        body = query_body(PERIOD, ("page",))
        for page in ("javascript:alert(1)", "https://flexdrive.ge.evil.test/", "https://other.ge/", "https://user:secret@flexdrive.ge/"):
            with self.assertRaises(ValueError):
                parse_rows({"rows": [row((page,))]}, body)
        self.assertEqual(parse_rows({"rows": [row(("https://www.flexdrive.ge/product",))]}, body)[0]["page"], "https://www.flexdrive.ge/product")
        body = query_body(PERIOD, ("date",))
        for rows in ([row(("2026-12-01",))], [row(("2026-11-01",)), row(("2026-11-01",))]):
            with self.assertRaises(ValueError):
                parse_rows({"rows": rows}, body)

    def test_transport_exact_url_read_query_and_error_redaction(self):
        session = MagicMock()
        session.post.return_value = response({"rows": [row()], "responseAggregationType": "byProperty"})
        self.assertEqual(_query(session, query_body(PERIOD))[0]["clicks"], 2)
        self.assertEqual(session.post.call_args.args, (URL,))
        self.assertFalse(session.post.call_args.kwargs["allow_redirects"])
        for failure in (response({"error": {"message": "PRIVATE_TOKEN", "errors": [{"reason": "accessNotConfigured"}]}}, status=403), response({}, status=429), Timeout("PRIVATE_TOKEN")):
            session.post.side_effect = failure if isinstance(failure, Exception) else None
            session.post.return_value = failure
            with self.assertRaises(MetaUnavailable) as caught:
                _query(session, query_body(PERIOD))
            self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))

    @patch("business.search_console._credentials_for_search", return_value=object())
    @patch("business.search_console.AuthorizedSession")
    @patch("business.search_console._query")
    def test_top_tables_do_not_supply_totals_or_weighted_averages(self, query, transport, credentials):
        query.side_effect = [[row(clicks=20, impressions=500, ctr=0.04, position=9.5)], [row(clicks=10)],
                             [row(("2026-11-01",))], [row(("ფარი",))], [row(("https://flexdrive.ge/",))]]
        result = _read(PERIOD, date(2025, 7, 14))
        self.assertEqual(result["summary"]["clicks"], 20)
        self.assertEqual(result["summary"]["position"], 9.5)
        self.assertEqual(len(result["queries"]["rows"]), 1)
        self.assertEqual(query.call_count, 5)

    @patch("business.search_console._credentials_for_search", return_value=object())
    @patch("business.search_console.AuthorizedSession")
    @patch("business.search_console._query")
    def test_partial_failure_preserves_summary_but_never_fakes_query_zeros(self, query, transport, credentials):
        query.side_effect = [[row()], [row()], [], MetaUnavailable("access"), []]
        result = _read(PERIOD, date(2025, 7, 14))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary"]["clicks"], 2)
        self.assertEqual(result["queries"], {"status": "unavailable"})


@override_settings(CACHES=LOCAL_CACHE, BUSINESS_GA4_CREDENTIALS_JSON="test-reader", BUSINESS_GA4_CREDENTIALS_FILE="")
@patch("business.search_console.timezone.now", return_value=NOW)
class SearchCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("business.search_console._read", return_value={"status": "ready", "summary": row()})
    def test_cache_credential_change_and_no_provider_call_for_recent_only(self, read, now):
        first = build_search_console_report(PERIOD)
        self.assertEqual(build_search_console_report(PERIOD), first)
        read.assert_called_once()
        with override_settings(BUSINESS_GA4_CREDENTIALS_JSON="different-reader"):
            build_search_console_report(PERIOD)
        self.assertEqual(read.call_count, 2)
        self.assertEqual(build_search_console_report(ReportPeriod(date(2026,11,13),date(2026,11,14)))["status"], "range_limit")
        self.assertEqual(read.call_count, 2)

    @patch("business.search_console._read", side_effect=MetaUnavailable("access"))
    def test_denied_connection_is_not_zero_and_retry_is_bounded(self, read, now):
        first = build_search_console_report(PERIOD)
        self.assertEqual(first["status"], "unavailable")
        self.assertNotIn("summary", first)
        self.assertEqual(build_search_console_report(PERIOD), first)
        read.assert_called_once()

    @patch("business.search_console._read", return_value={"status": "ready", "summary": row()})
    def test_last_good_is_dated_stale_instead_of_current(self, read, now):
        first = build_search_console_report(PERIOD)
        original = cache.get
        with patch("business.marketing.cache.get", side_effect=lambda key: None if key.endswith(":2026-11-11") else original(key)):
            read.side_effect = MetaUnavailable("quota")
            stale = build_search_console_report(PERIOD)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["fetched_at"], first["fetched_at"])
        self.assertEqual(stale["summary"], first["summary"])


@override_settings(CACHES=LOCAL_CACHE)
class SearchAccessTests(TestCase):
    def setUp(self):
        from .throttling import BusinessLoginIpThrottle, BusinessLoginAccountThrottle
        caches["throttling"].clear()
        BusinessLoginIpThrottle.cache.clear()
        BusinessLoginAccountThrottle.cache.clear()
        self.client = APIClient()
        self.owner = get_user_model().objects.create_superuser("gsc-owner", "gsc@example.test", "test-password")

    def tearDown(self):
        from .throttling import BusinessLoginIpThrottle, BusinessLoginAccountThrottle
        BusinessLoginIpThrottle.cache.clear()
        BusinessLoginAccountThrottle.cache.clear()

    @patch("business.search_console.build_search_console_report", return_value={"status": "not_configured"})
    def test_business_session_date_validation_fixed_scope_and_no_store(self, build):
        url = reverse("business:search-console")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 401)
        build.assert_not_called()
        with patch("business.views.validate_recaptcha", return_value=True):
            self.client.post(reverse("business:login"), {"username": "gsc-owner", "password": "test-password", "recaptcha_token": "mock"})
        for query in ({"start":"2026-01-01"}, {"start":"2027-01-01","end":"2027-01-02"}, {"start":"2024-01-01","end":"2026-01-01"}):
            self.assertEqual(self.client.get(url, query).status_code, 400)
        build.assert_not_called()
        result = self.client.get(url, {"start":"2026-11-01","end":"2026-11-14", "siteUrl":"sc-domain:foreign.ge"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
        build.assert_called_once_with(PERIOD)
