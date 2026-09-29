# Accounting module: staged implementation

2026-09-30: order headings and XLSX show saved buyer type/company VAT answer.
Purchase unit gross and purchase total are hidden by default, including subtotals;
`show_purchase` enables both in HTML and XLSX. Net cost/profit calculations remain
unchanged. Unknown historical company VAT answers remain unspecified. Existing
order fields reused; no migration or remote data changes. 55 focused tests passed.

Staging prepared 2026-09-29: commerce 0034 already applied; accountant account
created with report-only permission; seeded 36 orders / 72 product lines / 42 mock
transactions across April-September. Existing catalog/order/payment rows verified
unchanged. Local Django Client against staging verified login/report/export;
deployed-site browser verification remains outstanding. Production untouched.
Explicit `accounting_demo --staging` is restricted to the approved Neon hostname
and database; `--staging --delete` safely removes only this marked demo batch.
Three seed/cleanup/remote target guard tests pass.

Accountant access stage authorized and completed locally on 2026-09-29: explicit
`commerce.view_accounting_report` permission (migration 0034), read/export-only
staff group and local `accountant` user. Admin index redirects to the report;
other admin model/action URLs are denied, including accidental extra model grants.
Own password change/logout remain available. No credentials stored in project files.
51 access/export tests passed; actual local account verified through Django Client.
Remote migration/account creation and deployment have not been performed.

Latest XLSX presentation: five metadata/title rows and spacer above row-7 table
header, selected period/status/search, alternating order-event shading, dark total,
numeric currency formatting, frozen identifiers/headings and landscape print setup.
Flat rows/calculation/filter semantics unchanged. 32 focused tests passed; desktop
Excel visual rendering remains user review.

Current presentation: visually grouped order/event blocks with order identity once,
product rows and subtotal, then delivery and full amount footer. Twenty complete
blocks per page; original payment/refund events remain separate. Period totals
include every page. Excel flat rows/calculations unchanged. Thirty focused tests and
desktop/mobile browser checks passed. This supersedes the ungrouped UI below.

Latest correction: markup percentage removed from ledger UI/XLSX at user request.
Product profit excluding VAT remains. Day/month/SKU/all filters and multiple-product
order rows are unchanged; order-level fees appear once. 26 focused tests passed.

## Latest additions

Day/month ranges and SKU input restored; status now paid/refunded/all. All includes
original payments and signed refund reversals by event date. SKU matches only the
product, so order-level fees/full cash are deliberately blank in that mode (no
fictional per-product delivery allocation). Added markup %; profit remains product
margin before other expenses. Excel uses identical filtered signed rows.
Local mock batch expanded to 36 orders/72 distinct item SKUs across Apr–Sep 2026,
including 1–3 items per order, varied prices/quantities and six full refunds.
Non-demo financial rows verified unchanged during transactional replacement.

## Current UI — single ledger (supersedes historical stages below)

User requested one table and totals, no tabs. Implemented start/end dates plus
successful/refunded selector. Successful rows use payment date and exclude orders
with any confirmed refund; returned rows use refund date. Fixed VAT 18%. One row
per product; shipping/buffer/payment total only on first row of each order event.
Full-period totals span all pages. Single-sheet XLSX shares exactly these rows and
totals. 43 tests passed; browser verified filters/totals/export and one-table layout.
Local demo batch recreated with complete purchase costs, unrelated orders unchanged.
No remote deployment or accountant accounts. Historical designs below are superseded.

## Latest correction — supersedes historical stage descriptions below

User confirmed VAT payer status and requested fixed 18% with no selector. UI/XLSX
now always calculate purchase/sale VAT at 18%; old tax_mode parameters are ignored.
Only orders/items with confirmed captured payments or confirmed refunds appear.
Fulfilment statuses are removed; paid/refunded labels derive from confirmed events.
Pending demo data stays in the database but is excluded from accounting and export.
Summary now shows confirmed cash events and net known product markup after refunds,
without the duplicate order-created summary. 41 targeted tests passed, including
unpaid exclusion from XLSX, fixed VAT, and absence of shipping/refund-pending labels.
No schema changes or remote deployment; accountant account remains deferred.

