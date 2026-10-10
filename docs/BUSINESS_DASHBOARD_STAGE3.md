# Business dashboard stage 3 — operations

Date: 2026-10-09. User authorized this stage after reviewing sales/finance; review of the operations page is the next checkpoint. Full business/net profit and combining delivery/buffer contributions remain deferred until the user agrees the calculation with their accountant.

## Implemented scope

- Protected, GET-only `/api/business/operations/` uses the existing independent business session and dashboard permission, with private no-store responses. No new schema or credentials.
- `/business/operations` now has a real Georgian operations component, replacing its foundation placeholder. It uses the existing design tokens, shared buttons, typography, light/dark theme and Tailwind only.
- This page shows a current snapshot and saved history, rather than inheriting the financial period filter and accidentally hiding old outstanding cases. Existing test records are explicitly included. Refresh/entry/filter/pagination requests obtain fresh database results; there is no polling or scheduler.
- Physical returns: awaiting order/unit totals, received/not-required totals, separate filters and pages. Receipt state and the order's saved payment state are separate. Waiting cases are ordered oldest first. Each case shows complete quantity totals, its first five product names/company codes and the total product count; no buyer PII or private supplier SKU is returned.
- Owned stock: receipt-lot balances subtract only non-restored allocations. Positive balances show receipt date, days since this batch's receipt, received/remaining units and historical gross purchase value. Supplier stock is excluded. Unknown-cost units retain a missing full valuation and a separately labelled known subtotal. Invalid negative lot balances are flagged rather than presented as a complete valid valuation. All summary totals cover the full matching dataset, not only the visible page.
- Payment states: pending/authorized/refund-pending, failed and saved monitoring issues have separate counts and filters. They count transaction attempts, not unique orders or lost customers. A paid transaction without an order is visible. All currencies retain their currency label; amounts are not aggregated across currencies. The latest saved check time is shown where present, without implying a new bank check. Raw provider payloads, checkout snapshots, free-text bank errors, tokens and IDs are not returned.
- Synchronization: latest stored Cross Motors and EasyWay reports, their separate latest stored success times, and whitelisted validated integer counts. Missing/invalid counts remain unknown. Absence of a report is not labelled failure or proof that a scheduler is absent. EasyWay's existing omission of unchanged successful checks is explained. Raw report summaries, item JSON and run-error text are excluded.
- Return, stock and payment lists each have independent 20-row pagination. Filter/page inputs are validated; pages beyond the current last page are normalized. Refresh errors clear old values instead of substituting zeros. Late responses are discarded; requests are aborted and private data cleared on unmount. Revoked business access redirects to login without changing storefront login.

## Verification

- 44 backend tests passed on disposable in-memory SQLite: 11 new operations tests plus existing business-auth and return-foundation tests. Covers receipt/payment separation, old waiting cases, complete totals across pagination, consumed/restored stock, unknown/historical costs, Tbilisi dates, negative balances, transaction filters/currencies/orphans, synchronization history and sanitized payloads, input/permissions/GET-only/no-store behavior.
- The operations read-path test enforces SELECT-only SQL, denies outbound socket/DNS calls and checks a bounded query count (at most 17 queries for the populated fixture). This is not a deployed PostgreSQL performance measurement.
- 33 focused frontend tests passed, including five new operations tests for filter/page request races, mutable query snapshots, refresh failure, authorization isolation and unmount cleanup. Scoped ESLint and Nuxt typecheck passed. Operations and section-route scripts/templates compile without errors or style blocks.
- Local `npm run build` passed (4 minutes 29 seconds). All 110 static Tailwind utilities in the operations template exist in compiled CSS; the compiled client manifest confirms 17 public roots have no static dependency on the operations API code.
- No dev server or browser automation started. No existing business database or record was changed. No demo data was added to the user's database. No real provider requests, scheduler, environment/secret changes, remote database access, push or deployment.

## User review

Open `/business/operations` in the usual user-started local frontend. Review light/dark and narrow/desktop layout, return filters, stock balances/values/age, payment filters, saved synchronization statuses and refresh. Pagination appears when a list contains more than 20 matching records. Empty states and unknown values are actual results, not demo substitutions. Browser review remains with the user.

## Reusable selects and payment explanations — 2026-10-09

User requested the project's reusable dropdown instead of native selects in both operations filters. Both now use the existing `BaseSelect` with its `modelValue`/`update:modelValue` contract. Explicit handlers validate the selected option, assign the filter before fetching, and reset only its page. Return/payment card wrappers no longer clip the absolute dropdown panels; horizontal table overflow remains contained. Shared `BaseSelect` itself was not modified.

Payment group labels are shorter, with selected-filter hints explaining pending/authorized/refund-pending, failed attempts and saved review issues. Filtering scope is unchanged: ordinary paid transactions appear in financial/sales reporting, while paid transactions with saved review issues or missing linked orders can still appear here. No new all/successful filter or backend/payment behavior changes were made.

Five focused operations frontend tests, scoped ESLint and Nuxt typecheck passed. An ad hoc check of the compiled actual operations component verifies both BaseSelect update events, selected filter values, independent page resets, retained sibling filters, changing hints and ignored invalid/duplicate selections. No permanent test was added for this UI adjustment; no browser or server started. Earlier stage-wide build results above precede this focused review adjustment.
