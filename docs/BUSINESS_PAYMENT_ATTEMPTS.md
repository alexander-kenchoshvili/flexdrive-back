# Business payment attempt explanations

Prepared 2026-11-20; both repositories need deployment. No new migration or ENV.

The private Operations payments table now includes a saved bank failure reason,
checkout product/delivery totals and service, expandable chronological attempts,
and a later confirmed payment/order when one can be linked conservatively.
The original failed records remain failed; summary counts still count payment
actions, not unique people, abandoned carts or lost sales.

The actual Nov20 case has three failed 79 GEL BOG attempts with saved callback
status `rejected`, code `108`, reason `Authentication Declined`. Each snapshot
has the same 60 GEL item and fast delivery19. Later sale7 is confirmed for69 GEL
with standard delivery9 and the existing order2. All four share the checkout
owner, source cart and identical item/quantity/unit-price snapshot. This does
not establish that changing delivery resolved authentication or that fast
delivery caused the earlier rejection. Exact OTP/app/issuer subreason is not
established by the saved generic bank reason.

Time verification: failed starts are09:15:51/09:18:05/10:09:30 Tbilisi, and status
updates09:17:02/09:19:20/10:10:42. Successful payment initiation is10:15:43 and
bank confirmation/order creation10:19:43. Stored bank-signed callback timestamps
corroborate those times. Django admin uses UTC, four hours behind Tbilisi;
06:15/06:19 in admin are10:15/10:19 locally. Payment Created at is initiation,
whereas capture/order creation records completion. No timezone setting changed.

BOG's official [response codes](https://api.bog.ge/docs/payments/response-codes)
classify108 as Authentication Declined and109 as Technical Issue. The saved
code description repeats the generic reason and has no additional3DS/ACS reason
field. A support inquiry with bank order IDs and both timezone representations
was prepared in the ignored QA folder as bank-support-request.txt, not sent.

A delivery selector change alone does not set payment status failed. Payment
records are created by the bank-start path; a verified rejected bank callback
marks these sales failed and releases their reservations. A later success uses
a separate attempt. No payment/refund/stock/courier behavior was changed here.

The API adds optional `attempt_context` to payment rows. Existing clients ignore
it; the new frontend falls back to the old warning on an older backend. Known
bank reasons are translated through a fixed allowlist; unknown provider text,
raw errors, cards, credentials and responses are never returned. Legacy missing
snapshots remain unknown. `expiration` is described as bank checkout expiration,
not evidence that the customer's card expired.

Linking requires the existing SHA256 owner fingerprint AND the exact source
cart/Buy Now session ID, same currency, products, quantities and unit prices,
within24 hours of the selected attempt. Names/phone/email/personal number are
not used or returned; source IDs and owner digests stay server-side. No new
clickstream, cookies, analytics or persisted correlation records are created.
The displayed history covers saved payments, not every click or independently
verified person identity. A later success requires a linked order, paid sale
status and captured timestamp; current refund settlement remains visible.

The report page runs one bounded context SELECT (maximum400 candidate rows),
then returns at most12 related entries per payment. The selected row stays in
history, along with a known later success. Limits are explicit; missing matches
must not be interpreted as proof that no later purchase exists. Existing page
filters, permissions, no-store headers and summary rules remain.

Validation:39 focused backend tests passed, covering conservative matching,
unknown/private/malformed values, bounds, read-only query counts, permission
checks, actual bank callback rejection/reservation release, late rejection after
success, fast-service successful confirmation and Wingo service guards. Ten
frontend composable/actual-SFC-render tests passed, plus scoped ESLint and strict
app vue-tsc. Migration drift and whitespace checks passed. Existing CKEditor and
local staticfiles warnings remain. No full build or browser automation was run.

The new report code was also executed against production with database-enforced
read-only access and a SELECT-only wrapper: four SELECTs correctly linked
attempts4/5/6 to successful7, and kept old Oct19 expiration attempt1 separate.
Only redacted IDs/reason categories were saved in ignored
`tmp/measurements-20261015/personal-number-20261120/`. No production writes,
bank API requests, provider events, reconciliation, commit, push or deployment.
