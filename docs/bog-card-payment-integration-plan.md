# BOG Card Payment Integration Plan

Status: phase 7 local automated verification complete; phase 8 requires explicit user approval  
Last updated: 2026-06-23

## Purpose

This document is the implementation checklist for adding Bank of Georgia online
card payments to FlexDrive. It is intentionally limited to the code and
operations required for a safe, one-time card payment flow.

The integration must preserve the existing cash-on-delivery checkout and the
working cart, buy-now, order, admin, authentication, and catalog behavior.

## Authorization gate

This document does not authorize implementation by itself. No model, migration,
API, frontend, environment, deployment, or payment-provider change may start
until the user explicitly approves beginning the implementation phase.

Implementation approval must not be treated as approval to:

- edit `.env` or deployment secrets;
- run a real payment or refund;
- enable card payments for public customers;
- deploy to staging or production.

Those actions require their own task scope or explicit approval when reached.

## Fixed decisions

- Provider: Bank of Georgia Payments API.
- Payment method: bank card only.
- BOG request value: `"payment_method": ["card"]`.
- Capture mode: `"capture": "automatic"`.
- Currency: GEL only.
- Checkout sources: cart and buy-now.
- Payment page: BOG-hosted redirect page.
- Final payment truth: verified BOG callback or verified BOG payment-details
  response, never the browser redirect alone.
- Testing environment: the real BOG environment with the bank-provided GEL 100
  limit; no sandbox was provided.
- Card details are entered only on the BOG payment page. FlexDrive must never
  receive or store a card number, CVV, or full card expiry details.
- Credentials are read only from environment variables. They must not be
  committed, logged, returned to the frontend, or copied into this document.

## Explicit non-goals

The first integration will not include:

- installments;
- BNPL / part-by-part payments;
- Apple Pay;
- Google Pay;
- BOG internet/mobile-bank payment;
- loyalty points or gift cards;
- saved cards;
- recurrent or automatic card charging;
- split payments;
- manual capture / pre-authorization;
- embedded card forms;
- speculative provider abstractions that are not required by the BOG card flow.

## Official BOG documentation

- Introduction: <https://api.bog.ge/docs/payments/introduction>
- Authentication: <https://api.bog.ge/docs/payments/authentication>
- Create order: <https://api.bog.ge/docs/payments/standard-process/create-order>
- Payment details: <https://api.bog.ge/docs/payments/standard-process/get-payment-details>
- Callback: <https://api.bog.ge/docs/payments/standard-process/callback>
- Refund: <https://api.bog.ge/docs/payments/refund>
- Response codes: <https://api.bog.ge/docs/payments/response-codes>

## Target customer flow

1. The customer completes the existing checkout form and chooses card payment.
2. The backend revalidates the products, current prices, quantities, buyer data,
   terms acceptance, and cart/buy-now ownership.
3. The backend creates a time-limited stock reservation.
4. The backend creates one local pending payment attempt with an idempotency key
   and an immutable snapshot of the checkout data.
5. The backend authenticates with BOG and creates a BOG order using:
   - card-only payment method;
   - automatic capture;
   - GEL;
   - HTTPS callback URL;
   - success and failure redirect URLs;
   - matching basket and total amount;
   - a unique BOG `Idempotency-Key`.
6. The frontend redirects the browser to the exact URL returned by BOG.
7. BOG processes the card payment on its hosted page.
8. BOG sends a server-to-server callback.
9. The backend verifies `Callback-Signature` against the untouched raw request
   body before parsing JSON.
10. The backend matches the callback to the local payment attempt and verifies
    provider order ID, amount, currency, payment method, and final status.
11. On successful payment, one database transaction:
    - creates the FlexDrive order from the immutable checkout snapshot;
    - creates order-item snapshots;
    - decreases physical stock once;
    - completes the reservation;
    - links the payment record to the order;
    - marks the payment paid.
12. On failed, cancelled, declined, or expired payment:
    - no FlexDrive order is created;
    - physical stock is not decreased;
    - the reservation is released;
    - the payment attempt keeps its final failure state for audit.
13. The browser result page reads the status from FlexDrive. A `success`
    redirect query parameter must never mark a payment as paid.

## Data integrity rules

### Provider identifiers

