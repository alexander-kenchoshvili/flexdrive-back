# Project Instructions

## Accounting Production Migrations - 2026-10-04

- After user-confirmed production code deployment, applied only commerce 0033
  (historical purchase-cost fields) and 0034 (accounting report permission) to the
  explicitly supplied production database, in one transaction. Catalog pricing
  dependencies were already applied; no pricing reset performed.
- Verified the target migration plan is empty, new fields query successfully and
  view_accounting_report permission exists. Existing product/category/order/item/
  payment/user column values verified unchanged using pre/post row hashes.
- No demo data or accountant account created; their creation remains deferred.
  Deployed production browser verification was not performed.

## Accounting Buyer Details And Optional Purchase Columns - 2026-09-30

- Order headings show saved buyer_type and, for legal entities, saved
  company_is_vat_registered (yes/no; null remains explicitly unspecified).
  XLSX includes both buyer columns for sales and refunds; no checkout changes.
- `show_purchase` checkbox defaults off, hides gross purchase unit/total columns
  including order/period totals. Net cost and product profit remain visible.
  Checkbox submits the GET form; pagination/export URLs retain the selection.
  XLSX omits hidden columns entirely using the same column selection helper.
- 53 existing access/UI/export tests plus 2 new visibility/buyer parity tests passed.
  No migration or remote changes in this stage; browser visual review remains.

## Accounting Staging Preparation - 2026-09-29

- User authorized staging accountant access and demo data. Commerce 0034 and its
  dependencies were already applied (migration plan empty); no migration run needed.
- Created staging `accountant` in `FlexDrive Accountants`, active staff/non-superuser,
  with only `commerce.view_accounting_report`. Password supplied in session only.
- Seeded 36 marked orders, 72 distinct product lines, 42 mock payment/refund events,
  April-September 2026. Existing catalog products/categories and pre-existing
  orders/items/payments verified unchanged by row hashes in the same transaction.
- Local code against staging DB verified accountant login, redirect, report and
  XLSX. Deployed-site browser verification remains outstanding. Production untouched.
- `accounting_demo --staging` permits only the exact approved Neon staging host
  and neondb database. Default stays SQLite-only; all other remote targets denied.
  `--staging --delete` retains existing marker/link safety checks. Three demo
  creation/cleanup/remote-guard tests pass. Push this command/test change as well.

## Accountant Access - 2026-09-29

- User explicitly authorized the previously deferred accountant account stage.
- Local SQLite account `accountant` belongs to `FlexDrive Accountants`, with only
  `commerce.view_accounting_report`; active staff, never superuser. Credentials
  were provided privately in conversation and must not be recorded in files.
- Login redirects to the accounting report. Filters/export and own password change
  are allowed; other admin routes are denied, with sidebar/site links hidden.
- Migration commerce.0034 applied locally only. No staging/production account or
  deployment performed. 51 access/export tests passed; actual local account login,
  redirect, report, XLSX and forbidden product/user pages verified with Django Client.

## Accounting Excel Readability

- Export now starts with FlexDrive report title, exact period, selected status,
  order count and name/SKU filter; includes GEL/VAT/timezone and relevant date/sign
  semantics. Table header is row 7; data begins row 8. Flat spreadsheet retained.
- Alternating pale bands follow complete financial-event groups, not individual
  product rows. Dark title/header/total, wrapped labels, tuned column widths,
  numeric 2-decimal money with red parenthesized negatives. Freeze first 7 rows
  and 4 identity columns. AutoFilter excludes the static report total.
- Landscape A3 print setup fits width, repeats title/header rows, adds page numbers.
  No dependency, calculation, data or permission change. 32 focused export/UI/demo
  tests passed, including metadata, banding, frozen panes, numeric/sign safety,
  correct totals and filters. Actual desktop Excel rendering not checked.

## Accounting Order Blocks - Latest UI

- User found repeated order numbers confusing. UI now uses a bordered block per
  financial event: one order heading/date/status, product count and unit count,
  product-only table, subtotal, then delivery/buffer/full order amount once below.
- Paginate 20 complete event blocks, never split an order's products across pages.
  All-mode original receipt/refund remain separate dated/status-labeled blocks;
  grouping uses transaction IDs, not display text. Period totals cover all pages.
  SKU search still product-only and hides order fee footer. XLSX remains flat for
  spreadsheet filtering with identical underlying rows and totals.
- 30 UI/export/demo tests passed, including order-boundary pagination. Browser
  verified 3 products/4 units in one block, one order heading, 795 GEL total,
  desktop fit and mobile overflow containment. No real data/schema/remote changes.

## Accounting Product Name Search

- Existing SKU input now labeled product name or SKU; substring search includes
  saved product_name as well as both SKUs in DB and line filtering. Same export
  filters and product-only totals. Two focused name/export/SKU tests passed.
- Verified local two-item example: FD-DEMO-202609-32, paid September 6 2026,
  DEMO-FD-32-1 mirror 110 GEL and DEMO-FD-32-2 brake pad 170 GEL; full order 301 GEL.
  Select Sept 6 start/end, paid, blank search to see both rows and shipping together.

## Accounting Markup Percentage Removed - Latest Decision

- User removed the markup-percent column again. Ledger UI and XLSX retain product
  profit excluding VAT (before other expenses), but no percent column or explanation.
  This does not change catalogue markup pricing or internal calculation precision.
- Multi-item orders remain adjacent product rows sharing order number. Delivery,
  buffer and full order amount appear only on the first row. Existing filters and
  72-line demo dataset unchanged. 26 accounting UI/export/demo tests passed.

## Accounting Filters And Expanded Demo - Latest Decision

- Restored day/month ranges and direct SKU substring search (company or supplier
  SKU, case-insensitive). SKU selects only matching product lines, not sibling
  products. In SKU mode order-level shipping/buffer/full payment columns and totals
  stay blank: these cannot be attributed to one product without invented allocation.
- Added "all": confirmed original receipts plus confirmed refunds by event date;
  refunds negate quantities and line/order totals, preserving positive unit prices
  and markup %. Net totals subtract refunds exactly once. Paid-only still excludes
  any order with completed refunds. Refunded-only displays positive reversals.
- Added markup-percent column (15 -> 35 gives 133.33%); existing product profit is
  VAT-exclusive markup before other expenses (16.95), not net company profit.
  Percent is not summed. Excel shares all filters, signs and numeric cells.
