# FlexDrive SKU contract

`Product.sku` is the private supplier/legacy identifier. Keep it for supplier imports,
sync, comparison, stock operations and image transfer. `Product.internal_sku` is the
permanent company code. Admin shows and searches both, with company SKU read-only.

Public catalog, suggestions, cart and buy-now `sku`/`display_sku` return the company
code or an empty string, never a supplier-code fallback. Public search uses company
SKU, names and manufacturer numbers. Browser analytics receive the public SKU; Meta
purchase content IDs use the frozen order `internal_sku`. New BOG basket IDs also use
company codes; private payment snapshots keep both identifiers.

## Allocation

| Group | Root category slug |
| --- | --- |
| 01 | ganateba |
| 02 | sarkeebi |
| 03 | dzaris-natsilebi |
| 04 | bamperebi-da-tskhaurebi |
| 05 | dzravi-zetebi-da-filtrebi |
| 06 | eleqtrooba |
| 07 | radiatorebi-da-gagrileba |
| 08 | savali-natsilebi |

These match the supplied workbook. Subcategories use their root's group. The supplier
inbox category `ახალი` has no group. Imports create Draft products without company
codes. Saving a valid product form in admin with a mapped category assigns a code if
missing. Merely opening/editing a form or running a supplier import does not allocate.
Saving as Published in that same operation is supported.

`SkuSequence` stores a persistent high-water mark per group. Allocation atomically
locks the product and updates its group sequence before writing `FD-XX-NNNN`. It
also checks the maximum existing code. Minimum four-digit numbers can grow past 9999.
Committed numbers are not reused after deletion. Rolled-back saves leave neither a
code nor a consumed number. Counters are not editable/deletable through admin.

Category changes and stale model saves preserve assigned codes. Both supplier import
paths preserve them. The XLSX importer advances counters and refuses replacement.
Use admin or the dedicated importer to assign codes, not arbitrary SQL/bulk updates.

Publication is protected by form validation, bulk action and database enforcement.
A mixed selection containing an unassigned product publishes nothing. PostgreSQL
uses a check constraint. SQLite uses INSERT/UPDATE guards, avoiding a product-table
rebuild with historical PostgreSQL trigram indexes. Supplier restoration without a
company code returns the product to Draft instead of publishing it.

## URLs and existing orders

Stored slugs remain unchanged internally. Public slugs remove the supplier code and
append company SKU. Catalog, cart, buy-now, wishlist, canonical metadata and sitemap
use the public slug. Product detail accepts old stored and new public slugs; old links
continue to work and respond with the new canonical URL.

Existing test orders, receipts and old payment snapshots are not rewritten. Their
historical display remains unchanged. New COD/card orders freeze the company code;
new order displays and receipts use it. Pre-change payment snapshots remain supported.

## Deployment

Install the schema before starting updated workers/admin. For an environment without
the mapping, stop at catalog 0023, import the reviewed file, then install 0024:

```powershell
.\venv\Scripts\python.exe manage.py migrate catalog 0023
.\venv\Scripts\python.exe manage.py migrate commerce 0032
.\venv\Scripts\python.exe manage.py import_internal_skus --input "C:\path\FlexDrive_Prices_Paired_Updated.xlsx"
.\venv\Scripts\python.exe manage.py import_internal_skus --input "C:\path\FlexDrive_Prices_Paired_Updated.xlsx" --commit
.\venv\Scripts\python.exe manage.py migrate catalog 0024
```

0024 refuses installation if any Published product lacks company SKU. Assign reviewed
codes first. Check category mappings if target slugs differ. Deploy backend before
frontend and refresh cached browser data. Deferred scheduled jobs remain disabled.

The importer reads only `SKU / კოდი` and `ჩვენი კოდი` on every worksheet. It never
imports prices or stock. Default is dry-run; duplicates, missing products, formulas,
invalid identifiers and conflicting assignments abort the batch. Commit changes only
company codes/counters. Repeating the same mapping is a no-op.

## Staging preparation, 2026-09-23

Staging catalog 0022–0024 and commerce 0032 are applied. All 2,037 workbook pairs
were verified and imported in one transaction. The additional existing published
`test1234` product received `FD-01-0216` from its lighting category. All 2,038
products now have company codes; group 01 high-water mark is 216. Hash comparison
verified existing product/category/order/order-item values unchanged, excluding
the new fields. No existing order was backfilled.

Staging `commerce_orderitem.internal_sku` has an additional SQL default of empty
string so the still-deployed old checkout can insert order items until deployment.
No credentials were stored in files. Automatic staging deployment can remain
enabled; deploy backend then frontend. Code has not been pushed or deployed by
the agent. Production preparation is recorded below.

## Production preparation, 2026-09-23

Applied catalog 0022–0024 and commerce 0031–0032 in one PostgreSQL transaction.
All 2,030 existing production products received their exact workbook codes, with
no Published product left without a code. Seven workbook products do not exist in
production and were not created: CM-000537, CM-000860, CM-000974, CM-000975,
CM-001065, CM-001155, CM-001156. Sequence high-water marks use the full workbook
maxima so their numbers cannot be automatically reused. If these products return,
assign their reviewed original workbook mapping explicitly before publication.

Existing product/category/order/order-item values were verified unchanged using
hashes before commit, excluding newly added fields. SQL DEFAULT '' was set on
commerce_orderitem.internal_sku and commerce_paymenttransaction.reconciliation_issue
to preserve inserts from the older deployed code. No supplier/bank/email calls,
scheduler activation, or code deployment occurred. Credentials were passed only
in the temporary process environment. Deploy backend then frontend and verify
the public catalog, search, URLs, and checkout afterward.

## Local verification, 2026-09-23

- Catalog 0022–0024 and commerce 0032 applied locally. All 2,037 mappings preserved;
  repeat dry-run reports 0 updates. Eight counters seeded from actual maximum codes.
  All 2,037 public slugs are distinct.
- Hashes confirmed all pre-existing values across 26 catalog/commerce tables unchanged,
  including product slugs, prices, stock, both SKU values and test orders. Only category
  group assignments and sequence records were added in this pass.
- 153 focused tests passed; 11 allocation/URL tests subsequently passed with added
  sitemap/group coverage. One PostgreSQL concurrency test was skipped on SQLite.
  Frontend typecheck passed. No browser/server was launched.
- The whole legacy suite is not reported as passing: previously identified stock,
  delivery and catalog expectation failures remain. Older Published-product fixtures
  also need company codes under the new required publication invariant.
- No remote code deployment or real supplier/bank/email calls performed. PostgreSQL runtime
  concurrency verification remains required before production rollout.

Keep a database backup and the mapping file for deployment. Preserve additive SKU
fields on application rollback where possible; do not reset counters or reuse codes.