BOG order IDs and BOG action/transaction IDs have different meanings and must
not share one uniqueness rule.

The payment model must distinguish:

- local immutable payment-attempt token;
- local provider-request idempotency key;
- BOG order ID;
- BOG payment transaction ID, when supplied;
- BOG action ID for refund or other provider actions, when supplied.

A refund action may refer to the same BOG order ID as the original payment.
Therefore BOG order ID must not be treated as a globally unique action ID.

### Amounts

- Local amount is calculated only by the backend.
- Frontend-supplied totals are never trusted.
- Currency is fixed to GEL.
- BOG basket sum, delivery amount, and total must reconcile exactly with the
  local snapshot before sending the request.
- Callback/payment-details amount and currency must match the local payment.
- A refund cannot exceed the remaining refundable paid amount.
- Duplicate refund requests must reuse the same local and BOG idempotency key.

### Payment attempts

- A retry after a network timeout must not create a second charge.
- One checkout attempt can have multiple sequential payment attempts only after
  the previous attempt is in a safe final state.
- A late callback from an older attempt must not overwrite the active/newer
  attempt or regress a paid/refunded order.
- Unknown BOG statuses are not guessed. They remain pending for reconciliation
  and are logged without sensitive payload data.

### Stock

- Online-payment start reserves stock; it does not decrease physical stock.
- Paid callback decreases stock exactly once.
- Failed/cancelled/expired payment releases the reservation.
- Reservation TTL must cover the BOG payment-order TTL with a small safety
  margin.
- An expired reservation cannot be converted into a paid order without a fresh,
  locked stock check.
- If BOG confirms payment but the local order cannot safely be fulfilled, the
  system records the incident and starts a BOG refund through the original
  payment channel. It must not perform an unrelated manual bank transfer.

## Callback security

- Public endpoint accepts POST only.
- CSRF is not used as callback authentication; only the narrowly scoped BOG
  callback endpoint may be exempted from API CSRF middleware.
- `Callback-Signature` is required.
- Signature verification uses BOG's published RSA public key and
  SHA256-with-RSA.
- Verification is performed on the exact raw request bytes before JSON parsing.
- Missing or invalid signatures return an error and do not change local state.
- Duplicate valid callbacks are idempotent and return HTTP 200 after confirming
  the already-applied state.
- Callback payloads are not logged in full because they may contain masked card
  and customer information.
- Browser redirects never call internal payment mutation services.

## Refund behavior

- Refund is performed only through the BOG refund API.
- Initial operational requirement: full refund.
- Partial refund will be implemented only if it can be represented accurately
  in the order/payment state and admin workflow; otherwise it remains disabled
  rather than being recorded as a full refund.
- Sending a refund request marks the local action `refund_pending`.
- BOG's `request_received` response is not final proof of a refund.
- Final `refunded` state requires a verified callback or payment-details result.
- Refund actions use their own idempotency keys.
- A failed refund remains visible to staff with a safe error code/message and
  can be reconciled without creating a duplicate refund.

## Order and admin rules

- Unpaid online payments cannot be moved to processing, shipped, or delivered.
- A paid online order cannot be cancelled by only restoring stock; cancellation
  must first follow the BOG refund workflow.
- Stock restoration happens once and only after the required payment/refund
  transition is safely recorded.
- Payment status is read-only in ordinary order admin editing.
- Provider records remain read-only audit data.
- Staff actions must clearly distinguish:
  - cancel unpaid attempt;
  - refund paid order;
  - retry status reconciliation;
  - view provider identifiers and safe error details.

## Frontend rules

- Card payment is enabled only through a backend feature/config response after
  deployment configuration is complete.
- Checkout submit for card payment calls payment-start, not the current
  cash-on-delivery order-creation endpoint.
- After receiving the BOG redirect URL, the browser navigates to BOG.
- Result page supports at least:
  - waiting for confirmation;
  - paid;
  - failed/declined;
  - cancelled/expired;
  - refund pending;
  - refunded;
  - temporary verification error with retry.
- The frontend polls only FlexDrive status endpoints, never BOG directly.
- Purchase analytics fires only when:
  - an online order is confirmed `paid`; or
  - an existing cash-on-delivery rule says the COD purchase is complete.
- Redirect success/fail parameters are display hints only.

## Environment configuration

