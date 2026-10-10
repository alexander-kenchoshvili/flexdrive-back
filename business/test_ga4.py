from datetime import date

from django.test import SimpleTestCase

from .ga4 import GA4_REPORT_URL, build_ga4_report_request
from .reports import ReportPeriod


class GA4SourceTests(SimpleTestCase):
    def setUp(self):
        self.period = ReportPeriod(date(2026, 10, 1), date(2026, 10, 9))

    def test_summary_and_breakdowns_share_exact_domain_scope(self):
        for dimensions in ((), ("date",), ("sessionSourceMedium",), ("searchTerm",)):
            body = build_ga4_report_request(self.period, dimensions, ("eventCount",))
            scope = body["dimensionFilter"]["filter"]
            self.assertEqual(scope["fieldName"], "hostName")
            self.assertEqual(scope["stringFilter"], {
                "matchType": "EXACT", "value": "flexdrive.ge", "caseSensitive": False,
            })
            self.assertEqual(body["dateRanges"], [{"startDate": "2026-10-01", "endDate": "2026-10-09"}])
            self.assertNotIn("www.flexdrive.ge", str(body))
            self.assertNotIn("ondigitalocean.app", str(body))
        self.assertIn("properties/538949234:runReport", GA4_REPORT_URL)

    def test_even_broad_additional_filter_cannot_replace_domain_restriction(self):
        extra = {"orGroup": {"expressions": [
            {"filter": {"fieldName": "hostName", "stringFilter": {"value": "localhost"}}},
            {"filter": {"fieldName": "eventName", "stringFilter": {"value": "search"}}},
        ]}}
        body = build_ga4_report_request(self.period, (), ("eventCount",), dimension_filter=extra)
        expressions = body["dimensionFilter"]["andGroup"]["expressions"]
        self.assertEqual(expressions[0]["filter"]["stringFilter"]["value"], "flexdrive.ge")
        self.assertEqual(expressions[1], extra)
        extra["orGroup"]["expressions"].clear()
        self.assertEqual(len(expressions[1]["orGroup"]["expressions"]), 2)
