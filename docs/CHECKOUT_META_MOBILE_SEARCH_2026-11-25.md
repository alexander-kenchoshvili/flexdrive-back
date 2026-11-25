# Checkout last step, Meta events and mobile search — 2026-11-25

Implemented in the user-requested order. Existing uncommitted payment-page,
cart-owner and vehicle-table-scroll work was retained. Google audience/devices
views were not reorganized or changed.

## 1. Last saved checkout step

BusinessCheckout highlights the final entry and timestamp from its existing
chronological saved steps. No new observation, inferred exit event, collection,
identity or reason is created. Existing history/reasons remain. A bank outcome
can be the final saved step; this is not proof of the visitor's exact exit moment.
No saved reason remains unknown, including a visitor simply closing the page.

## 2. Separate Meta event report

New protected `/api/business/meta-events/` and `/business/meta-events`; the menu
entry is Meta / საიტის მოვლენები · Pixel. Reuses existing dashboard permission,
private business session, no-store response, validated periods, credentials,
fixed Graph version/Pixel and five-minute cache/stale policy. No new ENV/model,
migration/job or provider settings. Current report scope is the most recent
seven calendar days, using Asia/Tbilisi day boundaries, clipped to the present.

Only read-only `GET /{fixed-pixel}/stats?aggregation=event` with `WEB_ONLY` and
`SERVER_ONLY` filters. At most three cursor pages of 200 hourly buckets per
source; bounded event rows, aware timestamps/range/duplicates/nonnegative safe
integers validated. Provider next URLs are never followed. Only nine standard
allowlisted names and aggregate counts leave the backend; no custom labels,
URLs, users, parameters or raw provider errors. Browser/server are separate,
never summed into deduplicated purchases or unique people. Counts cover the
entire dataset, including any staging host sharing it; not falsely main-host-only.

UI shows Georgian meanings, English event identifiers, independent source
status/freshness, dates and expandable daily counts. Unknown is dash, successful
zero is zero, stale is labelled. Campaign-attributed results remain separate.
Events Manager link remains available for receipt/dedup diagnostics.

**Live read verified on November25:** The old reporting credential returned
HTTP400/code100, `(#100) Permission denied`, including after the user assigned the
Analytics Reader to the dataset. User then generated a new Analytics Reader token
with the additional `ads_management` grant. Read-only `/me/permissions` confirms
that grant alongside `ads_read` and `read_insights`. Both implemented source-filtered
readers now return `ready` and successfully parse real November24–25 aggregate
payloads (including11 ViewContent and4 InitiateCheckout per source). Counts are
events, not unique buyers, and the source columns must not be summed.
Only `BUSINESS_META_ACCESS_TOKEN` in ignored local `.env` was replaced; the CAPI
setting was preserved byte-for-byte. A fresh process using configured settings
also reads both sources successfully. No secret is saved in tracked source,
helpers or evidence. Production ENV remains user-owned and has not been changed.

Official contracts:
- https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ads-pixel/stats
- https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adspixelstatsresult.py
- https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adspixelstats.py

## 3. Mobile search presentation only

For widths up to and including768px, non-home/non-catalog-listing pages retain
the query input/search action and expose detailed filters through a bottom sheet.
Home stays expanded; catalog listing/category pages retain their existing filter
ownership. At769px and above, existing inline layouts remain. The parent and
child media queries both include768px; existing staged Teleport relocation order
is retained. Mobile sheet is above the product buy bar and scrolls internally.

The same HeaderSearch instance owns all selected values, variants, categories,
query, VIN validation/decoder, async guards and submit/suggestion handlers. No
second search state, alternate navigation builder or new tracking. The compact
sheet reuses existing HeaderSearchFilters and adds no second query/checkout form.
Its open/close buttons are type button; search explicitly invokes the existing
handler. The existing dialog provides close/backdrop/Escape/focus/scroll behavior.
Opening, closing and resizing preserve draft values; moving above768 closes the
mobile sheet. Larger viewport behavior and existing keyboard submit stay intact.

## Verification / rollout

88 focused frontend navigation/auth/SSR/header-search checks pass, including real
Vue template clicks at375/768/769px, boundary checks at320/768/769/1280, both checkout
paths and product detail, draft/filter/variant preservation, one navigation,
VIN decoder use and its existing error/refinement regressions. Checkout final
step and Meta unavailable/separate-count rendering are covered.23 focused
backend checkout/Meta/marketing checks pass. Scoped ESLint and strict app vue-tsc
pass. No full build/browser visual review, provider events, live checkout, DB
migration/write, commit/push/deploy. Both repos need deployment; no migration.
Meta event counts were verified against real successful payloads locally. User
must update production `BUSINESS_META_ACCESS_TOKEN` with the new reporting token
and deploy the prepared source; do not replace the separate CAPI setting.