Names may be adjusted to existing project conventions, but the final
configuration must cover:

- `BOG_PAYMENTS_ENABLED`
- `BOG_CLIENT_ID`
- `BOG_CLIENT_SECRET`
- `BOG_OAUTH_URL`
- `BOG_API_BASE_URL`
- `BOG_CALLBACK_PUBLIC_URL` or a safely derived public backend URL
- `BOG_FRONTEND_SUCCESS_URL`
- `BOG_FRONTEND_FAIL_URL`
- `BOG_CALLBACK_PUBLIC_KEY`
- payment/reservation TTL values

Production/staging startup must fail safely when payments are enabled but a
required value is missing. Payment credentials must be redacted from errors.

## Required backend endpoints

Exact paths will follow current `commerce` URL conventions.

- Start cart card payment.
- Start buy-now card payment.
- Read local payment attempt/result by public token.
- Receive BOG callback.
- Staff-only full refund action.
- Staff-only reconciliation/status refresh action, if exposed through admin.

No endpoint may accept an arbitrary amount, provider URL, provider order ID, or
payment status from the public frontend.

## Reconciliation

Callback delivery can fail. A management command or scheduled job must:

- find old pending BOG payments;
- fetch BOG payment details;
- apply the same idempotent state-transition service used by callbacks;
- release truly expired unpaid reservations;
- flag ambiguous cases for staff;
- never automatically retry a charge.

## Implementation phases

### Phase 1 — specification and safety foundation

- [x] Fix card-only scope and automatic capture decision.
- [x] Record official BOG flow and security requirements.
- [x] Separate provider order ID from provider action/transaction ID.
- [x] Add local immutable payment token and provider idempotency key.
- [x] Add checkout snapshot storage required to create an order after payment.
- [x] Enforce payment action and amount rules.
- [x] Prevent payment-state regression across multiple attempts.
- [x] Add database constraints/indexes required by the final model.

Phase 1 verification:

- local migration `commerce.0021_payment_transaction_safety_foundation` applied;
- Django system and migration checks passed;
- 157 commerce tests passed;
- 5 PostgreSQL-only concurrency tests were skipped by local SQLite and remain
  required in a PostgreSQL environment.

### Phase 2 — BOG backend adapter

- [x] OAuth token client with bounded timeout and safe errors.
- [x] BOG create-order client with card-only/automatic/GEL payload.
- [x] BOG payment-details client.
- [x] BOG full-refund client.
- [x] Consistent HTTP timeout, retry, and idempotency policy.
- [x] Sensitive-field redaction in logs and stored provider data.

Phase 2 verification:

- official BOG authentication, create-order, payment-details, and refund
  contracts rechecked on 2026-06-23;
- adapter remains isolated from checkout and cannot run through the settings
  factory while `BOG_PAYMENTS_ENABLED` is false;
- create-order always sends `payment_method: ["card"]`, `capture: "automatic"`
  and `currency: "GEL"`;
- create-order and refund require a UUID v4 idempotency key;
- no automatic retry is performed after an ambiguous create/refund transport
  failure; a caller must reconcile or retry with the same idempotency key;
- one retry is allowed after HTTP 401, using a refreshed access token and the
  same idempotency key;
- full refund deliberately omits the optional partial-refund amount;
- known customer/card/token fields are removed from provider references before
  they can be stored;
- 18 isolated BOG adapter tests passed without real network requests;
- 175 commerce tests passed, with 5 PostgreSQL-only concurrency tests skipped
  by local SQLite;
- Django system check and migration drift check passed, apart from the existing
  unrelated CKEditor 4 support warning.

### Phase 3 — online checkout orchestration

- [x] Cart payment-start service and endpoint.
- [x] Buy-now payment-start service and endpoint.
- [x] Immutable checkout and legal-acceptance snapshot.
- [x] Reservation TTL alignment with BOG order TTL.
- [x] Safe recovery when BOG create-order times out.
- [x] Local payment-status endpoint.

Phase 3 backend endpoints:

- `POST /api/commerce/payments/card/cart/start/`
- `POST /api/commerce/payments/card/buy-now/start/`
- `GET /api/commerce/payments/card/<payment-token>/`

Phase 3 verification:

- card start requires reCAPTCHA, accepted terms, card payment method, and a
  UUID-v4 `Idempotency-Key`;
