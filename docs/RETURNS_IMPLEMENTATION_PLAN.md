# Returns and FlexDrive-owned inventory

## Delivery boundary

Implement in reviewable stages. Stages 1/2 added the foundation; stage 3 connected
owned inventory to selling and applied migrations locally. Stages 4/5 now expose
order-level pre-dispatch refunds and dispatched return/receipt/refund actions.
Operational lists are now implemented; integrated browser review is next. Real provider calls and
production rollout have not been performed during implementation.

The user confirmed on 2026-10-07 that all existing orders are test orders, and
the deployed site is not publicly launched or on its own domain. Do not build
elaborate historical-order compatibility solely for these test records. Do not
delete/reset them without a concrete task need. Production is outside this stage.

## Agreed operator flow (Georgian UI)

All actions start from the order, never the catalog product editor.

1. Before dispatch: `თანხის დაბრუნება`, one choice for the whole order:
   - `მომწოდებლისგან ჯერ არ შემიძენია`: release the supplier hold only when
     the existing verified full-refund finalizer confirms the bank refund.
   - `უკვე შეძენილია და ჩემთანაა`: explicitly confirm no dispatch and saleable
     condition. Record physical receipt directly in owned inventory, once.
   Do not route through the waiting list. The same confirmation requests the full bank refund.
     A bank timeout/rejection cannot erase physical receipt or repeat it on retry.
2. After dispatch/delivery: `დაბრუნების დაწყება` records an expected return.
   No bank refund, supplier hold release, or saleable inventory addition yet.
3. `დასაბრუნებელი ნივთები` -> receipt -> `მიღებისა და შემოწმების დადასტურება`.
   Full physical receipt is required in this initial full-order flow. Record
   saleable and unsaleable quantities per line; only saleable units enter stock.
   The procurement choice remains order-level, not a per-product question.
4. After inspection: `თანხის დაბრუნება` becomes available on the linked order.
   Show pending, confirmed, rejected/unknown bank results independently of receipt.
   Unsaleable receipt does not itself decide refund eligibility or trigger payment.

The waiting list and owned-stock list are two views of linked records, not
independently editable copies. Received cases remain in history. Cancelling an
awaiting return creates no money/stock changes; restarting must explicitly reuse
the case with an audit trail (UI/service for cancellation is a later stage).

## Non-negotiable rules

- Money, physical receipt, and outbound delivery have distinct states.
- Repeated submissions/callbacks must not duplicate receipts, stock, or refunds.
- Record actor, timestamp, order, line, quantity, condition and historical cost.
- Old unknown purchase costs stay NULL, not zero or today's supplier price.
- Existing test orders are not evidence of procurement and need no invented backfill.
- Existing paid orders without an order object retain their separate incident path.
- Check prerequisites on the server, including the payment admin's refund route.
- Protect received inventory/history from deletion or stale form overwrites.
- A customer can buy one owned unit; supplier safety reserve does not hide it.
- Consume owned inventory first; record lot allocations internally. Mixed sources
  do not require the operator to answer procurement questions per line.
- Returning an owned unit creates a new receipt with its original cost provenance;
  it must not release/increase unrelated supplier inventory.
- A bought supplier item must not become available at both sources because an old
  supplier feed still includes it. Preserve the existing conservative hold until
  expiry/reconciliation when procurement is confirmed; do not treat this as an
  unpurchased cancellation. Sync/receipt ordering needs explicit tests.
- Supplier sync never overwrites owned stock. Missing-feed archiving must respect
  owned stock while preserving intentional admin publication/archival choices.
- Freeze fulfilment actions once a return starts; carrier updates must not reopen
  a returned/cancelled order. Creating an EasyWay job is not proof of dispatch.
- Partial refunds, exchanges and supplier returns are outside the initial scope.

## Stages and acceptance gates

1. **Rules/data design**: this document; preserve full-order procurement choice.
2. **Inactive foundation**: return case/lines, immutable inventory receipt lots,
   full receipt validation, idempotent internal services, actor/time/cost history.
   Additive migration only; no edits to old tables or data. Not exposed in admin.
3. **Inventory selling**: stock allocation/provenance, source-aware reservation
   and sale finalization in all three paths (cart, buy-now, verified BOG callback),
   historical lot cost on resale, supplier holds/sync, search filters/ranking,
   serializers/cache and missing-feed behavior. Test concurrent purchase of last
   owned unit and mixed-source orders. No UI activation until these pass.
