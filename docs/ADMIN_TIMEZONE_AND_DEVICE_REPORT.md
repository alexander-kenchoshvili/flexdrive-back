# Admin time and aggregate device report — 2026-11-20

The admin under `/manager-fd/` uses `Asia/Tbilisi` for Django templates, date
filters and form input, with a visible UTC+04:00 header. Request-scoped middleware
restores the previous timezone afterwards. Project TIME_ZONE stays UTC and USE_TZ
stays enabled: no stored timestamps are rewritten, and public/API/business request
timezone behavior is unchanged. Accountant pages under the admin use the same zone.
The existing business frontend already formats payment dates explicitly in Tbilisi.

For the real paid sale, payment start 06:15:43 UTC corresponds to 10:15:43 Tbilisi;
payment confirmation/order creation 06:19:43 UTC corresponds to 10:19:43 Tbilisi.
Start, bank result and order creation remain separate timestamps.

`GET /api/business/devices/?start=YYYY-MM-DD&end=YYYY-MM-DD` is a private aggregate
GA4 report. It inherits existing business-session permissions, period validation
(both dates, up to 366 days, no future), throttling and no-store responses. The
server fixes the property and exact flexdrive.ge hostname; admin/business paths
are excluded. One bounded read requests deviceCategory, sessions and
ecommercePurchases using the existing read-only Google credentials. No events,
tracking, cookies, device identity, DB field or migration is added.

The frontend Users page adds a separate card for mobile, desktop/laptop, tablet
and other/unknown, with counts and shares for visits and purchases separately.
Desktop and laptop cannot be distinguished in deviceCategory. Sessions include
repeat visits. Purchases are GA4 purchase events, not the financial ledger or all
paid orders; consent, blocked collection and processing delay affect coverage.
An aggregate row cannot identify a particular order or prove a cross-device
journey. No historical device attribution is invented.

Only a valid successful report can supply zero counts. Missing/failed credentials
or malformed/truncated data return unavailable, never fake zeros. A zero total
has an unknown share (dash), not 0%. Unknown source labels are grouped without
returning their raw text. Threshold/sampling warnings are preserved; percentages
describe the returned counts. Existing 5-minute fresh/24-hour stale cache behavior
retains the original timestamp on stale responses and bounds retry traffic.

Real read-only API verification for Nov 1–20 returned Asia/Tbilisi, 97 sessions:
mobile84 (86.6%), desktop11 (11.3%), tablet2 (2.1%), unknown0. GA4 returned one
purchase in the desktop category, not an identified order. No warnings were
returned. Only aggregate evidence is saved in ignored tmp/measurements-20261015/
personal-number-20261120/devices-live-read.json. No bank communication, production
DB access/write or tracking event was performed for these changes.

Validation: eight admin timezone/navigation checks, 25 device/page/analytics
backend checks, 16 device/page/payment frontend checks, scoped ESLint and strict
app vue-tsc pass. The actual admin order template renders 10:19 a.m. from the
stored 06:19 UTC payment without rewriting payment rows; form parsing and request
timezone restoration are covered. Existing CKEditor/staticfiles warnings remain.
No full build or browser automation. Deploy backend and frontend; no new migration
or environment variable is required. User owns push/deployment.

Sources: [GA4 schema](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema),
[Django timezone handling](https://docs.djangoproject.com/en/5.2/topics/i18n/timezones/).
