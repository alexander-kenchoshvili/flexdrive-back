# Business dashboard stage 2 — 2026-10-09

User authorized this stage after the login/Tailwind review. Stop after delivering it for the user's review; do not begin operations/GA4/Meta automatically. Use the ordinary paired project folders, without a new branch/worktree.

## Implemented

- Protected read-only `GET /api/business/report/?start=YYYY-MM-DD&end=YYYY-MM-DD`, using the existing independent business session and permission on every request. No-store, no new schema, no provider calls.
- `/business`, `/business/sales`, `/business/finance` now show actual records from the connected environment: confirmed cash receipts/refunds, order/unit counts, product results, period comparisons and daily graphs. Existing test orders are included for this review and are explicitly labeled as included. No data was marked, reset or seeded. A permanent test exclusion rule still needs agreement before public business reporting.
- Dates follow confirmed receipt/refund events in Asia/Tbilisi, rather than order creation or mutable fulfilment state. Prior-month comparisons use calendar months; custom periods use the preceding equal number of days. A zero previous baseline does not invent a percentage.
- Product margin uses the existing Decimal accounting calculations with fixed 18% VAT and exact allocated historical purchase totals where present, otherwise saved historical purchase unit costs. Current supplier prices are never substituted. A missing cost or ambiguous allocation produces `null` / `—`, not zero or invented profit. Confirmed cash remains visible.
- Regional courier total sums saved carrier quotes once per paid order. No invoice reconciliation or carrier settlement tracking. A completed pre-dispatch cancellation is excluded; a dispatched return retains its original outward quote. Quote grouping follows the original confirmed payment date, shown in the detail table.
- Saved regional buffer amount/count is separate; gross received and amount after confirmed refunds are labeled. Internal/Tbilisi delivery uses actual saved fees/counts, without hardcoding the undecided 10 GEL rate.
- Unsaleable received returns show inspected quantity and known purchase value excluding VAT separately. Actual remaining FIFO cost layers are used after subtracting saleable receipt lots. These losses are not subtracted a second time from product margin.
- ECharts uses selected line/bar/component/canvas modules, a lazy private component, design-system colors/fonts, resize/dispose lifecycle and accessible daily tables. Tailwind only; no dashboard stylesheet/style block.
- Data is fetched on entry, refresh and date changes. No scheduler or live polling. Outdated requests are aborted/ignored, failed refreshes clear old values, revoked access clears only the private business state. Private values are not persisted to browser storage or SSR payloads.
- Limits: 366 days and 10,000 events/inspection rows per source/period; excessive requests fail rather than silently truncating totals. Detail lists show the latest 20 with total count; product results show the first 10 by gross sales. Period totals cover every eligible row, not only displayed detail rows.

## Verification

- 85 backend tests passed: business session/report tests and existing accounting foundation/report/returns foundation tests, on disposable in-memory SQLite. The 15 new report tests cover VAT/history, mixed inventory, refunds, missing costs, multiple products, courier counting, timezone, comparison dates, permissions, input validation and no-store/read-only behavior.
- 19 focused frontend tests passed, including the actual logout layout regression and 6 new period/request race/failure/revocation/cleanup tests.
- Focused ESLint, Nuxt typecheck and local `npm run build` passed. Migration drift check: no changes detected; tracked-file whitespace checks passed.
- Compiled client manifest: 17 public entry/page/layout roots have no static dependency on the chart chunk; only the private report component dynamically imports it. Five dashboard templates have all 334 static Tailwind utilities present in generated CSS, with no dashboard stylesheet/style blocks.
- No dev server or browser automation started. No real database, environment/credentials, bank, supplier, carrier, staging/production, deployment or push changes.

## User review

Open the usual local frontend `/business` with the administrator credentials for that backend environment. Review overview, sales and finance, dates/presets, refresh, light/dark appearance, narrow layouts, graphs and tables. Check that carrier/buffer/internal delivery/unsaleable figures are separate. If the current period has no confirmed events, select an earlier period; zero is an actual empty result. If `—` appears, a historical cost/allocation is missing rather than guessed. GA4/Meta/users/operations remain explicitly deferred to later stages.

Browser appearance, actual browser session/proxy behavior and deployed PostgreSQL performance remain for user/integration review; code checks are not claims of those verifications.

## User visual review adjustments — 2026-10-09

User confirmed the visible DEMO-FD products are the older accounting demo batch, not new data for this dashboard. All development orders remain test records. No new records were created or deleted during this review.