- cart and buy-now flows create a stock reservation and local BOG payment
  attempt before calling BOG;
- the database transaction is committed before the external BOG request, so a
  slow provider response does not hold product/cart database locks;
- physical product stock, cart items, and buy-now sessions remain unchanged
  until a verified paid result is handled in phase 4;
- the immutable snapshot contains buyer/order-item/price/legal/marketing data
  required for later order creation and includes an integrity hash;
- BOG receives only the immutable snapshot values, not newly changed cart or
  form values during a same-key retry;
- a timeout or retryable BOG error keeps the same local attempt, reservation,
  snapshot, and BOG idempotency key for safe retry;
- a definitive create-order rejection fails the attempt and releases its
  reservation without reducing physical stock;
- a second online attempt and a cash-on-delivery checkout are blocked while an
  unresolved online attempt exists for the same cart/buy-now owner;
- passing the local TTL alone does not falsely mark an unknown bank result as
  failed; it becomes `verification_pending` until phase 4 verifies BOG details;
- public status output does not expose buyer data, provider references,
  provider IDs, credentials, or the internal checkout snapshot;
- both authenticated and guest cart/buy-now ownership paths are covered;
- 22 focused payment-orchestration tests passed without real BOG requests;
- 197 commerce tests passed, with 5 PostgreSQL-only concurrency tests skipped
  by local SQLite;
- Django system check, Python compilation, and migration drift check passed,
  apart from the existing unrelated CKEditor 4 support warning.

Operational note: `BOG_PAYMENTS_ENABLED` must remain false for public checkout
until phase 8 controlled real-environment tests are complete.

### Phase 4 — callback and order finalization

- [x] Narrow CSRF exemption for BOG callback only.
- [x] Raw-body RSA signature verification.
- [x] BOG status/amount/currency/method validation.
- [x] Idempotent paid-order creation and stock commit.
- [x] Idempotent failure/cancellation/expiry release.
- [x] Duplicate and out-of-order callback handling.
- [x] Unknown-status reconciliation behavior.

Phase 4 callback endpoint:

- `POST /api/commerce/payments/bog/callback/`

Phase 4 verification:

- the official BOG RSA public key published in the callback documentation is
  the default verification key and can be replaced through
  `BOG_CALLBACK_PUBLIC_KEY` if BOG rotates it;
- `Callback-Signature` is verified with RSA PKCS#1 v1.5 and SHA-256 against the
  exact raw request bytes before UTF-8 decoding or JSON parsing;
- malformed signatures, altered bodies, duplicate JSON keys, invalid callback
  events/timestamps, and oversized bodies are rejected without payment changes;
- the callback is the only state-changing commerce API path exempted from the
  application's API CSRF middleware; all normal browser API POST requests
  remain CSRF-protected;
- callback order ID, local external order ID, industry, automatic capture,
  requested/transferred amount, GEL currency, card method, direct-debit option,
  and provider transaction ID are validated before a paid transition;
- callbacks can safely recover a BOG order ID when create-order succeeded at
  BOG but the response timed out before the local record was updated;
- signed `completed` creates the FlexDrive order from the immutable snapshot,
  commits stock once, completes the reservation, links the checkout attempt,
  and marks both payment and order paid in one database transaction;
- duplicate completed callbacks return HTTP 200 without creating a second
  order or decreasing stock again;
- signed `rejected` fails the still-unpaid attempt and releases its reservation,
  while a late rejected callback cannot regress an already paid order;
- expired reservations receive a fresh locked stock check before paid order
  creation; stock is never allowed to become negative;
- if BOG confirms payment but safe fulfillment is impossible, the payment is
  recorded as paid, no unsafe order/stock mutation occurs, and a clear
  `paid_*` incident remains for the phase 5 provider-refund workflow;
- a late success from an older attempt cannot override a newer pending or paid
  attempt for the same checkout owner/source;
- unknown, manual-capture, and refund-related statuses do not guess a state or
  regress the sale; they remain marked for reconciliation;
- authenticated BOG payment-details lookup uses the same validation and
  finalization service as the signed callback;
- callback provider evidence is redacted before storage; buyer, masked PAN,
  expiry, authorization code, credentials, and raw callback body are not
  exposed through the public status endpoint;