## Status and authorization — 2026-09-29

Stages 1–5 including XLSX export are complete locally. User subsequently authorized
local demo data, now available for review. Accountant accounts and staging fixtures
have not been created. Stop here before accountant permissions/account creation.

The user requested incremental work, not the entire module in one task. Complete
and report one bounded stage at a time. There is a mandatory user-review stop
before accountant permissions, groups or account creation. Initial report views
must be superuser-only, including direct URLs and exports. Never temporarily make
reports available to every staff user while the dedicated access stage is deferred.

No production/staging database changes, deployment, provider calls, email or
scheduler changes are authorized by this design stage. Keep existing checkout,
payment/refund, stock, receipt and public API behavior intact.

## Agreed product rules

- Supplier purchase price and customer sale price are VAT-inclusive in the user's
  intended 18% VAT model. FlexDrive plans VAT registration; the effective date has
  not been supplied. Do not mark the company already registered or infer its status
  from `Order.company_is_vat_registered`, which describes the BUYER.
- Reference: `FlexDrive_Prices_Paired_Updated.xlsx`, Subaru rows 5–14, columns J:P.
  The first ten rows were inspected in the preceding discussion. Supplier retail
  price/comparison columns K/Q are outside scope, including their missing-price errors.
- Individual product markup remains the existing pricing mechanism. Do not change
  catalogue pricing or add a category/bulk pricing feature for accounting.
- Proposed report includes a summary, orders, product lines, payments and refunds,
  arbitrary date/month filtering, search, and XLSX export using the same calculations.
- Delivery is counted once per ORDER, never once per product. Target customer fee
  for Tbilisi is GEL 10; regional fee is carrier quote plus GEL 3 buffer. Store/report
  actual historical values, not hard-coded 10/3 multiplied by historical counts.
  Latest user instruction explicitly defers setting either tariff: leave current
  pricing configuration unchanged and report the existing dynamic order fields.
- Delivery fees are not automatically profit. Product margin excludes delivery.
  Regional buffer is shown and summed separately, with refund adjustments separate.
- Later staging-only test fixtures should cover different months, multiple items,
  shipping routes, pending/failed/paid transactions and cross-month refunds. No
  provider calls, real notifications or production fake sales.

## Audit evidence and integration points

