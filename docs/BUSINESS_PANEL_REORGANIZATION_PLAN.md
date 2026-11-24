# Business panel reorganization

Approved 2026-11-25. Follow these steps in order. Preserve existing information,
permissions, financial calculations, tracking consent and private-session rules.
User owns full builds, commits, pushes and deployment. No production writes.

## Ordered checklist

- [x] 1. Inventory existing information and its source/destination.
- [x] 2. Identify details which must be preserved.
- [x] 3. Group navigation: overview, our shop, Google, Meta, diagnostics; preserve old URLs.
- [x] 4. Give each metric an explicit source and meaning.
- [x] 5. Provide six overview metrics with links to detailed reports.
- [x] 6. Show at most three factual attention items with links.
- [x] 7. Preserve our shop's sales, finance, returns, stock and delivery details.
- [x] 8. Organize GA4 into audience, acquisition, pages/devices, internal search and journey views.
- [x] 9. Add GA4 daily/period new and returning users and first-user acquisition.
- [x] 10. Give Search Console its own Google search page.
- [x] 11. Create cart views for current contents, period additions and existing checkout diagnostics.
- [x] 12. Show paginated/filterable current nonempty carts and product quantities.
- [x] 13. Record successful cart additions only; deduplicate observation IDs; preserve consent/internal exclusions.
- [x] 14. Add product interest summaries; link checkout/order only with established evidence; keep Buy Now separate.
- [x] 15. Make campaigns the primary Meta report with objective, status and relevant results.
- [x] 16. Label attribution period/currency/limits; never equate ROAS with profit.
- [x] 17. Separate Facebook/Instagram profile activity from paid campaign reporting.
- [x] 18. Move connection diagnostics out of primary performance reports.
- [x] 19. Unify period, source/timezone/freshness, incomplete-day and missing-data presentation.
- [x] 20. Run focused preservation/access/count/performance/render checks and document rollout/migrations.

## Preservation inventory

| Existing source and view | Information retained | Destination |
| --- | --- | --- |
| business/reports.py, BusinessReport | Confirmed sales, daily series, top products, net/refund/VAT/cost/profit definitions, unknown costs and losses | Overview, Sales, Finance |
| business/operations.py, BusinessOperations | Payment attention filters, saved allowlisted failure reason/code, attempt chronology, delivery/product totals and later paid order; shipments, returns and owned stock | Our shop / Operations; overview links |
| business/checkout_report.py, BusinessCheckout | Per-product checkout cases, observed stages, quote/form/price/stock issues, bank outcome, later payment, cart/Buy Now distinction, limits | Our shop / Carts / Started purchases |
| business/vehicle_demand.py, BusinessVehicleDemand | Make/model/year/variant demand, VIN-use flag, empty results and missing catalog; session/coverage limits | Our shop / Vehicle demand |
| business/analytics.py, BusinessUsers | GA4 period/daily users and sessions, source/medium, successful/empty internal searches and terms, warnings | Google / Website analytics tabs |
| business/decisions.py, BusinessDecisionPanel, BusinessFunnel | Previous-period comparison, GA4 source+campaign purchases/revenue, ordered all/cart/Buy Now funnels; Meta CPA/ROAS/campaign attribution | Corresponding Google/Meta view; compact overview |
| business/pages.py, BusinessPagePerformance | Page views/users/active time | Google / Pages and devices |
| business/devices.py, BusinessDevices | Separate device session and purchase counts/shares and coverage warnings | Google / Pages and devices |
| business/search_console.py, BusinessSearchConsole | Search impressions/clicks/CTR/position, queries/pages/devices, source reporting-day and privacy limits | Google / Google search |
| business/marketing.py, BusinessMarketing | Ads summary/daily/campaign spend, all clicks, link clicks, landing views, reach, attributed purchases/value; account currency/timezone | Meta / Campaigns |
| business/marketing.py, BusinessMarketing | Facebook and Instagram existing profile/activity metrics and partial coverage | Meta / Facebook and Instagram |
| BusinessMetaTechnical | Pixel identity/last-fired time, CAPI configuration, honest delivery limits and Events Manager link | Connections and diagnostics |

## Rules for new information

Current cart contents are a snapshot, not addition history or unique people.
Addition history starts at deployment and cannot reconstruct deleted past items.
Only confirmed mutations may create event records; retries must not duplicate
events. No customer identity/contact data, raw guest token, VIN, search text or
browser fingerprint is added to the new analytics records or public responses.
Existing consent and internal/preview exclusions remain. Never fabricate unknown
order links, historic traffic, abandonments or lost revenue.

GA4 new/returning metrics are requested directly, not computed by subtraction.
First-user acquisition and session acquisition remain distinct. Daily unique
users must not be summed into period users. Unavailable, stale, thresholded and
successful zero reports remain distinct. GA4 stays scoped to flexdrive.ge.