- 27 focused callback/finalization tests passed without real BOG requests;
- 224 commerce tests passed, with 5 PostgreSQL-only concurrency tests skipped
  by local SQLite;
- Django system check, Python compilation, dependency declaration, and
  migration drift check passed, apart from the existing unrelated CKEditor 4
  support warning.

Operational note: `BOG_PAYMENTS_ENABLED` must remain false for public checkout
until phase 8 controlled real-environment tests are complete.

### Phase 5 — refund and admin

- [x] Full refund service and idempotent BOG request.
- [x] Refund callback/details reconciliation.
- [x] Paid-order cancellation guard.
- [x] Admin refund action with confirmation and clear result.
- [x] Admin visibility for pending/failed reconciliation.
- [x] Decide partial-refund launch only after accurate state support is tested.

Phase 5 verification:

- a full refund creates a separate immutable BOG refund transaction with its
  own UUID-v4 idempotency key and deliberately omits BOG's optional partial
  amount;
- BOG's `request_received` response records the provider action ID but leaves
  both refund and order in `refund_pending`; it is never treated as final proof
  that money was returned;
- a retry after a timeout reuses the same local refund transaction and the same
  BOG idempotency key, preventing a second independent refund request;
- a definitive BOG request rejection marks that refund action failed and
  safely returns the order payment state from `refund_pending` to `paid`;
- verified callback/payment-details states parse and reconcile BOG refund
  actions, action IDs, amounts, completion, and rejection without changing the
  original paid sale record incorrectly;
- a verified full refund marks the refund and order refunded, then cancels an
  eligible new/confirmed/processing order and restores stock exactly once;
- shipped/delivered orders are not automatically restocked by this initial
  cancel-and-refund workflow because physical returned-stock handling does not
  yet exist;
- BOG-manager/external refunds remain visible and require order/stock review
  instead of silently assuming that a product has physically returned;
- conflicting provider evidence, out-of-order refund callbacks, amount
  mismatches, and partial refunds stay in an explicit reconciliation state;
  they do not guess a successful full refund or restore stock;
- partial refund launch remains disabled. If BOG reports a partial refund
  outside this flow, FlexDrive flags it for manual reconciliation rather than
  recording the order as fully refunded;
- paid online orders remain protected from the ordinary
  `Cancel and restore stock` action;
- order admin provides separate confirmation screens for full refund and BOG
  status refresh; payment-transaction admin provides the same recovery tools
  for paid incidents where local order creation was blocked;
- provider IDs, action IDs, safe error codes, timestamps, and pending/failed
  states are visible in read-only payment audit records;
- no phase 5 model change or migration was required;
- 30 focused refund/adapter tests and 29 callback/finalization tests passed
  without real BOG requests;
- the full commerce regression passed: 238 tests, with 5 PostgreSQL-only
  concurrency tests skipped by local SQLite;
- Django system check, Python compilation, migration drift check, dependency
  check, and diff whitespace check passed, apart from the existing unrelated
  CKEditor 4 support warning.

Operational note: `BOG_PAYMENTS_ENABLED` must remain false for public checkout
until phase 8 controlled real-environment tests are complete.

### Phase 6 — frontend

- [x] Backend-driven card-payment availability.
- [x] Card start request and BOG redirect.
- [x] Result/status page for all required states.
- [x] Cart/buy-now recovery after failed or expired payment.
- [x] Paid-only online purchase analytics.
- [x] Georgian customer messages without exposing provider internals.

Phase 6 implementation note:

- card payment availability is read from the backend and remains disabled
  unless `BOG_PAYMENTS_ENABLED` is explicitly enabled in the environment;
- cart and buy-now checkout can start a card payment with the existing
  checkout form data, recaptcha, marketing-consent header, and checkout
  idempotency key;
- successful card start redirects only to a validated HTTPS provider URL;
- the payment result pages verify local FlexDrive payment status by
  `payment_token` instead of trusting the bank redirect URL text;
- pending, failed, cancelled, paid-with-order, paid-needs-review,
  refund-pending, and refunded states have Georgian customer-facing copy;
- cart/buy-now recovery uses short sessionStorage context only and does not
  store payment credentials or sensitive data;
- purchase analytics is blocked for card orders unless the local order summary
  has `payment_status=paid`;