- Local demo refreshed atomically: 36 orders, 72 distinct product SKUs/lines,
  42 mock transactions across April–September 2026, 1/2/3 lines per order and varied
  quantities/prices. 6 refunded orders; paid-only shows 30 orders/54 lines. All view
  has 90 event lines and net 10888 GEL; refunded-only 2183 GEL. Unrelated order,
  item and transaction values verified unchanged. No stock/providers/users affected.
- 25 UI/export/demo tests passed, then two focused export-filter/demo tests passed
  after adding exact signed XLSX/markup/SKU assertions. No schema/remote changes.
- Isolated browser QA confirmed day/month visibility, all-status signed totals,
  unchanged totals across pages and exact SKU-only rows. Preview server removed.

## Single Accounting Ledger - Latest User Decision

- Replaced all accounting tabs with ONE product table, start/end dates and only
  successful/refunded status filter. Fixed 18% VAT; one-sheet XLSX matches table
  and includes full-period totals at bottom. No search/month-mode/tax selector.
- Successful uses confirmed payment date and excludes any order with a completed
  refund, including refunds outside selected period. Returned uses refund date.
  Unpaid/orphan orders are absent. GEL ledger only. Delivery/buffer and full payment
  amount appear on first product row only; quantity/cost/sales/profit totals cover
  all pages. Purchase cost is not evidence of supplier cash settlement.
- commerce/accounting_ledger.py reuses validated saved order/payment facts. Partial
  or ambiguous refund allocations do not invent product-cost/profit reversals.
  Internal arithmetic safeguards remain, with no accountant review UI.
- 43 focused tests passed; isolated browser QA confirmed one table/no tabs,
  successful/refund filters, totals and XLSX download. Temporary preview removed.
- Local marked demo batch safely recreated with ALL purchase costs populated;
  unrelated orders verified unchanged. July–September successful: 5 orders,
  6 items, gross 286, purchase gross 90, product profit 101.70 GEL. Returned:
  1 order / 2 items, gross 93, purchase gross 30, profit reversal 33.90 GEL.
- No new schema, remote changes, or accountant account. User review remains next.

## Accountant Review Section Removed - Latest Decision

- User removed the accountant-facing exceptions/review concept entirely. No review
  tab, undated global query/count, issue-note columns, unallocated/unknown-cost alerts
  or review worksheet in XLSX. Four remaining sections/sheets: summary, orders,
  products, payments/refunds. Preserve internal arithmetic/allocation validation;
  do not invent missing amounts or change operational payment recovery behavior.
- Orders are one row per order; products are one row per order item; cash is one
  row per confirmed payment/refund event. User requested explanation of overlap,
  not authorization yet to merge these three remaining sections.

## Accounting Simplification - Latest User Decision

- User confirms FlexDrive is a VAT payer and explicitly requires fixed 18% in
  accounting from the start. Removed unknown/scenario selector; stale tax_mode URL
  parameters are ignored. UI and XLSX always use 18% for purchase/sale calculations.
- Accountant sees only orders/items backed by confirmed captured sale/capture or
  confirmed refund records. Pending/failed/authorization-only orders are excluded,
  including the pending demo order (retained in DB, hidden from accounting).
- Remove fulfilment states from accounting; show only paid/refunded derived from
  confirmed events, not mutable delivery/payment workflow flags. Products also
  identify paid/refunded. Normal operational order admin is unchanged.
- Main summary displays confirmed cash totals and known product markup less
  confirmed refund markup. Removed duplicate order-created summary cards from UI.
  No new migrations, account permissions or remote deployment. 41 focused tests pass.
- This overrides earlier notes requiring unknown VAT/scenario UI and showing all
  order statuses. Dedicated accountant account is still deferred for user review.

## Domain Cutover Decision - 2026-09-28

- User deferred BOG reconciliation scheduler setup until migration to flexdrive.ge; do not provision it before that stage.
- flexdrive.ge must initially remain restricted to authorized testers, not publicly open. Establish and verify access protection before exposing the domain; noindex alone is not access control. Account for direct hosting URLs and required bank/provider callbacks without exposing the storefront.
- After restricted domain cutover, update domain-dependent configuration/URLs (frontend/backend origins, OAuth redirects, reCAPTCHA, email links, bank redirects/callback where applicable), configure payment reconciliation scheduler, and complete deferred integration/analytics checks before public launch.
- Cross Motors category-warning investigation confirmed existing category assignments are preserved; new supplier products are created Draft in category "ახალი" for manual categorization. Warning text is misleading, not evidence of category reassignment. No importer code or data changed during review.

## Production Progress Confirmed by User - 2026-09-28

- Live browser audit on 2026-09-28: backend app has only two Job components, crossmotors-sync and easyway-tracking; no BOG reconciliation job in this app or its displayed job history. An external scheduler was not checked.
- Both triggers are `0 0 * * *` in Asia/Tbilisi, while wrappers calculate UTC dates. This differs from documented UTC trigger: EasyWay first due execution is October 3 at local midnight, rather than October 2 UTC. Normalize timezone before relying on documented due dates.
- Latest Cross Motors scheduled run succeeded September 28 local time: 2030 updated, 0 created, 0 archived; category inference warnings remain in log for separate review.
- Latest EasyWay run succeeded by skipping under the ten-day wrapper; actual Django tracking command/provider/DB access is not proved by that skip. Neither job has component alert policies; app alerts shown were Failed Deployment and Failed Domain Configuration only.
- Audit was read-only: no job created, triggered, or schedule changed.

- User confirms contact and receipt environment variables were added last week.
- User observed successful Cross Motors sync reports in production admin; sync runs successfully at the longer pre-launch interval. Reduce cadence at launch as planned.
- User has not created orders/payments for current verification. No EasyWay report is expected for empty/skipped/unchanged successful scheduled runs.
- User recalls enabling payment reconciliation cron, but current live scheduler configuration and execution have not been verified. Do not state it is disabled solely from older preparation documents. Payment reconciliation stores per-payment issue/attempt fields and optional problem emails, not a batch report for every execution.
- Older handoff/deployment documents contain historical setup status; reconcile with these confirmations and live evidence before proposing repeated setup.

## Production Analytics Follow-up - 2026-09-24

- Existing GTM container GTM-MVNFL9TH and GA4 stream G-CKQC30CKYJ are reused for production; no separate property/container is required by the current plan.
- Production frontend GTM ID was corrected and deployed. Browser confirmed GTM, GA4 and Meta Pixel script loading, not end-to-end event delivery.
- User explicitly deferred full analytics verification until migration to flexdrive.ge and completion of site flows. Revisit page views/search/product/cart/checkout events, paid purchase values/company SKUs and browser/server deduplication then.
- Cookie consent handling/revocation remains outstanding; do not treat script loading as completion of analytics readiness.
- Cash-on-delivery is disabled by product decision and excluded from this verification scope.

