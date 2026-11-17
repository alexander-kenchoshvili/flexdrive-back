# Meta marketing signals — 2026-11-18

User requested a bounded audit and useful missing signals before deploying both
repositories. Specifically approved existing `_fbp`/`_fbc` identifier forwarding
in the async reply on 2026-11-18, after automatic review required that specific
payload/destination consent. No ad-account, conversion, audience, campaign, budget,
GTM publication, production database or provider-event action was performed.

## Existing event inventory

Live public GTM-MVNFL9TH version10 was inspected during the preceding VIN task.
Its existing Meta base initializes Pixel1020718363721235 and PageView. Existing
commerce mapping is:

| Storefront action | Meta event | Relevant payload |
| --- | --- | --- |
| Product detail | ViewContent | Public FlexDrive SKU, name, price, quantity, GEL |
| Successful add to cart | AddToCart | Added product SKU/quantity/value |
| Successful add to wishlist | AddToWishlist | Product SKU/value |
| Checkout entered | InitiateCheckout | Checkout items/quantities/value |
| Payment information submitted | AddPaymentInfo | Checkout items/quantities/value |
| Completed purchase | Purchase | Items, total, GEL, order number, matching event ID |

GA4 separately receives view_cart/remove_from_cart and search-result selection.
They have no equivalent required Meta standard commerce event in the current
mapping. They are not mislabeled as another purchase/cart-add or added as noisy
custom events. Existing GA4 tags remain unchanged. Search Console concerns Google
search visibility; it does not deliver user events into Meta.

Purchase CAPI already exists server-side: approved marketing consent, paid card
orders or delivered COD orders. Browser/server share purchase-{order_number}
event IDs and frozen public item SKUs. Existing server matching data includes
hashed email, phone, first/last name, city and account ID when available, plus
checkout IP/user-agent. Hashes are matching identifiers, not anonymous statistics.
No new names/addresses/contact fields were added to that existing contract.

## Added or corrected

1. Shared `useMetaMarketing` now owns VIN/part `Search` and `Contact` events via
   the existing GTM-initialized fbq. `useVinSearchMarketing` is a thin adapter.
   Do not create duplicate GTM forwarding tags for these same actions.
2. VIN Search retains safe make/model/year and decoded outcome; invalid/provider
   failures/stale results do not count. See VIN_SEARCH_MARKETING.md.
3. Part Search reuses the existing successful API result + query dedup hook.
   Sends search_type=part, API total and results/no_results. Normalizes only the
   analytics copy, preserving actual customer search. For obvious email/phone/
   long-number/17-character VIN input it omits search_string entirely. No result
   product IDs are invented. API failure is not reported as zero results.
4. Contact is fired only after a successful contact-form response, not a button
   click, validation failure or failed request. Payload is only
   contact_method=website_form; no message/topic/order/contact input is forwarded.
   It is Contact, not an invented sale or automatic duplicate Lead.
5. Consented checkout sends only existing validated `_fbp`/`_fbc` cookie values in
   explicit X-FlexDrive-Meta-Fbp/Fbc headers on the existing checkout/payment-start
   endpoints. CORS allows those two headers. No new cookie or fabricated fbc for
   direct traffic; no raw fbclid search/history harvesting. Client host and consent
   gates apply. Backend also validates bounded format and consent before capture.
   Existing marketing_context JSON carries these original values through the bank
   snapshot to CAPI. They are not hashed, lowercased or reconstructed from a bank
   callback's browser. Invalid/missing/old contexts omit them safely.
6. Explicit denied marketing header now wins over an older granted cookie.
   Existing local Georgian mobile numbers gain country code995 for the outgoing
   phone hash; full international inputs remain supported. Source phone values
   and checkout validation are unchanged.
7. Browser COD Purchase now requires delivered status, matching existing CAPI.
   A newly placed unpaid COD order is not counted as completed revenue. Paid-card
   rule, event IDs, totals, receipt eligibility and refund handling are unchanged.
   A refund does not automatically erase a historical Meta Purchase event; actual
   net sales/accounting remain first-party business data.

New browser signals require both existing analytics + marketing consents, valid
GTM ID and canonical flexdrive.ge. Current business users/internal browser flag
are excluded. Bounded ten-second in-memory wait for fbq, scope disposal/revocation
cleanup and failure isolation are retained. Each explicit valid VIN search is an
event; the business demand panel uses distinct sessions and different consent
rules, so its counts are not a promise of Meta receipt or equal totals.

## Deployment and remaining receipt check

Deploy backend then frontend. No NEW migration/ENV/cron/dependency is required by
these marketing changes. The preceding vehicle-demand migration business0002 is
still required independently and will be applied in the user's agreed later step.
No production migration/deployment was done during this task.

After deployment, check actual Search/Contact and existing commerce events in
Meta Events Manager, using a consented non-internal browser without a blocker.
Validate Purchase browser/server deduplication and fbp/fbc presence on a real
approved test transaction; do not fabricate an ad click or another charge merely
to fill reports. Real event reception/Ads Manager optimization eligibility is not
proven by source, mocks or fbq calls. A VIN custom conversion still needs separate
account configuration after event receipt if selected for future campaigns.

No DOB/gender, raw VIN, message text, arbitrary clickstream or speculative
registration conversion was added. No additional paid tracking service needed.

## Focused validation

- 88 frontend checks pass: VIN/part/Contact dispatch, consent/internal gates,
  delayed/blocked Pixel, identifier bounds, catalog dedup, real receipt-success
  component including COD delivery eligibility, existing header and consent flows.
- 11 backend checks pass: six new pure mocked attribution/consent/hash cases and
  five existing SKU/payload/receipt checks. No actual Meta HTTP call made.
- Scoped ESLint, strict Nuxt typecheck and whitespace checks pass. No full build
  or browser automation. Existing CKEditor warning remains unrelated.

Sources: [Meta Pixel event definitions](https://developers.facebook.com/documentation/meta-pixel/reference),
[existing fbp/fbc values](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/fbp-and-fbc),
[customer parameter formatting](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/customer-information-parameters),
[browser/server event IDs](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/server-event).