| Area | Existing implementation | Required extension / constraint |
| --- | --- | --- |
| Catalogue pricing | `catalog/models.py`, `effective_markup_percent`, `calculate_customer_price` | Current supplier price is mutable; it cannot reconstruct historical cost. |
| Card preparation | `commerce/card_payments.py`, `_build_checkout_snapshot` | Snapshot already stores item sales prices, identities, quantities and delivery. Add private cost facts before bank redirection, inside snapshot integrity coverage. |
| Snapshot compatibility | `CHECKOUT_SNAPSHOT_VERSION = 1`; `commerce/bog_callbacks.py`, `_create_order_from_paid_snapshot` accepts version 1 | Preserve in-flight version-1 snapshots. Add an optional versioned accounting block, with absent old blocks treated as unknown. Never rehash/rewrite old snapshots. |
| BOG order finalization | `commerce/bog_callbacks.py`, `_normalize_snapshot_items`, `_create_order_from_paid_snapshot` | Normalizer explicitly rebuilds a whitelist. Carry and validate the new private fields through normalization and item creation; never read today's supplier price during finalization. |
| Direct checkout | `commerce/services.py`, cart `OrderItem.objects.bulk_create` and buy-now `OrderItem.objects.create` | Capture equivalent facts from the locked product. Preserve disabled COD behavior; do not enable it. |
| Bank payload | `commerce/card_payments.py`, `_start_prepared_bog_payment` | Explicit basket whitelist currently sends identity/description/quantity/sale price. Keep cost and accounting data out of it. |
| Order items | `commerce/models.py`, `OrderItem` | Already stores identity, sale unit price, quantity, line total. No historical supplier cost or tax treatment yet. |
| Delivery | `commerce/delivery_quotes.py`, `delivery_order_fields`; `Order` | `carrier_delivery_cost`, `delivery_margin`, `delivery_price`, provider and location snapshots exist. Reuse them. Internal delivery's carrier cost is hard-coded zero; that does NOT establish actual fulfilment cost as zero. |
| Delivery settings | `config/settings.py` | Code defaults are internal fee 0 and regional margin 2. Effective environment values were not inspected. User deferred tariff changes; keep defaults and configuration unchanged. Future tariffs affect new quotes, never rewrite historical order amounts. |
| Financial events | `PaymentTransaction.action/status/amount/currency/captured_at/refunded_at` | Authorization and failed/pending attempts are not money received. Existing paid sales later refunded must remain visible in the original period. Missing timestamps are exceptions, not silently replaced with `updated_at`. |
| Full refunds | `commerce/bog_refunds.py`, `_prepare_bog_full_refund`, `_mark_refund_completed` | Refund request context references sale payment ID; confirmed refund timestamp exists. Full refunds restore stock through existing workflows. Partial/ambiguous refunds are review cases, not automatically full reversals. |
| Paid without order | Existing BOG finalization/reconciliation records unresolved paid states | Include in payment exceptions and appropriate received-money reporting without inventing product sales/cost. Resolve deduplication against eventual order creation. |
| Customer serializers | `commerce/serializers.py`, order/item serializers; views/urls | Keep public contracts unchanged. No purchase costs, margins or tax-document data in customer responses or receipts. |
| Receipts | `commerce/receipts.py`; immutable `OrderReceipt.document_snapshot` | Existing receipts are not a purchase VAT ledger. Preserve issued snapshots and their rendering. |
| Deletion | `ProtectedFinancialQuerySet` blocks ordinary deletion; explicit hard-delete escape exists | Do not add a general delete capability. Any later fixture cleanup is restricted to a known staging test batch with referential checks. |
| Dates | `config/settings.py`: UTC, `USE_TZ=True` | Build report boundaries in `Asia/Tbilisi`, then convert to UTC. Use inclusive start/exclusive next-day end. Do not change application-wide timezone. |

## Calculation contract to implement and test

For the agreed standard-rate example (and only where that treatment applies):

- purchase net = purchase gross / 1.18;
- sale net = sale gross / 1.18;
- included VAT = gross minus net;
- product markup amount excluding VAT = sale net minus purchase net;
- product markup percentage = (sale net / purchase net - 1) * 100, undefined for
  zero/unknown purchase cost, not an invented 0%.

Example: purchase 15, sale 35 -> purchase net 12.71, sale net 29.66,
markup net 16.95, purchase VAT 2.29, sale VAT 5.34, markup 133.33% displayed.
Workbook example: purchase 340, sale 410 -> purchase net 288.14, sale net
347.46, markup net 59.32, markup 20.59% displayed. Do not calculate markup from
already rounded unit values. Use Decimal, never binary float.

Proposed rounding contract for review with the accountant:

1. Gross unit prices are stored money; multiply by quantity to get the authoritative
   gross line total. Split VAT at line level using sufficient internal precision.
2. Round net line amount to cents with an explicit HALF_UP rule; VAT line amount is
   gross line minus rounded net, so gross = net + VAT exactly.
3. Match workbook markup: subtract unrounded net line amounts, then round the
   result to cents. Preserve an explicit residual so sale net = purchase net +
   markup + rounding adjustment. For purchase 340 / sale 420, rounded nets are
   288.14 / 355.93, markup 67.80 and adjustment -0.01. Unit displays are not
   operands for totals; reports must retain and reconcile the adjustment.
4. Sum line components into orders and periods; do not divide an aggregate gross
   total afresh or multiply a rounded unit net by quantity. For example purchase
   15 x 3 has gross 45 and net 38.14, not 12.71 x 3 = 38.13.
5. Reverse original saved/report-versioned components for full refunds. Do not
   recalculate using current price, VAT settings or a different rounding policy.