## FlexDrive Internal SKUs - 2026-09-23

- Existing `Product.sku` remains PRIVATE supplier/legacy identity for imports,
  comparisons, supplier API and image transfer. Public product/cart/buy-now `sku`
  and `display_sku` expose ONLY `internal_sku`, with no supplier fallback. Public
  search no longer matches supplier SKU. Admin shows/searches both codes.
- Browser analytics and server Meta purchase IDs use company SKU. New BOG basket
  IDs also use company SKU; private payment/order snapshots preserve both codes.
- Root category groups 01–08 match the supplied workbook. Children inherit root
  group. `SkuSequence` retains high-water marks; admin save with a mapped category
  assigns `FD-XX-NNNN` atomically. Imports never allocate. Company code is readonly
  in admin and survives category changes/stale saves. Deleted numbers are not reused.
  Publishing without a company SKU is blocked in form, bulk action and database.
- Public slugs/canonicals/sitemap use FD codes. Stored slugs stay unchanged and old
  links still resolve. Do not expose the stored supplier-bearing slug publicly.
- Local migrations `catalog.0022`–`0024` and `commerce.0032` applied; 2,037 pairs from
  `FlexDrive_Prices_Paired_Updated.xlsx` imported locally, all matching, no conflicts.
  Existing values across all 26 catalog/commerce tables verified unchanged.
  Staging subsequently prepared with catalog.0022–0024 and commerce.0032, all
  2,037 workbook mappings imported. Existing staging test1234 assigned FD-01-0216
  from its lighting category; group 01 counter is now 216. Other existing product,
  category and order values verified unchanged by hashes in one transaction.
  Staging commerce_orderitem.internal_sku has SQL DEFAULT '' for old deployed
  checkout compatibility until code deployment. No code push/deploy performed by
  the agent. Unrelated pending pages migration was not applied.
- Production subsequently prepared: catalog.0022–0024 and commerce.0031–0032 applied
  atomically; all 2,030 existing products received their exact workbook codes.
  Seven workbook products absent from production were not created: CM-000537,
  CM-000860, CM-000974, CM-000975, CM-001065, CM-001155, CM-001156. Counters use the
  full workbook maxima, protecting these numbers from reuse. On return, assign their
  reviewed original mapping explicitly. Old product/category/order/order-item values
  verified unchanged by hashes. Production SQL defaults '' on orderitem.internal_sku
  and paymenttransaction.reconciliation_issue preserve old deployed insert behavior.
  No cron, bank/email call, or code deployment performed. Backend then frontend
  deployment and browser verification remain outstanding.
- `import_internal_skus --input <xlsx>` is dry-run by default; `--commit` fills
  unassigned codes atomically. It refuses duplicates, missing products, collisions
  and replacement of existing assignments. Only SKU columns are read for import.
  Supplier refreshes preserve assigned codes. Import also advances group counters.
- New COD/card orders snapshot both codes. Old orders/receipts and pre-migration
  payment snapshots retain original identifiers; no historical backfill. Admin
  supports both codes. See `docs/INTERNAL_SKUS.md` for rollout and verification.
- Latest verification: 153 focused tests passed, then 11 allocation/URL tests passed
  after extra sitemap/group coverage; PostgreSQL concurrency test skipped on SQLite.
  Frontend typecheck passed. Broader legacy tests have stock,
  delivery and catalog expectation failures; representative failures reproduced on
  unmodified HEAD; old Published-product fixtures now also need company codes.
  Browser and production PostgreSQL verification remain pending.
- On remote rollout apply catalog 0023 and commerce 0032, import reviewed SKU mapping,
  then catalog 0024. The latter refuses Published products without company codes.

## Payment Reconciliation Preparation - 2026-09-23

- User authorized preparing monitoring now; cron activation remains deferred.
  `reconcile_bog_payments` checks stale/unresolved BOG SALE transactions through
  the existing verified finalizer. It never initiates a charge or refund.
- Migration `commerce.0031_payment_reconciliation_monitoring` adds operational
  lease/attempt/issue/notification fields. Deploy migrations before command/admin use.
  Applied locally; 90 targeted monitoring/callback/payment/refund tests passed
  (including the added lease-expiry case). Migration 0031 also confirmed on staging
  and applied on production during SKU preparation; scheduler remains disabled.
- Empty/dry-run batches make no bank requests or send emails. Paid-without-order
  and missing-bank-ID cases require admin review, not blind order recreation.
- Per-payment leases, apply-time locking and state rechecks protect overlapping
  runs and callbacks. Refund/cancel workflows retain existing behavior.
- Admin displays/filter issues; optional `BOG_RECONCILIATION_ALERT_EMAIL` defaults
  empty (disabled). Problem-only emails use existing delivery, throttled per payment
  and unchanged issue to 24 hours. Job failure/nonexecution alerts are also required.
- No cron provisioned/enabled, no real bank/email calls or remote changes made.
  Production PostgreSQL concurrency verification and activation remain pending.
  Instructions: `docs/PAYMENT_RECONCILIATION.md`. This supersedes the older deferral
  of implementation below, but preserves deferred scheduler activation.

## EasyWay Tracking - 2026-09-22

- EasyWay sync reports: `commerce.EasywaySyncReport`, local migration `0030` applied.
  One private report per changed/problematic batch (or manual refresh), no empty,
  dry-run, skipped-only or unchanged-success reports. Exact counts, up to 50 details,
  safe order links, read-only admin with permission-controlled deletion. Report deletion
  never changes orders/history. Deploy migration before updated command/admin use.
  55 report/tracking/client/shipment tests pass; no remote API calls made for reports.

- `commerce/easyway_tracking.py` reconciles carrier history into existing order
  statuses. No customer-facing carrier text or new public serializer fields.
- `new` preserves the current order state; `taking` advances to processing;
  `taken/in_store/taken_store` advance to shipped; `delivered` advances to delivered.
  `canceled` records carrier cancellation only, with no order/refund/stock action.
- Paid-only forward progress; cancelled/refunding orders and local shipment
  cancellation are protected. Unknown/ambiguous events require admin review.
- Admin refresh and cron share a per-order database lease with short apply-time
  row locking. Preserve tracking fields when saving an older admin form.
- Local migration `commerce.0029_easyway_tracking` applied. 71 targeted tests pass;
  real cancelled shipment tracking was read successfully. Production migration,
  pickup/delivery lifecycle and production PostgreSQL verification remain pending.
