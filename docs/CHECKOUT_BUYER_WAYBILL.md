# Checkout buyer details for transport waybills

Prepared 2026-11-20; not deployed or migrated on local/production databases.

Both cart and Buy Now checkout require an individual's 11-digit ASCII personal
number. It is text throughout, preserving leading zeroes. The Georgian input hint
explains that it is needed to prepare a transport waybill. This checks format,
not identity or ownership. Legal buyers keep their existing company name,
9-digit identification code and VAT declaration; the contact person's personal
number is not required. No passport/foreign-document flow was added.

The number is stored on `Order.personal_number`. Card checkout also saves it in
the existing private checkout snapshot before the bank redirect; successful
confirmation copies that original value to the order. A changed number changes
the request fingerprint and the frontend's idempotency key. Historical requests
with no number keep their original fingerprint; existing in-flight bank
snapshots without the field can still complete. Existing orders remain blank.
An authorized order administrator can enter a genuinely obtained missing number
in the new Customer field; nothing backfills or guesses it.

The number is absent from checkout responses, public/lookup/owner summaries,
normal receipts, profile backfill, browser drafts, analytics, bank create-order
requests and Wingo payloads. Buyer-type switching clears the frontend value.
Existing account-deletion cleanup now clears the new order field as well; this
does not redesign retention of existing private payment/receipt records.

The private accountant report shows saved order buyer names (contact names for
a company), delivery address, phone, and type-appropriate identification fields.
It reads order data, not the account's current profile. Old missing values show
as unavailable. Existing accountant permissions and no-cache handling apply to
HTML and XLSX; no new access is granted.

The XLSX adds a `მყიდველები` sheet with one row per included order, even when the
financial report includes multiple products or both sale and refund events.
Order number joins it to the unchanged financial sheet. Company and personal IDs
are inline text with Excel's explicit text format; values cannot become formulas.
The sheet filters every buyer row, has no invented totals, and freezes the order
column. Missing/inapplicable identifiers are blank. Amount columns, VAT, delivery,
refund signs and totals remain in the established financial report.

Deployment requires both repositories and these new migrations:

- `commerce.0046_order_personal_number`: one blank-compatible order column.
- `pages.0087_personal_number_waybill_notice`: appends a purpose notice to the
  existing privacy policy, preserving other sections and existing admin edits.

Run migrations before activating new backend code, then deploy the frontend
promptly: an old checkout tab without the new field cannot submit a new
individual order to the updated API and must refresh. Existing created orders,
bank confirmations and Wingo labels do not need a new personal number. The repo's
Render build configuration uses `build.sh`, which already runs
`python manage.py migrate --noinput`; verify those two migrations in deployment
logs rather than assuming the configured production build is unchanged.

No RS/waybill integration, provider mutation, payment/refund/stock change, real
customer data entry, commit, push or deployment was performed.

Validation: 160 targeted bank callback, guest checkout, Wingo, accounting and
account-deletion tests passed; the final export/notice/Wingo-accounting/navigation
run passed 50 tests (overlapping earlier coverage), plus the targeted provider
redaction test. Frontend passed 23 real schema/composable/render/page-payload
tests, scoped ESLint and strict app vue-tsc. Migration drift and whitespace checks
passed. Existing CKEditor/staticfiles warnings remain. No full build or browser
automation was run.

Synthetic export QA also confirmed identifiers, text cell types, filters and
freeze panes using an independent XLSX reader. Artifact rendering confirmed the
new sheet layout, but its numeric-string preview/import has a known limitation
in this run: it visually shortened zero-prefixed strings despite correct source
XML and exact imported values. Native Excel UI was not used. QA scripts/artifacts
are kept in ignored `tmp/measurements-20261015/personal-number-20261120/`.
