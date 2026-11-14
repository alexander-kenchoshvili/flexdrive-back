from copy import deepcopy
from datetime import date
from unittest.mock import patch

from django.core.cache import cache, caches
from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from requests.exceptions import Timeout

from .analytics import AnalyticsUnavailable
from .decisions import (STEPS, _google, _rows, build_decision_report, definitions,
                        funnel_request, parse_funnel)
from .marketing import _ad_values
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE, report

PERIOD = ReportPeriod(date(2026, 11, 1), date(2026, 11, 14))


def funnel(counts=(10, 6, 4, 2)):
    return {"kind": "analyticsData#runFunnelReport", "funnelVisualization": {
        "dimensionHeaders": [{"name": "funnelStepName"}], "metricHeaders": [{"name": "activeUsers"}],
        "rows": [{"dimensionValues": [{"value": f"{index + 1}. {event}"}], "metricValues": [{"value": str(value)}]}
                 for index, ((event, _), value) in enumerate(zip(STEPS, counts))], "metadata": {}}}


class DecisionContractTests(SimpleTestCase):
    def test_scoped_reports_and_comparison_dates(self):
        specs = definitions(PERIOD)
        self.assertEqual(specs[1]["dateRanges"], [{"startDate": "2026-10-01", "endDate": "2026-10-14"}])
        for body in [*specs, funnel_request(PERIOD)]:
            self.assertIn("flexdrive.ge", str(body["dimensionFilter"]))
            self.assertIn("manager-fd", str(body["dimensionFilter"]))
            self.assertIn("notExpression", str(body["dimensionFilter"]))
        request = funnel_request(PERIOD)
        self.assertFalse(request["funnel"]["isOpenFunnel"])
        self.assertEqual([step["filterExpression"]["funnelEventFilter"]["eventName"] for step in request["funnel"]["steps"]], [event for event, _ in STEPS])

    def test_revenue_remains_decimal_and_invalid_data_is_not_zero(self):
        spec = definitions(PERIOD)[0]
        parsed = _rows(report(spec, [(10, 7, 2, "123.45")]), spec)
        self.assertEqual(parsed[0]["purchaseRevenue"], "123.45")
        for value in ("NaN", "-1", "Infinity"):
            with self.assertRaises(ValueError):
                _rows(report(spec, [(10, 7, 2, value)]), spec)
        with self.assertRaises(ValueError):
            _rows(report(spec, [("1.5", 7, 2, "10")]), spec)

    def test_ordered_funnel_counts_and_missing_or_growing_steps(self):
        parsed = parse_funnel(funnel())
        self.assertEqual([s["lost"] for s in parsed["steps"]], [4, 2, 2, None])
        for bad in (funnel((10, 11, 4, 2)), funnel((10, -1, 4, 2)), funnel((10, "NaN", 4, 2))):
            with self.assertRaises(ValueError):
                parse_funnel(bad)
        bad = funnel()
        bad["funnelVisualization"]["rows"].pop()
        with self.assertRaises(ValueError):
            parse_funnel(bad)
        empty = funnel(())
        self.assertEqual([step["users"] for step in parse_funnel(empty)["steps"]], [0, 0, 0, 0])

    def test_duplicate_wrong_headers_and_sampling(self):
        bad = funnel()
        bad["funnelVisualization"]["rows"][1] = deepcopy(bad["funnelVisualization"]["rows"][0])
        with self.assertRaises(ValueError):
            parse_funnel(bad)
        bad = funnel()
        bad["funnelVisualization"]["metricHeaders"][0]["name"] = "eventCount"
        with self.assertRaises(ValueError):
            parse_funnel(bad)
        sampled = funnel()
        sampled["funnelVisualization"]["metadata"]["samplingMetadatas"] = [{}]
        self.assertTrue(parse_funnel(sampled)["warnings"])

    def test_live_alpha_duplicate_headers_empty_and_equal_rows_only(self):
        empty = funnel(())
        empty["funnelVisualization"]["metricHeaders"] *= 2
        self.assertEqual([step["users"] for step in parse_funnel(empty)["steps"]], [0, 0, 0, 0])
        same = funnel()
        same["funnelVisualization"]["metricHeaders"] *= 2
        for row in same["funnelVisualization"]["rows"]:
            row["metricValues"] *= 2
        self.assertEqual(parse_funnel(same)["steps"][0]["users"], 10)
        same["funnelVisualization"]["rows"][0]["metricValues"][1] = {"value": "9"}
        with self.assertRaises(ValueError):
            parse_funnel(same)

    @patch("business.decisions.AuthorizedSession")
    @patch("business.decisions._credentials", return_value=object())
    @patch("business.decisions._batch")
    def test_google_totals_source_campaign_currency_and_timezone(self, batch, credentials, transport):
        specs = definitions(PERIOD)
        answers = [report(specs[0], [(10, 7, 2, "123.45")]), report(specs[1], [(5, 4, 1, "50")]),
                   report(specs[2], [("facebook / paid_social", "launch", 10, 7, 2, "123.45")])]
        batch.return_value = answers
        result = _google(PERIOD)
        self.assertEqual(result["sources"][0]["sessionCampaignName"], "launch")
        self.assertEqual(result["currency"], "GEL")
        self.assertEqual(result["previous"]["sessions"], 5)
        answers[0]["metadata"]["currencyCode"] = "USD"
        with self.assertRaises(ValueError):
            _google(PERIOD)

    def test_link_clicks_do_not_include_all_clicks_or_purchase_aliases(self):
        result = _ad_values({"spend": "20.00", "impressions": "100", "clicks": "30", "reach": "50", "actions": [
            {"action_type": "omni_purchase", "value": "9"}, {"action_type": "link_click", "value": "12"},
            {"action_type": "landing_page_view", "value": "8"}, {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2.5"}]})
        self.assertEqual((result["clicks"], result["link_clicks"], result["landing_page_views"], result["website_purchases"]), (30, "12", "8", "2.5"))


@override_settings(CACHES=LOCAL_CACHE, BUSINESS_GA4_CREDENTIALS_JSON="reader", BUSINESS_GA4_CREDENTIALS_FILE="", BUSINESS_META_ACCESS_TOKEN="")
class DecisionCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("business.decisions._google", return_value={"current": {"sessions": 7}})
    @patch("business.decisions._funnel", side_effect=AnalyticsUnavailable("access"))
    def test_funnel_failure_preserves_core_and_cache_backoff(self, funnel_read, core):
        first = build_decision_report(PERIOD, "google")
        self.assertEqual(first["google"]["current"]["sessions"], 7)
        self.assertEqual(first["funnel"]["status"], "unavailable")
        self.assertNotIn("Meta", first["funnel"]["message"])
        self.assertEqual(build_decision_report(PERIOD, "google"), first)
        core.assert_called_once()
        funnel_read.assert_called_once()

    @patch("business.decisions._google", side_effect=Timeout("PRIVATE_CREDENTIAL"))
    @patch("business.decisions._funnel", return_value={"steps": []})
    def test_core_failure_does_not_hide_funnel_or_expose_exception(self, funnel_read, core):
        result = build_decision_report(PERIOD, "google")
        self.assertEqual(result["google"]["status"], "unavailable")
        self.assertEqual(result["funnel"]["status"], "ready")
        self.assertNotIn("PRIVATE_CREDENTIAL", str(result))

    @override_settings(BUSINESS_GA4_CREDENTIALS_JSON="")
    @patch("business.decisions._google")
    @patch("business.decisions._ads")
    def test_missing_config_and_source_selection_never_read_other_accounts(self, ads, google):
        result = build_decision_report(PERIOD, "all")
        self.assertEqual(result["google"]["status"], "not_configured")
        self.assertEqual(result["ads"]["status"], "not_configured")
        self.assertNotIn("ads", build_decision_report(PERIOD, "google"))
        ads.assert_not_called()
        google.assert_not_called()


@override_settings(CACHES=LOCAL_CACHE)
class DecisionAccessTests(TestCase):
    def setUp(self):
        caches["throttling"].clear()
        self.client = APIClient()
        self.owner = get_user_model().objects.create_superuser("decision-owner", "decisions@example.test", "test-password")

    @patch("business.decisions.build_decision_report", return_value={"period": {}})
    def test_private_gate_validation_and_no_store(self, build):
        url = reverse("business:decisions", args=["all"])
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 401)
        build.assert_not_called()
        with patch("business.views.validate_recaptcha", return_value=True):
            self.client.post(reverse("business:login"), {"username": "decision-owner", "password": "test-password", "recaptcha_token": "mock"})
        for query in ({"start": "2026-01-01"}, {"start": "2027-01-01", "end": "2027-01-02"}, {"start": "0001-01-01", "end": "0001-01-02"}):
            self.assertEqual(self.client.get(url, query).status_code, 400)
        self.assertEqual(self.client.get(reverse("business:decisions", args=["foreign"])).status_code, 400)
        # Build is mocked above: the date floor is validated before API work.
        build.reset_mock()
        response = self.client.get(url, {"start": "2026-01-01", "end": "2026-01-02", "property_id": "foreign"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        build.assert_called_once_with(ReportPeriod(date(2026, 1, 1), date(2026, 1, 2)), "all")
