"""Fixed GA4 reporting scope. Never accept a property/host from query parameters."""

from copy import deepcopy

from .reports import ReportPeriod


GA4_PROPERTY_ID = "538949234"
GA4_HOSTNAME = "flexdrive.ge"
GA4_REPORT_URL = (
    f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY_ID}:runReport"
)


def build_ga4_report_request(
    period: ReportPeriod, dimensions, metrics, *, dimension_filter=None
):
    """Build a runReport body with an inseparable exact production-host filter.

    Additional filters are ANDed with the source restriction, so search/event
    filtering cannot accidentally widen the report to localhost or preview hosts.
    Names/filter expressions must be provided by server-side report definitions.
    """
    hostname_filter = {
        "filter": {
            "fieldName": "hostName",
            "stringFilter": {
                "matchType": "EXACT",
                "value": GA4_HOSTNAME,
                "caseSensitive": False,
            },
        }
    }
    scoped_filter = hostname_filter
    if dimension_filter is not None:
        scoped_filter = {
            "andGroup": {"expressions": [hostname_filter, deepcopy(dimension_filter)]}
        }
    return {
        "dateRanges": [{"startDate": period.start.isoformat(), "endDate": period.end.isoformat()}],
        "dimensions": [{"name": name} for name in dimensions],
        "metrics": [{"name": name} for name in metrics],
        "dimensionFilter": scoped_filter,
        "currencyCode": "GEL",
        "returnPropertyQuota": True,
    }