- Cron command: `python manage.py sync_easyway_tracking --limit 100 --min-age-minutes 10 --max-seconds 600`.
  Pre-launch: sync every 10 days using the documented daily date-check wrapper,
  anchored to 2026-09-22; first due date 2026-10-02. At public launch switch to the
  direct command and `*/15 * * * *` (UTC). NOT provisioned/enabled.
  Empty batches make no carrier requests. Operator activation/cost review required.
- Deployment instructions and limitations: `docs/EASYWAY_TRACKING.md`.
- User deferred additional cancellation/refund features; do not expand that scope.

## Product Context

This repository is the backend for FlexDrive, an online auto parts store.

Important background:

- The project started from a copied backend of a previous online auto accessories store.
- Much of the existing business logic, API shape, admin behavior, and data model still reflects that earlier auto accessories project.
- The current product direction is a purpose-built auto parts ecommerce platform.
- Existing working ecommerce flows should be preserved unless a requested feature explicitly requires changing them.

Core backend capabilities that should be treated as valuable baseline behavior:

- Customer authentication and registration
- JWT/session-related auth behavior
- Customer profile / account cabinet APIs
- Product catalog APIs
- Cart
- Wishlist
- Checkout / orders / commerce flow
- Django admin and local admin workflows
- Security-related integrations such as reCAPTCHA, which have already been updated with new project keys
- Media/image handling and upload/storage behavior

Do not remove, bypass, or rewrite these areas casually. Preserve working behavior first, then adapt the domain model and API contracts deliberately.

## Technical Context

This is a Django backend using Django REST Framework.

Observed stack and patterns:

- Django 6
- Django REST Framework
- djangorestframework-simplejwt
- django-cors-headers
- python-dotenv based environment configuration
- Cloudinary/Pillow for media-related behavior
- Redis dependency present
- PostgreSQL driver present, with local SQLite development database present in the repository root
- Apps include areas such as `accounts`, `catalog`, `commerce`, `common`, and `pages`

Use the existing Django app boundaries before adding new modules. Prefer extending the relevant existing app when the feature clearly belongs there.

## Backend Working Rules

- Read models, serializers, views, urls, permissions, signals, and tests before changing API behavior.
- Preserve existing API responses expected by the frontend unless a coordinated frontend/backend change is being made.
- Do not change `.env`, secrets, reCAPTCHA keys, JWT signing settings, database credentials, Cloudinary credentials, or deployment secrets.
- Do not hard-code environment-specific URLs or credentials.
- Treat migrations carefully. Add migrations only when model changes require them, and keep them focused.
- Use this repository's virtual environment for Django/backend commands. Run management commands with `.\venv\Scripts\python.exe manage.py ...` from `C:\Users\kench\Desktop\flexdriveback`; do not try system `python` first.
- Do not delete existing fields or endpoints without checking frontend usage first.
- Keep validation in serializers/forms where that is the local pattern.
- Keep business rules server-side even when the frontend also validates them.
- Prefer explicit query optimization for catalog endpoints that return product lists.
- Avoid broad rewrites of working auth, cart, wishlist, checkout, or admin code during redesign-related tasks.

## Auto Parts Domain Direction

The business is no longer a generic auto accessories shop. Future backend work should move the catalog toward auto parts concepts.

Expected domain concepts may include:

- Make / model / year / engine compatibility
- OEM numbers
- Manufacturer part numbers
- Internal SKUs
- Brand / manufacturer
- Category and subcategory hierarchy
- Product condition
- Vehicle side / placement where relevant
- Fitment notes
- Stock status and availability
- Price ranges
- Search keywords and aliases
- Shipping or delivery constraints for large/heavy parts

Do not invent these fields blindly. Before adding schema, inspect existing `catalog` models and current frontend needs. When a new concept is needed, design it so it can support filtering, search, admin editing, and frontend display.

## Catalog And Filtering

Filtering will become a major feature for the auto parts store.

When adding or modifying filters:

- Keep filter parameters stable and documented through code/tests where possible.
- Validate filter values instead of silently accepting invalid combinations.
- Avoid expensive unbounded queries on product list endpoints.
- Consider indexes when adding fields that will be commonly filtered or sorted.
- Keep response payloads suitable for product listing pages: enough information for cards and comparison, without overloading each list item.
- Make frontend and backend naming consistent for categories, brands, compatibility, price, availability, and sorting.

## API Contract With Frontend

The paired frontend repository is expected at:

`C:\Users\kench\Desktop\flexdrivefront`

Frontend and backend are part of the same product effort. When changing an endpoint used by the frontend:

- Inspect frontend usage before modifying the response shape.
- Keep backward compatibility when practical.
- Coordinate breaking changes with frontend edits in the same task.
- Keep error response shapes predictable for forms and checkout flows.
- Ensure auth-protected endpoints continue to return appropriate status codes.

## Admin And Operations

The admin panel is part of the working baseline.

When changing admin-related behavior:

- Preserve staff workflows unless the task asks for a redesign or domain change.
- Make new catalog fields manageable from Django admin when appropriate.
- Keep list displays/search/filtering practical for product and order management.
- Avoid exposing sensitive fields or secrets in admin screens.

## Testing And Verification

Use tests proportional to risk.

For backend changes, consider running or adding tests around:

- Authentication and registration behavior
- Catalog list/detail endpoints
- Filters and sorting
- Cart and wishlist operations
- Checkout/order creation
- Admin-sensitive model behavior
- Security validation such as reCAPTCHA where applicable

If tests cannot be run because of local environment constraints, state that clearly in the final response.

## Session Memory

This file exists so the project context does not need to be re-explained in every Codex session. Treat it as the durable project brief for future work in this backend repository.

## Current Redesign State - 2026-05-01

- Homepage CMS data is being updated to support the FlexDrive redesign while preserving existing ecommerce APIs and admin workflows.
- `ProblemSolving` was renamed/replaced by `CategoryShortcuts`; the old problem-solving content was cleaned up. Category image upload/processing supports the frontend category card slider.
- `ValueProposition` was added as a homepage component between `CategoryShortcuts` and `OrderConfidence`.
  - Migration `pages/migrations/0041_seed_value_proposition_component.py` seeds the component, content `value_proposition_cards`, 3 content items, and homepage ordering.
  - Admin supports image uploads on each value proposition card.
- `OrderConfidence` backend content was refreshed:
  - `pages/migrations/0042_refresh_order_confidence_cards.py` updates card order/copy to process, registration, payment, delivery.
  - `pages/migrations/0043_shorten_order_confidence_registration_title.py` shortens the second title to `რეგისტრაციის გარეშე`.
  - Current expected card titles: `შეკვეთა მარტივად იწყება`, `რეგისტრაციის გარეშე`, `გადახდა შენზეა მორგებული`, `მიწოდება წინასწარ გასაგებია`.