6. Match source invoice amounts where supplied; document any rounding allocation
   explicitly. Do not claim the proposed operational rounding replaces invoice rules.

Computed included purchase VAT is NOT confirmed deductible VAT. Supplier API cost
is a quoted purchase-cost basis, not proof of acquisition/invoice/payment. Store
provenance and confirmation status. Invoice-confirmed actual cost corrections need
an audited adjustment path and must not overwrite original facts.

The product report cannot produce a complete VAT return: purchases of unsold stock,
other expenses, invoice dates and credit notes are not currently captured. Do not
label the difference between VAT on sold items as final monthly VAT payable. The
initial report is an operational accounting aid, not a full purchasing/general ledger.

Missing historical cost remains unknown. Show count/value of incomplete rows and
coverage for known-cost margins; never turn missing costs into zero and inflate profit.
Similarly, unknown VAT treatment stays unclassified, not silently 18% or exempt 0%.

## Delivery and period rules

- Order subtotal = sum of product gross line totals; total = subtotal + customer
  delivery fee. Regional carrier quote + buffer must equal customer delivery fee.
- Tbilisi internal fee is a collected delivery amount. Preserve unknown actual
  internal-delivery cost separately from the existing carrier placeholder 0.
- Product detail export links to an order ID. Order-level shipping appears in the
  order sheet/summary once; it is not added to every exported product row.
- Report collected regional buffer and refunded buffer separately, then net them
  where supported. Full-order refunds can reverse original components. Partial
  refund allocations must be explicit/reviewed, never guessed from refund amount.
- Order-date views, payment-confirmation-date views and refund-confirmation-date
  views need separate clearly labeled filters. A customer payment is not proof of
  product handover or tax recognition. Do not use payment date as an unqualified
  statutory sales-recognition rule.
- Match each money event to a stable source transaction ID. Avoid counting both
  authorization and capture/sale, or both order total and its payment, as revenue.
- Summaries and exports share a query/calculation service. Aggregate order-level
  and item-level data separately to avoid multiplication through database joins.

## Ordered stages and completion checks

### 1. Audit and design — complete

This document and session memory are the only changes in this stage. No executable
behavior changed, so no application tests/migrations were run or required.

### 2. Historical accounting facts and calculation foundation — complete locally

- Add focused private nullable purchase-cost/provenance snapshots to the existing
  commerce models. Exact schema is finalized against the audited paths above.
- Snapshot facts at checkout preparation; copy them into order items after verified
  payment. Existing snapshots/orders lacking facts remain usable and unclassified.
- Implement pure Decimal calculation helpers with explicit tax inputs, calculation
  version and rounding rules. No default assumption that VAT registration is active.
- Protect snapshots from stale admin forms; add constraints and readonly admin
  fields where needed. No edits to public serializers or existing receipt documents.
- Tests: workbook examples, quantities/rounding, null vs zero, percentage precision,
  supplier-price changes during pending payment, old/in-flight snapshots, callback
  retries, guest/account cart/buy-now and no leakage to bank/customer payloads.
- Complete local verification and report this stage before moving to report UI.

Implemented `accounting_snapshots.py` and `accounting_calculations.py` plus private
OrderItem fields `purchase_unit_gross`, `purchase_cost_source`, and
`purchase_cost_recorded_at`. Card snapshots are covered by existing integrity
hashing; direct checkout captures locked product values. Finalization copies the
saved cost, never the latest catalogue cost. Optional legacy blocks remain valid.
Readonly fields appear in the EXISTING order item inline, not a separate section.
Model saves preserve historical facts; queryset updates reject cost overwrites.
No tax rate/registration/deductibility is inferred or activated.

Migration `commerce.0033` applied locally only. Hashes of existing columns in all
27 catalogue/commerce tables matched before/after; all 32 legacy order items retain
unknown cost. No backfill, remote migration, provider call or deployment occurred.
109 targeted tests passed across calculation, callback, SKU, refund, reconciliation,
delivery and payment-toggle suites (two old delivery fixtures needed a company SKU;
their two tests passed on rerun). Migration drift and whitespace checks passed.

