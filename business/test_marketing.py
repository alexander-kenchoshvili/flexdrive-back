from datetime import date
from unittest.mock import MagicMock, patch
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests.exceptions import Timeout
from rest_framework.test import APIClient

from .marketing import AD_ID, GRAPH, IG_ID, PAGE_ID, MetaUnavailable, _cached, _count, build_marketing_report
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE

PERIOD = ReportPeriod(date(2026, 10, 1), date(2026, 10, 3))
SECRET = "test-reporting-credential"
PAGE_SECRET = "test-derived-page-credential"


def response(body, status=200):
    mock = MagicMock(status_code=status)
    mock.json.return_value = body
    return mock


def ad_row(**overrides):
    return {"date_start": "2026-10-01", "date_stop": "2026-10-03", "spend": "50.00", "impressions": "200", "clicks": "10", "reach": "100",
            "actions": [{"action_type": "omni_purchase", "value": "9"}, {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2.5"}],
            "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "120.30"}], **overrides}


@override_settings(BUSINESS_META_ACCESS_TOKEN=SECRET, CACHES=LOCAL_CACHE)
class MarketingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.calls, self.overrides = [], {}
        self.transport = patch("business.marketing.requests.Session")
        factory = self.transport.start()
        self.addCleanup(self.transport.stop)
        factory.return_value.__enter__.return_value.get.side_effect = self.answer

    def answer(self, url, **kwargs):
        self.calls.append((url, kwargs))
        self.assertTrue(url.startswith(GRAPH))
        self.assertFalse(kwargs["allow_redirects"])
        params = kwargs["params"]
        self.assertNotIn("access_token", params)
        node = url.removeprefix(GRAPH)
        label = node
        if node.startswith("act_") and node.endswith("/insights"):
            label = "campaigns" if params.get("level") == "campaign" else "daily" if params.get("time_increment") else "summary"
            self.assertEqual(params["action_report_time"], "conversion")
            self.assertEqual(json.loads(params["action_attribution_windows"]), ["7d_click", "1d_view"])
        if node == PAGE_ID and params["fields"] == "id,access_token":
            return response({"id": PAGE_ID, "access_token": PAGE_SECRET})
        if label in self.overrides:
            value = self.overrides[label]
            if isinstance(value, Exception):
                raise value
            return value
        if node == PAGE_ID:
            return response({"id": PAGE_ID, "name": "FlexDrive", "followers_count": 3, "instagram_business_account": {"id": IG_ID}})
        if node == IG_ID:
            return response({"id": IG_ID, "username": "flexdrive.ge", "followers_count": 12, "media_count": 4})
        if node == PAGE_ID + "/insights":
            self.assertEqual(kwargs["headers"], {"Authorization": "Bearer " + PAGE_SECRET})
            return response({"data": [{"name": metric, "period": "day", "values": [
                {"value": value, "end_time": f"2026-10-0{index + 2}T07:00:00+0000"} for index, value in enumerate(values)]}
                for metric, values in [("page_media_view", [10, 20, 30]), ("page_post_engagements", [1, 2, 3])]]})
        if node == IG_ID + "/insights":
            self.assertEqual(params["metric_type"], "total_value")
            return response({"data": [{"name": metric, "total_value": {"value": count}}
                                      for metric, count in [("reach", 70), ("views", 120), ("total_interactions", 9)]]})
        if node == "act_" + AD_ID:
            return response({"id": node, "name": "FlexDrive", "currency": "USD", "timezone_name": "Asia/Tbilisi"})
        if label == "summary":
            return response({"data": [ad_row()]})
        if label == "daily":
            return response({"data": [ad_row(date_start=day, date_stop=day, reach=reach) for day, reach in [("2026-10-01", "70"), ("2026-10-03", "80")]]})
        if label == "campaigns":
            return response({"data": [ad_row(campaign_id="123", campaign_name="Our campaign")]})
        self.fail("Unexpected endpoint")

    def test_real_contract_exact_assets_whole_period_unique_reach_and_attribution(self):
        report = build_marketing_report(PERIOD)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["facebook"]["profile"]["followers"], 3)
        self.assertEqual(report["facebook"]["activity"]["views"], 60)
        self.assertTrue(report["facebook"]["activity"]["complete"])
        self.assertEqual(report["instagram"]["activity"]["reach"], 70)
        ads = report["ads"]
        self.assertEqual(ads["currency"], "USD")
        self.assertEqual(ads["summary"]["reach"], 100)  # Not sum(70,80).
        self.assertEqual(ads["summary"]["website_purchases"], "2.5")  # Not all aliases added together.
        self.assertEqual(ads["summary"]["website_purchase_value"], "120.30")
        self.assertEqual(ads["daily"][1]["spend"], "0.00")
        serialized = json.dumps(report)
        self.assertNotIn(SECRET, serialized)
        self.assertNotIn(PAGE_SECRET, serialized)
        self.assertNotIn("access_token", serialized)
        self.assertEqual(len(self.calls), 9)

    def test_valid_empty_ads_are_zero_and_missing_social_metrics_are_unknown(self):
        for label in ("summary", "daily", "campaigns", IG_ID + "/insights"):
            self.overrides[label] = response({"data": []})
        report = build_marketing_report(PERIOD)
        self.assertEqual(report["ads"]["status"], "empty")
        self.assertEqual(report["ads"]["summary"]["spend"], "0.00")
        self.assertEqual(report["instagram"]["activity"]["status"], "unavailable")
        self.assertNotIn("reach", report["instagram"]["activity"])
        self.assertEqual(report["status"], "partial")

    def test_auth_errors_and_timeout_do_not_hide_other_sources_or_expose_errors(self):
        self.overrides[IG_ID + "/insights"] = response({"error": {"code": 190, "message": SECRET}}, 400)
        self.overrides["summary"] = Timeout(SECRET)
        report = build_marketing_report(PERIOD)
        self.assertEqual(report["facebook"]["activity"]["status"], "ready")
        self.assertEqual(report["instagram"]["activity"]["status"], "unavailable")
        self.assertEqual(report["ads"]["status"], "unavailable")
        self.assertNotIn("summary", report["ads"])
        self.assertNotIn(SECRET, json.dumps(report))

    def test_nonempty_campaigns_cannot_be_reported_with_a_successful_zero_account_total(self):
        self.overrides["summary"] = response({"data": []})
        self.overrides["daily"] = response({"data": []})
        report = build_marketing_report(PERIOD)
        self.assertEqual(report["ads"]["status"], "unavailable")
        self.assertNotIn("summary", report["ads"])

    def test_cache_backoff_stale_age_and_credential_rotation(self):
        report = build_marketing_report(PERIOD)
        calls = len(self.calls)
        cached = build_marketing_report(PERIOD)
        self.assertEqual({key: value for key, value in cached.items() if key != "generated_at"},
                         {key: value for key, value in report.items() if key != "generated_at"})
        self.assertEqual(len(self.calls), calls)
        with override_settings(BUSINESS_META_ACCESS_TOKEN="new-reporting-credential"):
            build_marketing_report(PERIOD)
        self.assertGreater(len(self.calls), calls)
        cache.clear()
        first = _cached("single", lambda: {"count": 9})
        cache.delete("single")
        stale = _cached("single", lambda: (_ for _ in ()).throw(MetaUnavailable("quota")))
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["fetched_at"], first["fetched_at"])
        with patch("business.marketing._get") as transport:
            _cached("single", lambda: transport())
            transport.assert_not_called()

    def test_range_limits_keep_current_profiles_and_ad_report_available(self):
        with patch("business.marketing._ads", return_value={"status": "empty"}):
            period = ReportPeriod(date(2026, 7, 1), date(2026, 10, 3))
            report = build_marketing_report(period)
        self.assertEqual(report["facebook"]["activity"]["status"], "range_limit")
        self.assertEqual(report["instagram"]["activity"]["status"], "range_limit")
        self.assertEqual(report["instagram"]["profile"]["followers"], 12)
        self.assertFalse(any(url.endswith("/insights") for url, _ in self.calls))

    def test_bad_counts_identity_and_dates_cannot_become_successful_zeros(self):
        for value in (-1, "NaN", "Infinity", "1.2", None, True):
            with self.assertRaises(MetaUnavailable):
                _count(value)
        self.overrides[PAGE_ID] = response({"id": "unrelated", "followers_count": 1000})
        self.overrides["daily"] = response({"data": [ad_row(date_start="2026-10-0a", date_stop="2026-10-0a")]})
        report = build_marketing_report(PERIOD)
        self.assertEqual(report["facebook"]["profile"]["status"], "unavailable")
        self.assertEqual(report["ads"]["status"], "unavailable")

    def test_campaign_pagination_rebuilds_fixed_url_and_has_a_visible_limit(self):
        original = self.answer
        pages = []
        def answer(url, **kwargs):
            if kwargs["params"].get("level") == "campaign":
                index = len(pages); pages.append(kwargs["params"].copy())
                self.assertEqual(url, GRAPH + "act_" + AD_ID + "/insights")
                return response({"data": [ad_row(campaign_id=str(index + 1), campaign_name="Campaign")],
                                 "paging": {"next": "https://untrusted.invalid/?access_token=private", "cursors": {"after": str(index + 1)}}})
            return original(url, **kwargs)
        with patch("business.marketing.requests.Session") as factory:
            factory.return_value.__enter__.return_value.get.side_effect = answer
            report = build_marketing_report(PERIOD)
        self.assertTrue(report["ads"]["campaigns_limited"])
        self.assertEqual(len(report["ads"]["campaigns"]), 3)
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[1]["after"], "1")
        self.assertNotIn("untrusted", json.dumps(report))

    @override_settings(BUSINESS_META_ACCESS_TOKEN="")
    def test_unconfigured_performs_no_provider_requests(self):
        self.assertEqual(build_marketing_report(PERIOD)["status"], "not_configured")
        self.assertEqual(self.calls, [])