- Staging DB was updated as of 2026-05-01:
  - `pages` migrations are applied through `0043`.
  - `OrderConfidence` title was manually set in staging DB to `შეკვეთა Flex[[Drive]]-ზე მარტივად და გარკვევით` to match local CMS content.
  - If staging UI shows old homepage text, suspect cached `get-current-content` response before changing migrations.
- Frontend no longer visually uses `OrderConfidence.content_items.icon_svg`; keep the field for compatibility unless a later cleanup is explicitly requested.

## Current Static/Legal Content State - 2026-05-15

- Static/legal/support content is being refreshed for FlexDrive while preserving existing CMS/page/component architecture. Frontend still loads backend components by route; do not replace this with hard-coded frontend copy.
- Backend migrations added for the current legal content pass:
  - `pages/migrations/0050_refresh_flexdrive_terms_content.py`
  - `pages/migrations/0051_refine_terms_account_security_copy.py`
  - `pages/migrations/0052_fix_terms_customer_contact_grammar.py`
  - `pages/migrations/0053_refine_terms_installed_part_return_copy.py`
  - `pages/migrations/0054_remove_terms_b2b_future_feature_bullet.py`
  - `pages/migrations/0055_remove_terms_warranty_reference.py`
  - `pages/migrations/0056_refresh_flexdrive_returns_content.py`
  - `pages/migrations/0057_refine_returns_unagreed_shipping_copy.py`
  - `pages/migrations/0058_refine_returns_customer_copy.py`
  - `pages/migrations/0059_refresh_flexdrive_payment_methods_content.py`
  - `pages/migrations/0060_trim_payment_methods_extra_copy.py`
  - `pages/migrations/0061_refresh_flexdrive_privacy_policy_content.py`
  - `pages/migrations/0062_refine_privacy_policy_copy.py`
  - `pages/migrations/0063_refresh_flexdrive_delivery_content.py`
  - `pages/migrations/0064_remove_contact_support_footer_settings_copy.py`
- These migrations were applied locally and on staging Neon/Postgres. If staging still displays old copy, suspect API/browser cache before changing migrations.
- Content direction by page:
  - `/terms`: practical FlexDrive rules for ecommerce use, order confirmation, payment, delivery, returns, B2B, privacy/security. Warranty references were removed because first-phase FlexDrive does not offer a warranty.
  - `/returns`: title is `პროდუქტისა და თანხის დაბრუნება`; ordinary return timing is based on product handover/receipt (`ჩაბარებიდან 14`), not purchase date; installed/used parts are assessed individually; wording avoids making returns feel automatic.
  - `/payment-methods`: reduced to 4 concise sections. Current active method is cash on delivery; card/installment/part-payment copy is future-ready but does not state those methods are already active. Refund/cancel is through the original payment channel for online methods.
  - `/privacy-policy`: reduced to 5 concise sections covering account/profile, cart/wishlist/buy-now, checkout/order, contact inquiries, reCAPTCHA, cookies, analytics/GTM/Google Ads/Meta Pixel, payment providers, delivery partners, retention/security, and user rights.
  - `/delivery`: reduced to 4 concise sections. Delivery timing starts after order confirmation; Tbilisi `1-2 სამუშაო დღე`, regions `4-5 სამუშაო დღე`; old same-day/13:00 logic was removed.
  - `/contact`: `support_intro` no longer has the redundant description about footer settings. The frontend renders this description only when CMS provides non-empty text.
- New legal content should set `ContentItem.icon_svg` to `None`. The redesigned frontend uses Heroicons and ignores backend SVGs for these legal pages.
- Placeholder company/contact data remains until registration and real support details are available. Current placeholders include `support@flexdrive.ge`, `returns@flexdrive.ge`, and `privacy@flexdrive.ge`.
- Tests updated/run during this pass:
  - `pages.test_payment_methods_page`
  - `pages.tests.GetCurrentContentAPITests.test_privacy_policy_page_includes_seeded_component`
  - `pages.tests.GetCurrentContentAPITests.test_delivery_page_includes_seeded_component`
- Next likely content/UI target: footer/contact browser QA if explicitly requested, then payment safety architecture work.

## Current Payment Safety State - 2026-05-15

- Stage 1 of payment safety is implemented as a low-risk foundation:
  - `commerce.Order` now has a separate `payment_status` field with values `pending`, `authorized`, `paid`, `failed`, `cancelled`, `refund_pending`, and `refunded`;
  - cash-on-delivery checkout and buy-now flows still create orders, reduce stock, clear cart/session, and return success through the existing flow;
  - public order summary and authenticated order list/detail serializers expose `payment_status`;
  - Django admin lists, filters, and edits `payment_status` independently from order status;
  - frontend order success, profile order detail, and profile order list display payment status, with `cash_on_delivery + pending` shown as `გადახდა ჩაბარებისას`;
  - guest users still only have the existing per-order success/status page by `public_token`; no guest cabinet was added.
- Local migration `commerce.0010_order_payment_status` was applied during this stage. Staging/prod still need this migration applied during deployment.
- The agreed generic availability copy is: `პროდუქტის ხელმისაწვდომობა შეიცვალა. გთხოვთ გადაამოწმოთ მარაგი და სცადოთ ხელახლა.`
- Payment safety work still not implemented: payment transaction records, reservation expiry, provider abstraction, online card/installment/part-payment callbacks, and refund/cancel provider flows.

## Upcoming Payment Safety Work - 2026-05-15

- Before real card, installment, or part-payment integrations go live, FlexDrive needs a carefully designed payment safety flow. This is high-priority work and must be implemented deliberately, with every step checked end to end.
- The goal is to avoid situations where a customer pays online or receives installment approval for a part that cannot be fulfilled because stock, compatibility, or order validation failed after payment.
- Required planning/implementation areas:
  - stock reservation during checkout, with expiry and release on failed/abandoned payment;
  - separate order status and payment status models/state handling;
  - payment transaction records with provider, provider transaction id, amount, currency, status, timestamps, and raw provider references where appropriate;
  - admin actions for cancelling orders, marking/refunding payments, and clearly tracking refund/cancel state;
  - provider abstraction so a manual/mock provider can exist before TBC/BOG/other real providers are connected;
  - success, failure, cancellation, callback/webhook, refund, and out-of-stock edge cases;
  - customer-facing copy for successful payment, pending confirmation, failed payment, cancelled order, refund initiated, and refund completed states.