### 3. Report queries, dates, refunds and delivery — complete locally

- Build the canonical report data service, explicit inclusion/exclusion rules,
  exception handling and separate financial-event views.
- Reuse existing dynamic delivery amount, carrier quote and buffer snapshots;
  preserve historical values. Tariff changes to 10/3 are explicitly deferred.
- Test one/many-item orders, delivery counted once, failed/retried/orphan payments,
  refunds in later months, incomplete costs, month-end Tbilisi boundaries and query
  counts. Do not expand actual provider refund features.

Implemented `commerce/accounting_reports.py`:

- `ReportPeriod(start, end)` accepts inclusive calendar dates; `months()` accepts
  inclusive YYYY-MM ranges. Boundaries are Tbilisi midnight converted to UTC,
  lower-inclusive/upper-exclusive. Application timezone remains unchanged.
- `build_order_report()` uses order creation dates, including all order statuses;
  it is an ordered-value report, not received money. Rows preserve saved item IDs,
  codes, names, amounts, purchase provenance and explicit calculation results.
  Summary reports cost/margin coverage and unknown-cost sale value separately.
- `build_cash_report()` uses captured/refunded timestamps and transaction IDs.
  Only confirmed sale/capture and refund events count. Authorization, failed and
  pending attempts do not count. Totals are separate by currency, and order totals
  are never added to cash totals. Original receipts remain in their original period
  after refund/cancellation. Separate receipt/refund components reconcile to net.
- Order-level delivery is counted once. Internal delivery's actual expense is
  unknown, not the existing zero carrier placeholder. Regional quote/buffer use
  saved values; 10/3 defaults and environment settings remain unchanged.
- Only an unambiguous full GEL payment matching its order receives a product/
  delivery allocation. Full refunds also require the saved sale transaction link,
  matching provider/currency/amount, valid chronology and one completed refund.
  They reuse historical item cost and the caller's same historical tax policy.
  Refund component amounts are positive reversals, summarized separately.
  Partial, multiple or invalid refunds remain cash events with unallocated amounts
  and review codes. No provider refund or stock behavior changes.
- Paid-without-order is cash with an explicit exception, never invented products.
  Confirmed events lacking their event timestamp are global undated exceptions;
  they cannot be silently attributed to a selected month using updated_at.
- Tax inputs default to unknown. Future UI must display coverage alongside known
  subtotals (zero covered rows does not mean zero margin). It must resolve explicit
  historical tax treatment before displaying VAT/margins as classified amounts.
- Read-only services expose no URLs or permissions. Queries prefetch relations:
  tested order reports use 2 queries and populated cash reports 4, independent of
  tested order count. Maximum 10,000 root rows; oversized reports fail explicitly
  instead of publishing partial totals. Future UI handles pagination separately.
- 24 report tests plus 13 foundation tests passed (37 total); migration drift and
  whitespace checks passed. No schema change, migration, local business-data write,
  remote call, deployment or real/staging fake-data insertion in this stage.

### 4. Superuser-only accounting admin section — complete locally

- Add summary, orders, product lines, payments/refunds and exception views.
- Search/filter/pagination, links to relevant details, readable Georgian labels.
- Enforce superuser checks on every view/action, including direct links, until the
  separately authorized accountant access stage. No groups/accounts created here.
- Browser test navigation, filters, empty states, totals and unauthorized requests.

Implemented `/manager-fd/accounting/` and a superuser-only link on the admin home.
Five tabs: summary, orders, product lines, confirmed payments/refunds and review
exceptions. GET-only view enforces active staff AND superuser checks in addition
to Django admin authentication/no-cache wrapping. Even staff with all commerce
permissions cannot access it. No new group/account or public API was added.

Day/month filters use the existing report service. Search by order number, product
name or either SKU selects whole matching orders and their complete totals; it
also applies to cash events linked to those orders. Tables paginate at 50 rows,
preserving filters. Undated events paginate separately at 25 and explicitly remain
global, unaffected by period/search. Row-limit failures display an error, no partial
totals. Links open existing private order/payment admin details.