4. **Before-dispatch refund**: attach procurement choice to existing bank request
   and replace indiscriminate restoration with source-aware finalization. Block
   invalid transitions and alternate admin bypasses. Existing orders are test
   orders; prefer clear new rules over elaborate legacy compatibility branches.
5. **After-dispatch return**: waiting/inspection/refund services and actions,
   cancellation/restart audit, receipt prerequisite, delivery/tracking safeguards.
6. **Georgian admin and integrated QA**: two lists, order actions, all new labels,
   messages and confirmations in Georgian, staff permissions (accountants remain
   report-only), browser review of the three scenarios and failures/retries.
7. **Rollout preparation**: PostgreSQL concurrency, pending legacy operations,
   migration/rollback rehearsal, staging/browser verification and deployment order.
   Production work remains a separate, explicit deployment step.

For each stage: implement -> focused tests -> report the result and remaining
work -> review before the next stage. Never activate a partially connected flow.

## Foundation schema

- `OrderReturn`: one full-return case per original order; procurement disposition,
  receipt state, requesting/receiving actors and timestamps. Bank state remains
  exclusively in the existing payment records.
- `OrderReturnLine`: immutable order-item link and expected full quantity; inspection
  records saleable/unsaleable counts. It is not an editable catalog stock number.
- `OwnedStockLot`: immutable receipt batch linked to its return line and product,
  with quantity and nullable historical unit cost. Multiple batches per line are
  allowed for mixed-cost/source allocation. Unique line/batch keys protect retries.

Receipt services remain internal and are not exposed by operational views/admin.
The inventory layer now participates in checkout and supplier synchronization.

## Completed foundation checkpoint — 2026-10-07

- Added commerce migration `0035_return_inventory_foundation`: three new models
  and constraints only; no existing columns/data changes or backfill.
- Internal `prepare_order_return` / `receive_order_return` support order-wide
  disposition, full physical inspection, saleable-only receipts, historical costs,
  atomic rollback and identical-request retries. No bank or carrier calls.
- 16 new foundation tests plus 24 existing refund/supplier-hold tests pass on a
  disposable SQLite test database. Migration drift and whitespace checks pass.
- Migration has NOT been applied to local business, staging or production DBs.
  PostgreSQL concurrency and browser checks are outstanding for later stages.
- No operational admin registration/URLs, API payload or availability changes.
  Labels/errors for new records are Georgian; interactive admin remains stage 6.
- Next checkpoint is stage 3, source-aware inventory selling. Until its completion,
  receipt lots are historical records only and must not be created operationally.

## Inventory selling checkpoint — 2026-10-07

- Added `Product.owned_stock_qty`, a materialized ledger balance independent of
  external `stock_qty`. Availability is owned + max(external - reserve, 0).
  Public API names/shapes are unchanged. Catalog/admin stock filters and ordering
  use both sources; no per-card inventory queries are introduced.
- `commerce/inventory.py` allocates FIFO owned lots, then external stock, in the
  direct cart, direct buy-now and verified BOG finalization paths. Product locks
  serialize writers; quantities, allocations and order creation commit together.
- Checkout reservations continue to reserve the combined available quantity. A
  reservation does NOT promise a specific stock source/cost layer. Source and
  actual historical cost are fixed at final allocation. Customer prices and the
  original bank checkout snapshot stay unchanged. Confirmed BOG finalization
  retains its existing external safety-margin allowance after supplier changes.
- `OrderItemInventory` stores external quantity/source and exact total purchase
  cost; `OwnedStockAllocation` links consumed lots. Supplier holds cover external
  units only. Ordinary pre-dispatch cancellation restores the same source once.
- Reports/XLSX use actual total allocated cost, including mixed batches, without
  prematurely rounding an average unit cost. Unknown cost remains unknown. The
  original pre-payment supplier-cost snapshot remains intact for external units.
- Returned resale units retain their original lots/costs. For fungible units of
  one product, inspected saleable units take the original FIFO cost layers first;
  remaining layers are attributed to unsaleable units. This is a valuation rule,
  not a claim that the operator identified individual serialized units.
- Regular/bulk supplier imports preserve owned balances. Missing-feed handling
  zeros external quantities and keeps owned stock published. A receipt or cancelled
  own-stock sale can reopen only supplier-auto-archived products; manually hidden
  products stay hidden. Stock mutations invalidate existing catalog cache groups.
- Receipt-driven cases are blocked from the OLD refund/restoration entry points
  until stage 4 supplies the dedicated finalizer; this prevents double restocking.
- Added migration catalog.0027 and commerce.0036. Rehearsal verifies prior product
  values unchanged and initializes only the new balance from foundation receipts.