- Prefer building the internal safety architecture before bank/provider integration. Bank APIs should plug into an already clear order/payment/refund model rather than defining the whole checkout logic.
- For card payments, prefer authorization/capture if the chosen provider supports it: reserve stock first, authorize payment, then capture only after the order is fulfilment-ready. If immediate capture is required, implement reliable full refund/cancel flows.
- For installments and part-payment providers, cancellation/refund must go through the same provider channel, not manual cash/bank transfer, unless a documented provider exception requires otherwise.
- Do not start this work casually while finishing legal/static pages. Treat it as a separate checkout/payment architecture phase after Terms/Returns/Delivery/Payment/Privacy content is stable and before production payment integrations.

## Current Supplier Import And Staging Media Workflow - 2026-07-02

- Cross Motors supplier refreshes on staging must use the fast bulk importer path, not the old row-by-row importer path.
  - Preferred staging command shape: `.\venv\Scripts\python.exe manage.py import_crossmotors_products --page-size 1000 --sample-size 0 --commit --bulk`
  - Set `DATABASE_URL` only in the command environment for the staging Neon database; do not edit `.env`.
  - Do a dry-run first without `--commit` when changing importer logic or when the supplier feed shape may have changed.
  - Use `--archive-missing` only when explicitly intended; the normal refresh used during this pass did not archive missing feed products.
- The importer now has canonical category mapping to prevent duplicate category creation:
  - Supplier lighting rows should map to `ფარები და განათება` / slug `ganateba`.
  - Supplier bumper/grille visual rows should map to `ვიზუალის ნაწილები` / slug `bamperebi-da-tskhaurebi`.
  - Engine/filter rows should map to `ძრავები და ფილტრები` / slug `dzravi-zetebi-da-filtrebi`.
  - Do not reintroduce fallback category names such as `განათება`, `ბამპერები და ცხაურები`, or `ძრავი, ზეთები და ფილტრები` as new catalog categories.
- If staging categories look wrong after an import, compare SKU-to-category assignments against local by SKU, not only category totals.
  - Ignore non-`CM-*` test products when comparing supplier catalog state.
  - For common `CM-*` SKUs, staging `Product.category.slug` should match local.
  - Local archived supplier leftovers should not be counted as active catalog parity issues.
- Product image sync from local to staging must not be done by copying local DB image paths directly.
  - Local image files are filesystem-backed under `media/`; staging image delivery is Cloudinary-backed.
  - Correct workflow:
    1. Build a local `ProductImage` snapshot keyed by product SKU, including `image_original`, `image_desktop`, `image_tablet`, `image_mobile`, `alt_text`, `is_primary`, and `sort_order`.
    2. Verify every snapshot SKU exists on staging before modifying staging image rows.
    3. Upload local image files to Cloudinary using parallel uploads. Sequential upload is too slow for the current volume.
    4. Only after all uploads succeed, replace staging `ProductImage` rows in one DB transaction: delete old rows, then `bulk_create` the snapshot rows with the uploaded Cloudinary asset paths.
    5. Verify final staging counts by SKU: expected image products, total image rows, no row-count mismatches, and no extra image products.
  - During the 2026-07-02 sync, the expected verified shape was 353 products with images, 1207 `ProductImage` rows, and 4828 Cloudinary files because each row stores original + desktop + tablet + mobile variants.
  - Cloudinary credentials must be supplied only as temporary command environment variables when needed. Never write them into repo files, `.env`, AGENTS.md, scripts, reports, or logs.
  - Temporary sync scripts/snapshots are acceptable for one-off operations, but remove them before finishing unless the user explicitly asks to keep a reusable tool.

## Cross Motors Delayed Stock Protection - 2026-07-27

- Cross Motors API stock is delayed and does not immediately reflect FlexDrive
  sales. Supplier-reported stock and FlexDrive effective stock must remain
  separate.
- `Product.supplier_stock_qty` stores the last raw Cross Motors quantity;
  `Product.stock_qty` stores effective stock after active supplier sale holds.
- Completed Cross Motors order items create a `SupplierStockHold`. The default
  hold window is controlled by `CROSSMOTORS_SALE_HOLD_SECONDS` and defaults to
  24 hours.
- Cross Motors imports must calculate effective stock as raw supplier stock
  minus active holds. Both normal and bulk importer paths must keep identical
  behavior.
- Expired holds are retired only as part of a successful supplier import.
  Supplier API failure must never increase stock from stale data.
- Cancelling/refunding a Cross Motors order releases its hold and recalculates
  from the latest supplier snapshot; never blindly increment supplier stock.
  Manual/local products retain the original stock restoration behavior.
- Django admin exposes supplier stock, active holds, customer-sellable stock,
  last sync time, hold history, and an audited confirmation-protected manual
  release action.

## Deferred Payment Monitoring - 2026-09-18

- The user explicitly deferred automatic payment reconciliation and alerts until
  the production launch phase; there are currently no real buyers. Do not
  implement or provision this work now unless requested.
- Revisit during production deployment planning: periodically check stale or
  unresolved BOG payments against the bank, using the existing verified,
  idempotent reconciliation flow. This must work even if the customer closes
  the browser; a paid cron service is not necessarily required. Choose a
  scheduler after checking hosting capabilities and cost.
- Add operator notifications and clear admin visibility for unresolved failures,
  especially confirmed paid transactions without an order. Rechecking a payment
  must not charge the customer again or blindly recreate a blocked order.
- Existing manual bank reconciliation is available in Django admin. Operators
  currently need to inspect payment transactions, not only the orders list;
  automatic monitoring/alerts are still outstanding.

## Supplier Publication And Scheduled Sync Preparation - 2026-09-22

- Both Cross Motors importer paths now create new products as Draft and preserve
  existing Draft/manual Archived status. Existing Published products still refresh
  supplier price/stock under the existing markup and sale-hold rules.
- `--archive-missing` archives only missing Published CM products and marks
  `Product.supplier_missing=True`. Only these automatically archived products
  republish on return; zero stock alone does not archive a product.
- Admin status changes and publish/draft/block actions clear the automatic-return
  marker. SupplierProductBlock continues to prevent reimport.
- `catalog.0020_product_supplier_missing` is applied locally; deployment must apply
  it before running the updated importer. Existing statuses were not changed.
- The management command locks before fetching (PostgreSQL transaction advisory
  lock; local SQLite file lock). Schedule the command rather than direct helper calls.