Campaign objective/status are read-only metadata. Sales and traffic objectives
have different outcome metrics. Existing reporting attribution stays explicit;
Meta, GA4 and financial orders must not be added together. Keep currency and
source reporting timezone visible. Diagnostics must not claim verified delivery
from configuration alone. No campaign, budget, audience, GTM or provider edits.

## Verification and rollout

Record each completed step and required checks here. Frontend and backend need
coordinated deployment; any new model requires an explicit forward migration.
Do not run production migrations, cart cleanup, fake purchases or real tracking
events as verification. Preserve older API response handling when practical.

### Completed implementation — 2026-11-25

All 20 steps were implemented in order. Existing URLs remain accessible, including
`/business/checkout`; the grouped menu links to the new cart tab instead.
The new menu is Overview; Our shop (Sales, Finance, Carts, Vehicle demand,
Operations); Google (Website analytics, Google search); Meta (Campaigns,
Facebook/Instagram); Connections and diagnostics.

New private read-only endpoints are `/api/business/audience/` and
`/api/business/carts/`. The former uses the existing fixed-host GA4 credentials
and cache. The latter uses the existing business permission, session, period and
no-store rules; current contents and event history are separate views. Event
history stores successful consented production additions, not cart reads, quantity
edits or Buy Now clicks. Reused observation IDs deduplicate the analytics record;
existing cart mutation behavior is unchanged. Deleting a cart/product preserves
the limited historic snapshot through nullable relations. No historic backfill.

Current cart reads are paginated at 20, preview five products per cart, and use
batched prefetching (three queries in the snapshot regression test). Addition
history reports actions, units and distinct cart contexts separately. The optional
later-order relation requires the same saved bank checkout cart/item/product and
unit price with enough quantity, within 24 hours. At most 400 candidate payments
are examined per page; an incomplete search is labelled. It does not establish a
person's identity or a lost sale. Direct product/account identity details and raw
checkout snapshots are not exposed by the new report.

Campaign objective and current effective status enrich existing Meta insights;
metadata failure retains spend/results with unknown objective/status. Campaign
objective is not ad-set optimization. Attribution remains seven-day click and
one-day view, conversion reporting time, with the ad-account currency/timezone.
Existing Meta insights and Facebook/Instagram cards are retained; profile metrics
are explicitly not guaranteed to represent organic-only activity.

### Verification

- Backend: all 49 focused audience/cart/marketing/financial/payment-attempt/
  checkout-report checks passed in isolated in-memory SQLite. Eight tests in the
  new source contract module cover direct GA4 counts, missing responses, privacy,
  query budget, successful mutations, observation deduplication, failed storage,
  strict later-order matching and private permissions.
- A broader 148-test run passed 143 and exposed five existing fixture/assertion
  problems outside the changed behavior: four CommerceAPITests fail in setUp
  because a published product lacks its required public SKU; one Wingo export
  test assumes sheet3 is the courier sheet, although the buyer sheet now precedes
  it. These unrelated tests were not rewritten. No claim that the whole suite passes.
- Frontend: 90 business render/composable/navigation checks including the focused
  organization suite pass; the latter executes real SFC renders and checks
  objective-specific results, source labels, missing values, escaping, cart
  detail links, old URLs, and analytics consent/host/internal exclusions.
- Scoped ESLint and strict app vue-tsc pass. New SFC templates/scripts compile.
  Migration drift check reports no missing model migrations. Git whitespace checks
  pass. Existing CKEditor/staticfiles warnings remain.
- No full production build, browser/viewport visual check, synthetic live analytics
  event, provider account change, DB cleanup or production data write was performed.
  Source checks and mocked provider responses do not verify live Meta/GA4 receipt.

### User-owned rollout

1. Push/deploy both repositories using the usual workflow. No new ENV or provider
   permission is required; optional campaign metadata may remain unknown if the
   existing Meta token cannot read it.
2. Inspect `python manage.py migrate business 0004_cart_addition --plan`, then apply
   `python manage.py migrate business 0004_cart_addition` on the deployment target
   (or let the existing deployment migration step apply it). It depends on
   business0003_checkout_progress and commerce0046_order_personal_number. No local
   or production migration was applied in this task; test databases alone migrated.
3. Open Overview, Google / Website analytics, Meta / Campaigns and Carts. Check the
   chosen dates, source labels and missing-data states. Cart additions start only
   after the backend table and frontend consented request are live; past history
   cannot be reconstructed. Current cart contents work independently of history.
4. Confirm one genuine consented external addition later appears, and inspect live
   GA4/Meta responses after deployment. No fake purchase is needed. Review desktop
   and mobile presentation manually; full build and visual verification remain
   user-owned.

Rollback: revert the frontend/backend source changes through the normal deployment
workflow. Leave the new history table in place to preserve observations; do not
reverse its migration or delete existing business data as a routine rollback.
