from datetime import date, datetime, timezone
from hashlib import sha256
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .authentication import BUSINESS_COOKIE, SESSION_KIND, session_store
from .marketing import PIXEL_ID
from .meta_events import build_meta_events_report
from .reports import ReportPeriod
from .test_analytics import LOCAL_CACHE
from .test_marketing import response

PERIOD = ReportPeriod(date(2026, 11, 25), date(2026, 11, 25))
NOW = datetime(2026, 11, 25, 10, tzinfo=timezone.utc)


@override_settings(BUSINESS_META_ACCESS_TOKEN="events-reporting-secret", CACHES=LOCAL_CACHE)
class MetaEventsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.clock = patch("business.meta_events.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.transport = patch("business.marketing.requests.Session")
        factory = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.calls = []
        self.override = None
        factory.return_value.__enter__.return_value.get.side_effect = self.answer

    def answer(self, url, **kwargs):
        self.calls.append((url, kwargs))
        self.assertTrue(url.endswith(PIXEL_ID + "/stats"))
        self.assertEqual(kwargs["params"]["aggregation"], "event")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertNotIn("access_token", kwargs["params"])
        if self.override:
            result = self.override(kwargs["params"])
            if result:
                return result
        count = 2 if kwargs["params"]["event_source"] == "WEB_ONLY" else 3
        return response({"data": [{"aggregation": "event", "start_time": "2026-11-24T20:00:00Z", "data": [
            {"value": "Purchase", "count": count}, {"event": "ViewContent", "count": 10},
            {"value": "PRIVATE-CUSTOM-LABEL", "count": 99},
        ]}]})

    def test_allowlisted_hourly_counts_keep_sources_separate_and_cache_without_raw_data(self):
        result = build_meta_events_report(PERIOD)
        self.assertEqual(result["status"], "ready")
        purchase = next(row for row in result["rows"] if row["event"] == "Purchase")
        self.assertEqual((purchase["browser"], purchase["server"]), (2, 3))
        self.assertNotIn("total", purchase)
        self.assertEqual(result["daily"], [{"date": "2026-11-25", "browser": 12, "server": 13}])
        self.assertEqual(result["scope"], "entire_dataset")
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn("events-reporting-secret", str(result))
        build_meta_events_report(PERIOD)
        self.assertEqual(len(self.calls), 2)

    def test_real_permission_denied_shape_is_unavailable_not_zero_and_other_source_survives(self):
        self.override = lambda params: response({"error": {"code": 100, "message": "(#100) Permission denied"}}, 400) if params["event_source"] == "WEB_ONLY" else None
        result = build_meta_events_report(PERIOD)
        self.assertEqual(result["status"], "partial")
        self.assertIn("წვდომა", result["sources"]["browser"]["message"])
        self.assertTrue(all(row["browser"] is None for row in result["rows"]))
        self.assertEqual(next(row for row in result["rows"] if row["event"] == "Purchase")["server"], 3)

    def test_invalid_or_duplicate_buckets_and_counts_never_produce_ready_numbers(self):
        valid = {"aggregation": "event", "start_time": "2026-11-24T20:00:00Z", "data": [{"value": "Purchase", "count": 1}]}
        for rows in ([valid, valid], [{**valid, "start_time": "2026-11-24T19:00:00Z"}],
                     [{**valid, "data": [{"value": "Purchase", "count": -1}]}], [{**valid, "aggregation": "host"}]):
            with self.subTest(rows=rows):
                cache.clear()
                self.override = lambda params: response({"data": rows})
                result = build_meta_events_report(PERIOD)
                self.assertEqual(result["status"], "unavailable")
                self.assertTrue(all(row["browser"] is None and row["server"] is None for row in result["rows"]))

    def test_stale_data_and_successful_empty_are_distinct_from_denial(self):
        first = build_meta_events_report(PERIOD)
        identity = sha256(b"events-reporting-secret").hexdigest()[:16]
        for source in ("browser", "server"):
            cache.delete(f"business:meta-events:v1:{identity}:{source}:{PERIOD.start}:{PERIOD.end}")
        self.override = lambda params: response({"error": {"code": 190}}, 400)
        result = build_meta_events_report(PERIOD)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["rows"], first["rows"])
        self.assertTrue(all(source["status"] == "stale" for source in result["sources"].values()))
        cache.clear()
        self.override = lambda params: response({"data": []})
        result = build_meta_events_report(PERIOD)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(all(row["browser"] == row["server"] == 0 for row in result["rows"]))

    def test_period_limit_and_missing_credential_do_not_call_meta(self):
        self.assertEqual(build_meta_events_report(ReportPeriod(date(2026, 11, 1), date(2026, 11, 25)))["status"], "range_limit")
        with override_settings(BUSINESS_META_ACCESS_TOKEN=""):
            self.assertEqual(build_meta_events_report(PERIOD)["status"], "not_configured")
        self.assertEqual(self.calls, [])


class MetaEventsAccessTests(TestCase):
    @patch("business.meta_events.build_meta_events_report", return_value={"status": "not_configured"})
    def test_existing_private_business_session_and_no_store_are_required(self, report):
        client = APIClient()
        url = reverse("business:meta-events")
        self.assertEqual(client.get(url).status_code, 401)
        owner = get_user_model().objects.create_superuser("events-owner", "events@example.test", "test-password")
        client.force_login(owner)
        self.assertEqual(client.get(url).status_code, 401)
        session = session_store()
        session.update({"kind": SESSION_KIND, "user_id": owner.pk, "auth_hash": owner.get_session_auth_hash()})
        session.save()
        client.cookies[BUSINESS_COOKIE] = session.session_key
        result = client.get(url)
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
        self.assertEqual(client.get(url, {"start": "2026-11-25"}).status_code, 400)