- Archive-enabled runs reject empty/no-importable feeds, duplicate SKUs, validation
  errors and a missing share above 20% of Published CM products. A reviewed one-off
  `--max-missing-percent` override exists; do not increase the scheduled threshold
  just to suppress a failed run. Pagination errors and changing snapshot timestamps
  also abort. Silent supplier truncation below the threshold remains a limitation.
- The planned App Platform job runs the bulk command with `--archive-missing`.
  User changed pre-launch cadence to every two days: daily UTC midnight trigger
  plus the documented calendar-parity wrapper runs the import every 48 hours.
  At launch switch to the direct command every two hours. It has NOT been
  provisioned/enabled. Instructions:
  `docs/SUPPLIER_SYNC_APP_PLATFORM.md`.
- Verification: 52 importer/publication/supplier-stock tests passed. Real supplier
  dry run returned 2030 valid rows, 0 errors and 7 missing Published local products.
  No committed supplier refresh or production change was performed.

## Supplier Sync Admin Reports - 2026-09-22

- `SupplierSyncReport` and migration `catalog.0021_supplier_sync_report` add private
  read-only admin history for committed Cross Motors command runs. Dry runs/skipped
  alternate-day launches do not create history. No email/Telegram is sent.
- Reports count new Draft products, customer-sellable stock exhaustion/return,
  archiving/restoration, and supplier price changes. Ordinary quantity changes are
  omitted; each group stores at most 50 names/SKUs plus its exact total count.
- The report and successful import commit together. Failures are saved after rollback
  with a safe phase summary. Database outages/process termination may prevent logging.
- Staff with the appropriate permissions can delete individual/selected/all filtered
  reports through Django admin's normal confirmation flow. Reports have no product
  foreign keys; deletion never deletes products or affects the next sync.

## Shared Cloudinary Product Image Transfer

- Staging and production will share the same Cloudinary cloud. Deploy the shared
  storage protection to BOTH environments before copying image references.
- `CLOUDINARY_SHARED_MEDIA` defaults to True: uploads use fresh UUID-based public
  IDs with overwrite=False; Cloudinary storage deletion becomes a no-op. Existing
  URLs remain valid. Local filesystem deletion behavior is unchanged.
- `audit_cloudinary_orphans --commit` is blocked in shared mode because it only
  checks one database. Future cleanup must account for every sharing environment.
  Unused Cloudinary files are retained for now; direct Cloudinary console changes
  are outside application protection.
- `export_product_images` / `import_product_images` transfer references and all
  ProductImage display/crop/AI settings by SKU. Source and target cloud must match.
  Import defaults to dry-run, only fills empty galleries, skips identical galleries
  on rerun, and refuses conflicting galleries. Missing SKUs require explicit
  `--skip-missing`; no products are created and no price/stock/status is modified.
- Use encoded exports for console transfer; never send credentials in snapshots.
  Instructions: `docs/SHARED_CLOUDINARY_IMAGES.md`. No schema migration required.
- Prepared/tested locally (25 image/storage tests); no remote deploy, image import,
  upload or Cloudinary configuration change has been performed by the agent.

## Individual Product Pricing - 2026-09-28

- User chose product-only markup: category markup no longer participates in admin,
  model or supplier-import pricing. Legacy category column retained unused for
  compatibility. No bulk price-setting action and no pricing-pending UI requested.
- Admin accepts customer amount or percentage with bidirectional live calculation
  and server-side verification. Supplier updates retain the individual percentage:
  supplier 100/customer 120 -> 20%; later supplier 110/customer 132.
- Empty markup means 0%, and new products default to 0%; Cross Motors still creates
  Draft products. User explicitly requested all current products start at 0%.
- Migrations 0025 (10-decimal individual percentage precision) and 0026 (zero default
  and one-time ALL-product reset) applied locally. 2,037 products now have 0%.
  All numeric prices already equalled supplier prices and stayed unchanged; every
  other product field and 26 other catalog/commerce tables verified unchanged by
  hashes. Orders/history unchanged. No remote changes or deployment performed.
- Before remote 0026, snapshot pricing; apply BEFORE setting final per-product
  prices because it resets existing markups once. No automatic data reversal.
  See docs/ADMIN_PRICING.md. Backend pricing/import/SKU checks: 55 passed, one
  PostgreSQL-only concurrency test skipped; 7 JavaScript checks passed.
- Accounting/reporting and historical cost snapshots remain a separate future task.
- Follow-up: admin markup input now displays two decimals while retaining ten-place
  storage/calculation precision. Ordinary saves and supplier-cost edits preserve
  the exact rate; explicit percentage edits replace it. 21 Django pricing tests
  and 8 JavaScript tests passed. No additional migration or price-data change.

## Staging Pricing Rollout Verified - 2026-09-28

- User supplied staging access after pushing the pricing changes. Read-only audit
  found catalog.0025 and 0026 already applied (19:01:11 / 19:01:13 UTC); no migrations
  were rerun and no database rows were changed by the agent.
- Verified PostgreSQL markup column numeric(14,10); all 2,038 products have individual
  0% and customer price equals supplier price. No invalid old_price conflicts.
- Saved a credential-free current pricing snapshot in the local temporary directory.
  This is a post-deployment snapshot, not a pre-migration backup. Admin browser/static
  deployment has not been verified in this database-only audit. Production pending.

## Production Pricing Rollout - 2026-09-28

- Applied catalog.0025_precise_product_markup and catalog.0026_individual_product_pricing
  to the user-supplied production PostgreSQL database in one verified transaction.
- All 2,030 products now have individual 0%; supplier/customer numeric prices already
  matched and remained unchanged. Percentage column verified numeric(14,10).
- Hashes verified every other product field and all 26 other catalog/commerce tables
  unchanged within the transaction. No order/history, stock, provider or scheduler
  actions. No unrelated migrations applied.
- Credential-free pre-change pricing snapshot saved locally at
  C:/Users/kench/AppData/Local/Temp/flexdrive-production-pricing-before-cutover-3da741f831b9430c93c9bf7c5b3f5895.json.
- Database preparation is complete on staging and production. This audit did not
  verify deployed admin/static assets in a browser or initiate a code deployment.

## Accounting Module Stage 1 - 2026-09-29

- User authorized incremental implementation, not the entire module in one task.
  Mandatory STOP for user review before accountant access/groups/account creation.
  Initial reporting routes/exports must be superuser-only; do not expose financial
  data to all staff while accountant permissions are deferred.
- Stage 1 completed: audited commerce models, card snapshot/finalization, direct
  checkout, delivery, refunds, serializers/admin and related tests. Implementation
  plan and acceptance criteria: docs/ACCOUNTING_IMPLEMENTATION_PLAN.md.