Native date inputs now use Tailwind light/dark `color-scheme` properties so calendar indicators follow the theme. The daily table uses thin, rounded accent scrollbars with transparent tracks, matching the header search style, entirely through Tailwind arbitrary properties/selectors. Conditional report/foundation components have distinct key prefixes instead of identical key expressions; the original template produced no compiler error in the CLI, but the reported editor warning is addressed with explicitly separate identities.

Focused ESLint, Nuxt typecheck and template compilation passed. Confirmed all 13 new native-theme/scrollbar utilities generate correctly with installed Tailwind. No browser/server check or backend calculation change. Comparison remains: prior calendar month for a single month starting on day one, otherwise the immediately preceding equal-length period (2026-08-01 through 2026-10-09 compares with 2026-05-23 through 2026-07-31).

## Distinct overview, sales and finance — 2026-10-09

User approved removing the excessive repetition between the three views. Overview now contains the four headline metrics, a receipts/refunds trend and links into the detailed sections that preserve the selected period. It has no product, delivery, allocation or daily-detail tables.

Sales owns the order/unit/average-order metrics, the popular-products table and a daily order/unit table. Its chart now plots actual confirmed order counts and sold-unit counts, with integer axes and count tooltips rather than currency; unknown unit counts retain gaps. Product quantities sold and returned have separate columns. Profit explanations and delivery/financial breakdown cards no longer appear here.

Finance owns the cash/refund/margin metrics, the profit chart and VAT explanation, purchase/sale/delivery breakdown, carrier/buffer/internal-delivery cards, unsaleable costs and detailed delivery/loss lists. Its daily table contains cash/refund/profit amounts. Missing-data notes are scoped to the figures shown in each section. Shared date/source/auth controls and the previously reviewed theme/scrollbar fixes remain.

No backend data, calculation, API, auth, scheduler, public storefront or deployment changes. The existing 19 frontend tests, focused ESLint and Nuxt typecheck passed. Both templates compile successfully and all 178 static Tailwind utilities in the two touched components generate correctly. Browser review remains with the user; no server/browser started.

## Overview automatic analysis — 2026-10-09

After further review the user explicitly requested removing the repeated headline figures from overview, retaining its chart, and adding an automatically written Georgian analysis paragraph. Overview now has a dedicated analysis block above the receipts/refunds chart, factual attention items below with period-preserving finance links, reporting-source connection statuses and compact detail navigation. Sales and finance retain their dedicated figures; overview no longer renders the four-figure strip.

`businessInsights.ts` derives the paragraph solely from the returned current/previous summaries and validated comparison deltas. It compares product sales, cash after refunds, product margin and order/unit counts without inferring causes or company net profit. Empty periods, zero baselines, refund-only periods, negative-but-improving product results and missing current/prior costs have distinct truthful descriptions. Attention facts use confirmed refunds, inspected unsaleable counts and incomplete saved financial values. No external AI API, token, dependency, paid service or extra data request was introduced. A Vue computed value rederives the text on every new report response; it is not persisted.

28 focused frontend tests passed (9 new analysis tests), plus focused ESLint, Nuxt typecheck and template compilation. All 186 static Tailwind utilities in the updated report template generate correctly. No browser/server, business-data or backend calculation changes; user reviews the resulting layout next.

## Product-profit calculation shown in finance — 2026-10-09

User requested seeing the purchase/sale totals that explain the displayed product profit. Finance now shows VAT-exclusive product sales after confirmed refunds, minus the historical cost of those sold units after refund reversals, and the existing product-profit result. It explicitly distinguishes cost of sold units from all inventory purchases during the selected period; delivery, buffer and other business expenses remain separate. The gross cash/product/delivery breakdown is retained below, without duplicating the former cost/profit rows.

The report adds `product_sales_net` and signed `product_rounding_net` from the existing Decimal line calculations. Existing margin arithmetic is unchanged: each line's profit is rounded from unrounded VAT-exclusive values. Thus sales net minus purchase net plus the signed rounding contribution equals profit exactly, including across refunds. A nonzero contribution is shown as a cents-rounding row; it is not a business expense. Unknown purchase costs retain known net sales but leave cost, rounding and profit unavailable. Ambiguous event allocations leave all these components unavailable instead of publishing incomplete totals.

71 backend business/accounting foundation/report tests passed on disposable in-memory SQLite, including two new reconciliation tests covering both rounding directions, line-level rounding, refund reversal and unpaid-cost exclusion. All 28 focused frontend tests, scoped ESLint, Nuxt typecheck and report script/template compilation passed. No schema/business-data, external provider, environment, server/browser, deployment or push changes. Browser layout review remains with the user.
