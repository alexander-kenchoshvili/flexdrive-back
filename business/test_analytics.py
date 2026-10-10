from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests.exceptions import Timeout
from rest_framework.test import APIClient

from .analytics import (
    AnalyticsUnavailable, BATCH_URL, READER_EMAIL, SCOPE, _credentials,
    build_analytics_report, report_definitions,
)
from .reports import ReportPeriod

PERIOD = ReportPeriod(date(2026, 10, 1), date(2026, 10, 3))
LOCAL_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ga4-tests"},
               "throttling": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ga4-throttle-tests"}}


def report(definition, rows=(), **metadata):
    dims, metrics = definition["dimensions"], definition["metrics"]
    return {"dimensionHeaders": dims, "metricHeaders": metrics, "metadata": {"timeZone": "Asia/Tbilisi", **metadata},
            "rowCount": len(rows), "rows": [
                {"dimensionValues": [{"value": str(value)} for value in row[:len(dims)]],
                 "metricValues": [{"value": str(value)} for value in row[len(dims):]]} for row in rows]}


def response(data=None, status=200):
    obj = MagicMock(status_code=status)
    obj.json.return_value = data
    return obj


@override_settings(BUSINESS_GA4_CREDENTIALS_FILE="test-reader.json", BUSINESS_GA4_CREDENTIALS_JSON="", CACHES=LOCAL_CACHE)
class AnalyticsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.auth = patch("business.analytics._credentials", return_value=object())
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.transport = patch("business.analytics.AuthorizedSession")
        self.factory = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.session = self.factory.return_value.__enter__.return_value
        self.core = report_definitions(PERIOD)
        self.search = report_definitions(PERIOD, search=True)

    def answers(self, *, empty=False):
        core = [report(self.core[0], [] if empty else [(7, 10, 4, 15)]),
                report(self.core[1], [] if empty else [("20261002", 10, 7)]),
                report(self.core[2], [] if empty else [("google / organic", 8, 3), ("(direct) / (none)", 2, 1)])]
        search = [report(self.search[0], [] if empty else [("results", 6, "12.5"), ("no_results", 2, "0")]),
                  report(self.search[1], [] if empty else [("ფარი", "results", 6, "12.5"), ("ბამპერი", "no_results", 2, "0")])]
        return response({"reports": core}), response({"reports": search})

    def test_real_rows_summary_unique_users_and_search_contract(self):
        self.session.post.side_effect = self.answers()
        result = build_analytics_report(PERIOD)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["summary"]["totalUsers"], 7)
        self.assertEqual(result["daily"], [
            {"date": "2026-10-01", "sessions": 0, "users": 0},
            {"date": "2026-10-02", "sessions": 10, "users": 7},
            {"date": "2026-10-03", "sessions": 0, "users": 0}])
        self.assertEqual(result["search"]["total"], 8)
        self.assertEqual(result["search"]["no_results"], 2)
        self.assertEqual(result["search"]["terms"][0]["average_results"], 12.5)
        self.assertEqual(result["report_timezone"], "Asia/Tbilisi")
        for call in self.session.post.call_args_list:
            self.assertEqual(call.args, (BATCH_URL,))
            self.assertEqual(call.kwargs["timeout"], (3, 8))
            self.assertFalse(call.kwargs["allow_redirects"])
            for body in call.kwargs["json"]["requests"]:
                self.assertIn('"value": "flexdrive.ge"', __import__("json").dumps(body))
                self.assertNotIn("localhost", str(body))
                self.assertIn("notExpression", str(body))
        for body in self.session.post.call_args_list[1].kwargs["json"]["requests"]:
            self.assertIn("search_tracking_version", str(body))
            self.assertIn("'value': '2'", str(body))
            self.assertIn("'value': 'search'", str(body))
            self.assertNotIn("view_search_results", str(body))

    def test_successful_empty_is_distinct_from_unconfigured_and_failure(self):
        self.session.post.side_effect = self.answers(empty=True)
        result = build_analytics_report(PERIOD)
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["summary"]["sessions"], 0)
        self.assertEqual(result["search"]["total"], 0)
        with override_settings(BUSINESS_GA4_CREDENTIALS_FILE=""):
            missing = build_analytics_report(PERIOD)
        self.assertEqual(missing["status"], "not_configured")
        self.assertNotIn("summary", missing)
        self.assertEqual(self.session.post.call_count, 2)

    def test_cache_avoids_repeated_calls_and_failure_returns_dated_stale_data(self):
        self.session.post.side_effect = self.answers()
        first = build_analytics_report(PERIOD)
        self.assertEqual(build_analytics_report(PERIOD), first)
        self.assertEqual(self.session.post.call_count, 2)
        # Expire only fresh entries, preserving the timestamped last-good snapshot.
        original = cache.get
        with patch("business.analytics.cache.get", wraps=original) as get:
            get.side_effect = lambda key: None if key.endswith("2026-10-03") else original(key)
            self.session.post.side_effect = [response(status=429)]
            stale = build_analytics_report(PERIOD)
            retry = build_analytics_report(PERIOD)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["fetched_at"], first["fetched_at"])
        self.assertEqual(stale["summary"], first["summary"])
        self.assertEqual(retry, stale)
        self.assertEqual(self.session.post.call_count, 3)

    def test_live_empty_dimensionless_report_can_omit_all_headers(self):
        core, search = self.answers(empty=True)
        empty = {"metadata": {"currencyCode": "GEL", "timeZone": "Asia/Tbilisi"},
                 "propertyQuota": {}, "kind": "analyticsData#runReport"}
        core.json.return_value["reports"][0] = empty
        self.session.post.side_effect = [core, search]
        result = build_analytics_report(PERIOD)
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["summary"]["sessions"], 0)
        for invalid in ({**empty, "rowCount": 1}, {**empty, "kind": "not-a-report"},
                        {**empty, "rows": [{"metricValues": [{"value": "10"}]}]}):
            cache.clear()
            core, _ = self.answers(empty=True)
            core.json.return_value["reports"][0] = invalid
            self.session.post.side_effect = [core]
            self.assertEqual(build_analytics_report(PERIOD)["status"], "unavailable")

    def test_search_failure_preserves_traffic_but_not_invented_search_zeros(self):
        self.session.post.side_effect = [self.answers()[0], response(status=400)]
        result = build_analytics_report(PERIOD)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary"]["sessions"], 10)
        self.assertEqual(result["search"]["status"], "unavailable")
        self.assertIsNone(result["search"]["total"])

    def test_timeouts_access_and_quota_errors_never_look_like_zero_data(self):
        for error in (Timeout("PRIVATE_TOKEN"), response(status=403), response(status=429)):
            with self.subTest(error=type(error)):
                cache.clear()
                self.session.post.side_effect = [error]
                result = build_analytics_report(PERIOD)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["fetched_at"])
                self.assertNotIn("summary", result)
                self.assertNotIn("PRIVATE_TOKEN", str(result))
                self.assertEqual(build_analytics_report(PERIOD), result)

    def test_wrong_headers_bad_counts_and_out_of_period_days_are_not_trusted(self):
        for bad in (report(self.core[0], [(7, "NaN", 4, 15)]), {"rows": []}):
            cache.clear()
            self.session.post.side_effect = [response({"reports": [bad, report(self.core[1]), report(self.core[2])]})]
            self.assertEqual(build_analytics_report(PERIOD)["status"], "unavailable")
        cache.clear()
        core = [report(self.core[0]), report(self.core[1], [("20261102", 4, 2)]), report(self.core[2])]
        self.session.post.side_effect = [response({"reports": core})]
        self.assertEqual(build_analytics_report(PERIOD)["status"], "unavailable")

    def test_privacy_sampling_notes_are_preserved(self):
        core, search = self.answers()
        core.json.return_value["reports"][0]["metadata"].update(subjectToThresholding=True, dataLossFromOtherRow=True, samplingMetadatas=[{}])
        self.session.post.side_effect = [core, search]
        self.assertEqual(len(build_analytics_report(PERIOD)["warnings"]), 3)

    def test_unknown_search_outcome_is_unavailable_not_success(self):
        core, search = self.answers()
        search.json.return_value["reports"][0]["rows"][0]["dimensionValues"][0]["value"] = "(not set)"
        self.session.post.side_effect = [core, search]
        result = build_analytics_report(PERIOD)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["search"]["no_results"])


