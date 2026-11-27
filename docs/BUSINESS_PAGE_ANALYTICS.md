# Page visitors and acquisition in the business panel

The existing Google → Website analytics → Pages and devices tab now includes
blogs, article pages and catalog categories alongside the existing public pages.
There is no new navigation section. The whole-site acquisition tab remains separate.

Choose the date range, search by recorded page title or path, and select a page.
The list is paginated, 20 paths at a time. Its counts are aggregated by path,
without splitting unique users across historical page titles. Title searches first
discover matching public paths and then request their complete metrics without a
title filter. Titles are optional labels from Google, with the route as fallback.
If a search matches more than 500 paths, the panel asks for a narrower search;
it does not present a partial result as complete.

The selected page shows period users, sessions, views, average active time, daily
counts and the first 50 session sources ordered by sessions, with the full source
row count shown. Facebook has its own aggregate covering facebook.com and its
subdomains, plus the explicit fb source. Its users come from an independent GA4
aggregate, never from summing source rows. Period users likewise are not summed
from daily rows. Average active time is engagement seconds / active users.

The source is the acquisition source of the session in which the page was viewed;
this does not imply that the page was the session's landing page. Direct includes
visits without an identified source. Facebook attribution alone cannot identify
the individual post or comment that produced a visit. Page views and engagement
do not prove complete reading, and GA4 counts only the users it can measure.

## API and access

The existing private GET `/api/business/pages/` accepts:

- `start`, `end`: existing date validation, up to 366 days, no future dates.
- `q`: optional title/path search, maximum 120 characters.
- `page`: list page, starting at 1.
- `path`: optional selected public path; returns detail mode instead of list mode.

Property and hostname remain fixed by the existing GA4 request builder. The
public path allowlist applies to every query and response, including title search.
Private/account/checkout URLs, query strings, encoded separators and traversal
paths cannot become page selections. Existing business session permissions,
no-store middleware and request throttling remain in effect. No customer identity
or visitor-level records are returned.

List/search/page/detail caches are independent, keyed by reporting identity,
period and filters. Existing five-minute freshness, stale timestamps, provider
warnings and unavailable-versus-zero handling remain. Optional title failure does
not discard valid counts. Closing details, changing filters/period and unmounting
abort pending work; late responses cannot restore prior private report data.

## Validation and deployment

Backend report/access/cache tests and frontend rendering/interaction/cancellation
tests cover the new reports. Scoped ESLint and strict application vue-tsc pass.
No browser/dev server or full production build was used.

The page report's 14 backend tests pass against the current clock; the 32 scoped
frontend checks pass. A wider 44-test backend run initially exposed four existing
cart-fixture failures: their report period ends on November 25, while their
auto_now records are created on the current day (November 27). Cart implementation
and fixtures were not changed by this feature. The wider suite was also checked
with its test clock aligned to the November 25 fixture period in an isolated
in-memory database: all 44 tests passed. Only the test runner's clock was patched;
no fixture or application clock was changed.

A reporting-only live GA4 check for 23–26 November 2026 found the Subaru article
through search and confirmed 20 users, 22 sessions, 28 views; Facebook's independent
aggregate confirmed 18 users, 20 sessions and 26 views. Time zone: Asia/Tbilisi.
These are historical verification results, not hard-coded UI values. No tracking
event was sent by the check.

Deploy both backend and frontend. No migration, new credentials or environment
variables are needed. The agent has not pushed or deployed these changes.
