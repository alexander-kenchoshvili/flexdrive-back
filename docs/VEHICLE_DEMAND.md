# Vehicle demand in the business panel

2026-11-18: the separate frontend Meta Search addition is documented in
`VIN_SEARCH_MARKETING.md`. This demand collector still does not forward records
to Meta/GA; the two channels have different consent/counting rules.

Implemented 2026-11-17 at the user's request. New private section:
`/business/vehicle-demand` — **მოთხოვნა მანქანებზე**.

Shows make/model/year, distinct search-session counts, sessions using VIN,
sessions with zero-result catalog searches, a selected date range and a factual
Georgian summary (leaders/ties, runners-up, missing-catalog demand, small sample).
First 100 model/year combinations are shown; the total group count is separate.
Empty/error/loading states are distinct; no historical or synthetic activity is
created. Insights derive from counts, not generated speculation or ad ROI claims.

## Collection

- VIN responses sign decoded make/model/year/version/outcome for 15 minutes.
  No raw VIN goes into this token, interest table, report or analytics payload.
  Valid decoded vehicles without catalog coverage are counted too. Invalid VINs
  and provider errors cannot be assigned to a car and are not guessed.
- Successfully loaded catalog selections also record make/model, optional year,
  version context and whether results were empty. Make-only selections are not
  collected. Raw q, VIN, URLs, customer/account ID, name/email/phone/IP are not
  stored in the new table. No Meta/GA event or advertising audience is created.
- Client collection requires existing analytics consent on `flexdrive.ge` only.
  No local/preview tracking. Business users/current staff are skipped; visiting
  the authenticated business layout marks that browser as internal in localStorage.
  This is a browser opt-out flag, not a unique account identifier. Shared browsers
  carrying it are also excluded. It does not retroactively erase earlier events.
- Random per-tab session IDs survive reload in sessionStorage, rotate after 30
  minutes without a vehicle-interest event and are forgotten on analytics denial.
  PostgreSQL stores only a keyed digest, never the original session ID. A DB
  uniqueness constraint deduplicates day/session/vehicle context. Model/year report
  counts distinct session digests across version contexts; one session can search
  multiple vehicles and row totals must not be summed as unique people/owners.
- POST `/api/catalog/vehicles/interest/` is public, CSRF protected, throttled
  30/min plus existing limits, strict bounded input fields. Manual make/model must
  exist under the selected active make. VIN attributes require a signed lookup
  token. Unknown payload fields are rejected. Staff requests are ignored.
- Repeated positive counts do not create requests per page/sort. A later empty
  result adds a monotonic signal. Collector failures are swallowed by the client
  and reported as unavailable by the endpoint, never interrupting shopping/VIN.

Zero-result counts mean some catalog search in that context returned zero; this
can reflect part/refinement filters and does not prove the model has no stock.
Missing-catalog counts refer specifically to the validated VIN lookup outcome.
Interest is not ownership, distinct vehicles, all visitors or completed purchases.
Conversion attribution and raw search-term storage were not added in this scope.

## Deployment and local state

Deploy both repositories and run:

```sh
python manage.py migrate business 0002_vehicle_interest
```

Migration creates `business_vehicleinterest` only, plus normal Django model
metadata/permissions. No product/order/payment tables or provider settings change.
No new ENV, job, paid service, external account access or provider request required
for reports. Private reporting reuses `business.view_dashboard` and the separate
business-session authentication; customer/admin cookies do not grant report access.

Local SQLite had business.0001 pending too (unmanaged permission anchor only).
Verified exact forward plan 0001 + 0002, applied both locally; table is empty.
No production database writes, deployment, commit or push were performed. Local
UI review intentionally starts with no activity; production collection starts
after deploying both sides, with analytics consent and a non-internal browser.

## Required validation only

Six focused backend tests pass: consent/data boundaries, VIN/manual dedupe,
monotonic flags, signed missing-model demand, staff exclusion/private report
authorization/date range, ranking/unique-session accounting, storage failure
isolation. Five collector tests pass: consent/host/internal gates, repeated events,
minimal payload, expiry/revocation and retry safety. Existing header/catalog tests
were run while wiring the hooks (75 tests total in that run, all passing).
Scoped ESLint and Nuxt strict typecheck pass. Full build and browser/visual checks
were deliberately skipped per user instruction. User owns visual review.