class CredentialTests(SimpleTestCase):
    @override_settings(BUSINESS_GA4_CREDENTIALS_JSON="", BUSINESS_GA4_CREDENTIALS_FILE="")
    def test_missing_config_never_uses_other_ambient_google_credentials(self):
        with self.assertRaises(AnalyticsUnavailable) as caught:
            _credentials()
        self.assertEqual(caught.exception.code, "not_configured")

    @override_settings(BUSINESS_GA4_CREDENTIALS_FILE="")
    @patch("business.analytics.service_account.Credentials.from_service_account_info")
    def test_explicit_reader_only_readonly_scope_and_fixed_token_endpoint(self, factory):
        import json
        info = {"type": "service_account", "client_email": READER_EMAIL, "token_uri": "https://oauth2.googleapis.com/token"}
        with override_settings(BUSINESS_GA4_CREDENTIALS_JSON=json.dumps(info)):
            _credentials()
        factory.assert_called_once_with(info, scopes=[SCOPE])
        for change in ({"client_email": "sheets@example.test"}, {"token_uri": "https://attacker.example/token"}, {"type": "authorized_user"}):
            with override_settings(BUSINESS_GA4_CREDENTIALS_JSON=json.dumps({**info, **change})):
                with self.assertRaises(AnalyticsUnavailable):
                    _credentials()
        self.assertEqual(factory.call_count, 1)


@override_settings(CACHES=LOCAL_CACHE)
class AnalyticsAccessTests(TestCase):
    def setUp(self):
        caches["throttling"].clear()
        self.client = APIClient()
        self.owner = get_user_model().objects.create_superuser("ga-owner", "ga-owner@example.test", "test-password")

    def login(self):
        with patch("business.views.validate_recaptcha", return_value=True):
            self.client.post(reverse("business:login"), {"username": "ga-owner", "password": "test-password", "recaptcha_token": "mock"})

    @patch("business.views.build_analytics_report")
    def test_business_authentication_required_before_google_or_cache(self, build):
        url = reverse("business:analytics")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 401)
        build.assert_not_called()
        self.login()
        build.return_value = {"status": "not_configured"}
        result = self.client.get(url, {"start": "2026-01-01", "end": "2026-01-02", "hostname": "localhost", "property_id": "1"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
        build.assert_called_once_with(ReportPeriod(date(2026, 1, 1), date(2026, 1, 2)))

    @patch("business.views.build_analytics_report")
    def test_invalid_long_future_and_incomplete_dates_never_call_google(self, build):
        self.login()
        for query in ({"start": "2026-01-01"}, {"start": "2026-01-03", "end": "2026-01-01"},
                      {"start": "2025-01-01", "end": "2026-01-02"}, {"start": "2027-01-01", "end": "2027-01-02"},
                      {"start": "bad", "end": "bad"}):
            self.assertEqual(self.client.get(reverse("business:analytics"), query).status_code, 400)
        build.assert_not_called()