@override_settings(CACHES=LOCAL_CACHE, RECAPTCHA_SECRET_KEY="test")
class MarketingAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = get_user_model().objects.create_superuser(username="meta-owner", email="meta@example.com", password="test-password")
        self.client = APIClient()

    def login(self):
        with patch("business.views.validate_recaptcha", return_value=True):
            self.client.post(reverse("business:login"), {"username": "meta-owner", "password": "test-password", "recaptcha_token": "mock"})

    @patch("business.views.build_marketing_report")
    def test_only_business_session_authorizes_private_reporting_and_assets_cannot_be_overridden(self, build):
        url = reverse("business:marketing")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 401)
        build.assert_not_called()
        self.login()
        build.return_value = {"status": "not_configured"}
        result = self.client.get(url, {"start": "2026-01-01", "end": "2026-01-02", "ad_account_id": "859079468055972", "access_token": "browser-token"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
        build.assert_called_once_with(ReportPeriod(date(2026, 1, 1), date(2026, 1, 2)))
        self.owner.is_staff = False; self.owner.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(build.call_count, 1)

    @patch("business.views.build_marketing_report")
    def test_invalid_periods_rejected_before_cache_or_provider(self, build):
        self.login()
        for query in ({"start": "2026-01-01"}, {"start": "2026-01-03", "end": "2026-01-01"},
                      {"start": "2025-01-01", "end": "2026-01-02"}, {"start": "2027-01-01", "end": "2027-01-02"}):
            self.assertEqual(self.client.get(reverse("business:marketing"), query).status_code, 400)
        build.assert_not_called()
