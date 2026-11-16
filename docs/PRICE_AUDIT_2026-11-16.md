# Published price audit — 2026-11-16

Production PostgreSQL snapshot: 2026-11-16 00:13 Asia/Tbilisi. Connected to the
user-supplied production host, TLS1.3, defaultdb, explicit REPEATABLE READ / READ
ONLY transaction; transaction_read_only=on verified. No production writes,
migrations, supplier calls, or price changes. Computer Use was stopped on the
user's instruction; all findings below come from the direct database snapshot.

## Findings

- 1,979 Published products, 1,300 with customer-available stock under the current
  owned stock + max(supplier-backed effective stock minus5,0) rule.
- No sale below supplier cost; no missing/zero/negative supplier or sale price;
  no invalid old_price; no missing FlexDrive SKU or inactive category.
- All 1,979 sale prices exactly match the current stored percentage calculation
  to the cent. This verifies arithmetic, not the commercial correctness of the
  originally chosen percentage or supplier feed.
- 95 products have equal cost and sale price. 94 have both supplier stock and owned
  stock zero. One is currently sellable: product375 / CM-000404 / FD-08-0007,
  წინა გიტარა (LH), AJSparts, cost140 GEL, sale140 GEL, supplier stock23 and
  customer-available18. User must decide its price or publication status.
- Two positive markups below10%: FD-04-0198 front right door1550→1700 GEL (9.68%)
  and FD-08-0039 front CV assembly240→250 GEL (4.17%). Neither has available stock.
  10% is an audit screening threshold, not an agreed business minimum.
- 23 markups at or above200% (21 with available stock), maximum525% on two
  4→25 GEL brackets. High percentages on low-cost parts are review signals, not
  evidence of an error; the previous approved price import included up to525%.
- Lowest available positive gross difference is FD-08-0121, wheel bolt2→3 GEL.
  This1 GEL difference is before payment/fulfilment/other operating costs.
- Price range is3–2200 GEL. No market-price validation or external supplier
  invoice/feed validation was performed. Human entry mistakes cannot all be
  ruled out from internally consistent numbers alone.

Full per-product evidence and review tables are git-ignored under
`tmp/measurements-20261015/price-audit-20261116/`: published-prices.json,
summary.json, review.md. They contain product facts only, no credentials/customer
records. A console Unicode encoding error happened after the evidence files were
saved; the saved files were then parsed locally to complete the audit.

## Price-review rollout limitation

Later on2026-11-16 the user deployed and authorized applying0032. It is now applied,
verified through a fresh read-only connection, with all original product data
preserved. The audit-time status below is historical; the no-backfill limitation
and existing95 equal prices still apply.

Production's latest catalog migration remains0031;0032 is not applied. The prepared
0032 defaults existing review flags to false and does not backfill equal-price
products. Therefore deploying it alone will NOT block the existing95 equal-price
products: the prepared guard operates after a supplier cost change is detected.
The live140/140 product and the94 unavailable equal-price products require an
explicit price/publication/review decision before launch or restocking. No such
decision or data change was made in this audit.

## Financial verification before opening

1. Resolve equal-price products; agree how unpriced stock returning to availability
   is prevented from selling at zero product margin. After deployment verify the
   price-review workflow, list/card/search visibility and purchase blocking.
2. Run a small genuine BOG purchase: compare cart, checkout, bank amount/currency,
   final order, receipt and business report. Test quantity>1 and fractional prices.
3. Confirm repeated return/callback/reconciliation creates one order, one stock
   deduction and one sale event; browser closure after payment must not lose it.
4. Confirm cancellation/failed payment creates no paid sale and releases temporary
   stock. Confirm one full/partial refund and stock restoration follow the actual
   returned quantity and confirmed bank outcome, without duplicates.
5. Check delivery totals for Tbilisi/region, service and quantity/weight changes:
   customer fee, provider quote, buffer and actual booked cost; count delivery once
   per order. Internal delivery's stored zero carrier cost is not proof that actual
   fulfilment has no expense.
6. Compare bank settlement and contractual fees with gross paid amounts. Establish
   whether bank fees, packaging, own delivery, ads and hosting are actually recorded
   before describing any dashboard amount as final company profit.
7. Verify paid-order unit cost/sale snapshots stay unchanged when current product
   prices later change; refunds appear once and in the right reporting period.
8. Verify reconciliation with a genuine candidate and real operator notification;
   previous empty successful batches do not establish recovery or email delivery.
   Missed-run detection is separate from failed-job alerts.

These are remaining verification tasks, not results of this price-only audit.
Real charges/refunds/shipments remain separate explicitly authorized actions.