- No accounting code/schema/data changes, migrations, remote calls, fixtures or
  user accounts in this stage. Next bounded stage: private historical purchase-cost
  snapshots plus Decimal calculation foundation and targeted regression tests.
- User's workbook rule: gross purchase/1.18 = net cost; gross sale/1.18 = net sale;
  net markup = net sale - net cost. Supplier retail/comparison columns irrelevant.
  VAT registration is planned, effective date unknown. Calculated included purchase
  VAT is separate from invoice-confirmed deductible VAT; no automatic tax return.
- Cost snapshot must be frozen before bank redirection and carried through callback
  normalization/order creation. Preserve in-flight version-1 snapshots; missing
  historical cost stays unknown, never filled using today's supplier price.
- Delivery order fields already exist. Code defaults remain internal fee 0 and
  regional margin 2 (remote effective settings not checked); user intends 10/3.
  Internal carrier cost placeholder 0 is not evidence of zero actual delivery cost.
  Count delivery/buffer once per order, separately from product margins.
- Fake multi-month data and accountant login remain later separate stages. Do not
  create them or deploy accounting changes as part of the next foundation stage.

## Accounting Module Stage 2 - 2026-09-29

- Historical cost/calculation foundation implemented locally. Separate accounting
  screens, report queries, XLSX and accountant access are NOT implemented yet.
- Private OrderItem purchase gross/source/time snapshots are captured before bank
  redirection and copied by verified finalization; direct checkout captures locked
  product values. Old snapshots remain compatible; missing costs stay unknown.
  Model saves preserve snapshots and queryset cost updates are rejected. Existing
  order-item admin inline shows readonly facts; public/bank/receipt fields unchanged.
- Decimal helpers require explicit VAT rates, preserve unknown treatment, match the
  first ten workbook examples and expose rounding residuals: subtract unrounded
  net amounts before rounding markup; reconcile rounded net columns explicitly.
  No VAT registration or deductibility is assumed or activated.
- Local commerce.0033 applied; existing columns in all 27 catalogue/commerce tables
  verified unchanged by hashes; 32 legacy order items remain unknown-cost.
  109 targeted tests passed; two legacy delivery fixtures needed company SKU, then
  passed on rerun. Migration drift/whitespace checks passed. No remote changes.
- Latest user instruction defers 10/3 tariff changes. Reuse dynamic order delivery,
  carrier cost and margin fields. Do not change current pricing defaults/settings.
- Next bounded stage: report queries, date boundaries, delivery and refund/event
  handling, followed by superuser-only UI and export. Stop before accountant access
  for user review. See docs/ACCOUNTING_IMPLEMENTATION_PLAN.md.

## Accounting Module Stage 3 - 2026-09-29

- Added private read-only commerce/accounting_reports.py: inclusive Tbilisi date/
  month periods, order-created reports and separate confirmed cash-event reports.
  Money is grouped by currency; receipt/refund periods remain independent. Delivery
  and regional buffer count once per order. No tariff or checkout changes.
- Full refund allocations require valid sale linkage, matching full amount/currency/
  provider, chronology and unambiguous order transactions. Partial/ambiguous refunds
  and orphan receipts stay visible as unallocated cash with review codes. Missing
  timestamps remain global undated exceptions, not assigned using updated_at.
- Product margin coverage/missing cost and rounding residuals are explicit. Tax
  policy must be supplied using historical treatment; no default 18% activation.
  Internal carrier zero remains unknown actual delivery cost. Order-date totals
  include all statuses and must not be presented as received money or added to cash.
- 24 report tests + 13 foundation tests passed. Tests cover month boundaries,
  cross-month refunds, orphan cash, full/partial/duplicate refunds, currency isolation,
  missing costs, unknown tax, delivery, row limits and fixed query counts (2/4).
  No new migration, business-data write, remote call, provider action or deployment.
- Next stage is the superuser-only admin section; XLSX follows. Neither UI nor
  export exists yet. Do not create accountant access until user review at agreed stop.

## Accounting Module Stage 4 - 2026-09-29

- Separate superuser-only UI now exists at /manager-fd/accounting/, linked from
  admin home. Tabs: summary/orders/products/cash events/exceptions. Active staff AND
  superuser required server-side, with admin login/no-cache; read-only GET endpoint.
  Ordinary staff, even with commerce permissions, cannot access it. No accounts made.
- Date/month/search filters, whole-order search totals, pagination, Georgian labels,
  private detail links and global undated exceptions are implemented. Tax defaults
  unknown; optional clearly labeled 18% hypothetical model previews spreadsheet
  arithmetic without confirming registration/deductibility or changing stored data.
- 51 targeted tests passed. Browser verified month/scenario/search/empty-state/tab
  flows and desktop/mobile layout using an isolated in-memory test database; preview
  server/script removed. No local business-data writes, remote calls or deployment.
- UI needs existing commerce.0033 and new static assets at deployment. Tariffs remain
  unchanged. Next stage: XLSX export; then mandatory review stop BEFORE accountant
  permissions/account. Staging synthetic data remains a later separate stage.

## Accounting Export And Local Demo - 2026-09-29

- XLSX export now available from accounting UI with identical date/search/tax-mode
  filters; all rows, not just current page. Five sheets: summary/orders/products/
  payments-refunds/exceptions. Money is numeric, text explicitly inline (no formula
  injection), headers styled/frozen/filterable. Uses standard-library OOXML writer
  commerce/accounting_export.py; no runtime dependency added. Same superuser gate.
- Three focused export/access/demo create-cleanup tests passed. Prior 51 UI/report/
  foundation tests passed in preceding stage. No remote deployment or new migration.
- User authorized fake data now. Created LOCAL SQLite batch FD-DEMO-202609-:
  7 orders, 9 item rows, 8 mock transactions across July–September 2026. Includes
  pending payment, unknown cost, multiple lines, internal/regional delivery and July
  sale refunded in August. No real product links, stock changes, emails or provider
  calls; no accountant/user created. Demo 10/3 amounts do not change live tariffs.
- Command: accounting_demo (SQLite-only, refuses duplicate batch). Cleanup:
  DATABASE_URL=sqlite:///db.sqlite3 then venv python manage.py accounting_demo --delete.
  Checks demo markers and no real product/payment links before atomic hard-delete;
  tested to preserve unrelated orders. Do not run against remote databases.
- Verified demo totals July–September: orders 424 GEL, received 379, refunded 93,
  net cash 286. Search FD-DEMO-202609- isolates the examples. Fake data remains in
  local db for user review; does not deploy with code. STOP before accountant access.