- the old frontend validation rule that rejected card payments as "coming
  soon" was removed; actual availability is controlled by the backend flag;
- no real BOG request or real payment was executed during this phase.

Phase 6 verification completed:

- frontend `npm run typecheck` passed;
- frontend `npm run lint` passed;
- frontend `npm run build` passed, with only existing dependency warnings
  about stale Browserslist data and Vue package export deprecation;
- browser QA covered payment result pages at 320, 375, 768 dark, 1024, and
  1440 widths for pending, failed, paid-needs-review, and refunded states;
- browser QA covered checkout card selection at 320, 375, 768 dark, and
  1440 widths;
- browser QA found no horizontal overflow, no console/page errors, visible
  safe card-payment copy, and usable submit controls;
- backend `manage.py check` passed with the existing unrelated CKEditor 4
  warning;
- backend migration drift check passed with no changes detected;
- full commerce regression passed: 240 tests, with 5 PostgreSQL-only
  concurrency tests skipped by local SQLite.

### Phase 7 — automated verification

- [x] Model and migration tests.
- [x] Payment-start validation tests.
- [x] BOG payload contract tests.
- [x] OAuth expiry/cache tests.
- [x] Signature-valid and signature-invalid callback tests.
- [x] Duplicate callback tests.
- [x] Out-of-order callback tests.
- [x] Same-idempotency retry tests.
- [x] BOG timeout-before/after-processing tests.
- [x] Concurrent last-item reservation/payment tests on PostgreSQL.
- [x] Paid finalization stock-decrement-once tests.
- [x] Failed/cancelled reservation-release tests.
- [x] Refund success, duplicate, failure, and timeout tests.
- [x] Frontend typecheck, lint, and production build.

Phase 7 verification completed:

- added card payment-start validation tests for missing terms acceptance and
  failed reCAPTCHA; both cases create no payment, reservation, or BOG request;
- added a model regression test proving that one BOG order ID can be shared by
  the original sale and a refund action, while provider transaction/action IDs
  remain independently unique;
- added a PostgreSQL-only concurrent last-item card-payment-start test: two
  buyers attempt to reserve the final unit at the same time, exactly one local
  BOG payment/reservation can be created, physical stock is not decreased, and
  available stock becomes zero;
- local SQLite correctly skips the PostgreSQL-only concurrency test; it must be
  executed in a PostgreSQL environment before public enablement;
- targeted backend verification passed: 73 tests, with 1 PostgreSQL-only
  concurrency test skipped by local SQLite;
- backend `manage.py check` passed with the existing unrelated CKEditor 4
  warning;
- backend migration drift check passed with no changes detected;
- full commerce regression passed: 244 tests, with 6 PostgreSQL-only
  concurrency tests skipped by local SQLite;
- frontend `npm run typecheck`, `npm run lint`, and `npm run build` passed;
- frontend build warnings were limited to existing dependency-maintenance
  warnings: stale Browserslist data and Vue package trailing-slash export
  deprecation.

### Phase 8 — controlled real-environment test

- [ ] Deploy code with card option still hidden/disabled for normal customers.
- [ ] Configure BOG credentials only in deployment secrets.
- [ ] Confirm callback HTTPS reachability.
- [ ] Confirm callback signature against a real callback.
- [ ] Run a minimal successful card payment.
- [ ] Confirm order creation and one-time stock decrement.
- [ ] Confirm payment details in BOG manager.
- [ ] Run a declined/cancelled payment.
- [ ] Confirm reservation release.
- [ ] Run a full refund.
- [ ] Confirm verified refund state and customer-side balance behavior.
- [ ] Test duplicate callback/reconciliation behavior where operationally safe.
- [ ] Enable card payment publicly only after every mandatory check passes.

## Definition of done

The card option may be publicly enabled only when:

- backend and frontend automated checks pass;
- no secret is present in Git or frontend output;
- one real successful payment has been reconciled end to end;
- one real failed/cancelled attempt has released stock;
- one real full refund has reached a verified final state;
- duplicate callback handling is proven idempotent;
- an unpaid order cannot enter fulfillment;
- purchase analytics does not fire for pending/failed online payments;
- staff have a documented recovery path for pending payment and failed refund;
- cash-on-delivery behavior remains unchanged.