- Applied catalog.0027 + commerce.0035/0036 to LOCAL SQLite only after backup:
  `local-docs/returns-stage3-backup-7r5l_yzn/db.sqlite3` (git-ignored).
  Original columns in all 33 pre-existing catalog/commerce/accounts tables have
  identical pre/post row hashes. Target plan empty; owned balance starts at zero.
  No staging/production migration, real supplier/bank call, push or deployment.
- Verification: foundation/refund/hold/accounting tests (77) passed; final inventory,
  signed callback and hold suite: 80 run, 79 pass + 1 PostgreSQL-only concurrency
  test skipped on SQLite. Search/accounting UI/export/migration suite: 87 passed.
  Drift/whitespace checks pass. PostgreSQL row-lock execution and browser QA remain.
- Broader tests uncovered existing SKU-less card-payment fixtures (29 setup errors)
  and one stale category-markup expectation (250 vs 275). Representative failures
  reproduced on unmodified HEAD in an isolated temporary checkout; not repaired
  or hidden in this stage. Other tests in that broader run passed.
- Next: stage 4, Georgian pre-dispatch procurement choice + dedicated bank refund
  finalizer. Then dispatched receipt/refund actions and two operational admin lists.

## Pre-dispatch checkpoint — 2026-10-07

- Implemented the Georgian order confirmation page and whole-order choice, explicit
  non-dispatch acknowledgement, product quantities/amount and explained outcomes.
  Only this flow is localized; the overall admin language is unchanged.
- Admin requests record receipt/case atomically before the BOG request. On-hand
  receipt immediately credits own inventory. Its finalizer only cancels the order;
  supplier holds remain conservative until normal reconciliation/expiry. Unpurchased
  finalization restores recorded sources/releases holds only after confirmed refund.
- Case identity is bound to the payment request. Retries lock the original choice,
  reuse pending requests and do not credit inventory twice. Order status banners
  separate physical receipt from pending/confirmed/failed monetary outcomes.
- Linked payment admin routes redirect to the order confirmation. New shipment,
  manual fulfilment advancement and tracking advancement stop when a case exists.
  Dispatched cases cannot use this pre-dispatch flow.
- Seven focused tests cover both supplier cases, duplicate request/completion,
  timeout retry key, Georgian form validation, real admin submission with mocked
  bank, changed-choice rejection and dispatched/alternate-route blocking.
- All 19 focused tests passed (7 new + 12 existing refund tests).
- No schema/migration, actual bank/carrier request, deployment or business-data edit.
- Remaining two stages: dispatched return/inspection/refund, then the two operational
  admin lists and a practical integrated review. Keep further checks focused.

## Dispatched-return checkpoint — 2026-10-07

- Paid dispatched orders show return start; awaiting cases show receipt/inspection;
  received cases enable the separate full-refund confirmation. All new text is
  Georgian. Each endpoint enforces order-change permission, and service checks
  prevent direct refund requests from bypassing physical receipt.
- Receipt requires all expected units, recording saleable/unsaleable counts.
  Saleable units credit stock once. Full bank refund remains an explicit decision
  even when some received units are unsaleable. Bank completion never credits
  received stock again or releases purchased supplier holds.
- Four focused new tests plus 19 existing refund tests pass on disposable SQLite.
  Tested admin actions, denied permissions, receipt/refund sequencing, unreceived
  refund bypass attempts, invalid receipt totals, unsaleable goods and replay.
- No schema, business-data, real provider or remote changes. Browser review is
  still pending. Next: operational lists and integrated QA. Cancellation/restart
  audit remains unimplemented and must not be advertised as available.

## Operational lists checkpoint — 2026-10-07

- Added the two Georgian sections using existing return/receipt models, without
  migrations or edits to business data. Awaiting returns appear by default;
  received/all-history filters preserve prior records and show bank state separately.
- Return details show each product and inspected quantities, with a link to the
  existing receipt action. Order details link back to their return case.
- Owned inventory shows receipt batches, received/remaining units and source order.
  Remaining units exclude consumed allocations and include restored allocations.
  Default list shows positive balances; empty and complete history remain searchable.
- Both sections are read-only, with permission checks; accountants remain report-only.
- SQLite verification: 20 existing foundation/customer-return tests passed and
  all 3 new operational-list tests passed (history, balances, filters, permissions).
- Browser review is explicitly deferred by the user, who will start the backend
  and open Chrome before that review. Do not start servers/browser in this stage.
  Cancellation/restart and production rollout remain outside completed work.