Tax defaults to unknown; an explicit `scenario18` UI option previews the user's
18%-inclusive spreadsheet model. It is labeled hypothetical, not confirmed tax
treatment or deductible VAT, and writes no tax settings/data. Percentages and money
display 2 decimals; historical precision is unchanged. Known-margin coverage and
unknown cost are visible. Template escaping protects stored/user-supplied text.

51 targeted tests passed (14 UI/access + 24 report + 13 calculation/snapshot).
Browser QA used an isolated in-memory SQLite database and temporary test users,
with no writes to local business data. Verified admin home link, month filters,
18% example, search/empty results, tab navigation and 1440px/390px layout. Temporary
preview server/script removed afterward. No new migrations or remote deployment.
Deploy existing commerce.0033 and collect static assets with normal deployment.

### 5. XLSX export and reviewable delivery — complete locally

- Same filters and calculation service as admin; summary/orders/product lines/
  transactions sheets, explicit timezone/date semantics, numeric currency cells,
  headers/filters/frozen rows and safe handling of spreadsheet formula-like strings.
- Do not expose provider secrets, raw provider JSON or unnecessary personal data.
- Verify exported totals, missing-value treatment, stable row ordering and practical
  volume limits; protect export endpoint with the same superuser requirement.
- Test exports and provide a safe synthetic preview if requested, separate from any
  real database. An export endpoint is application code, not a one-off workbook build.

Implemented same-view `export=xlsx` under the existing superuser check. Five sheets
use the same complete filtered report data and table definitions as UI. Numeric
money, explicit inline strings (including formula-like text), frozen styled headers,
column widths and filters. Standard-library OOXML ZIP writer, no dependency added.
Summary identifies period/search/timezone/tax scenario, coverage and global undated
count; undated global detail remains in admin rather than filtered workbook rows.
Three focused tests passed: ZIP/XML/numeric/formula-safety/filter checks, forbidden
staff export, and demo creation/duplicate rejection/cleanup preserving unrelated rows.

Latest user authorized local fake data: `accounting_demo` created 7 orders, 9 items,
8 mock transactions for July–September 2026. All marked `FD-DEMO-202609-`, no product
links, real provider references, notifications or stock effects. Demo tariffs 10/3
are sample historical values only. Search this prefix, select 2026-07-01 through
2026-09-30, optionally select the 18% model, then download. Verified totals: ordered
424 GEL; received 379; refunded 93; net cash 286. Cleanup via local-only command
`accounting_demo --delete`; markers/link checks and transaction protect other data.
No real accountant account, remote fixture, deployment or additional migration.

### Mandatory stop: user reviews BEFORE accountant access

Summarize implementation, tests, migrations and limitations. Do not create a staff
account/group, assign permissions, generate credentials or invite the accountant.
Wait for the user's review and instruction to start that separate stage.

### Later, separately authorized stages

1. Accountant-only permission/group/account setup and adversarial access tests.
2. Staging rollout and marked multi-month synthetic dataset with controlled cleanup,
   no live integrations/notifications, then user/accountant review.
3. Fix review findings; production backup/migrations/deployment and browser checks.
   No fixture data or real-account credentials in committed files.

## Information still needed (does not block capturing gross cost facts)

- Actual effective date of FlexDrive VAT registration, plus classification of earlier
  transactions. Do not request or invent a date before registration exists.
- Source purchase invoice fields and who confirms deductibility/actual cost; decide
  whether the first release records confirmation only or includes audited corrections.
- VAT treatment and invoice basis for internal delivery, EasyWay and the buffer.
- Accountant acceptance of rounding/recognition conventions. Missing decisions must
  remain visible in reports rather than silently becoming tax assumptions.

These items block activation of confirmed tax reporting, not basic private snapshot
capture or implementation with explicit unknown treatment. Do not introduce a new
tax/purchasing system or change checkout charges to resolve them by assumption.
