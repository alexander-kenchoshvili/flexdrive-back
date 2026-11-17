# VIN search: business demand versus Meta Pixel

Implemented 2026-11-18. The live public GTM-MVNFL9TH script was read without
changing the container: version 10 has the existing commerce mapping, including
AddToCart/Purchase, but no Search event or VIN mapping. Merely installing GTM,
Pixel or Search Console does not send VIN searches to Meta.

Later on the same date, the dispatcher was shared as `useMetaMarketing` and part
Search/Contact/checkout attribution were added. `useVinSearchMarketing` remains
the VIN adapter. See META_MARKETING_EVENTS.md for the complete current contract.

## Frontend event contract

`useVinSearchMarketing` is instantiated synchronously in HeaderSearch setup.
After an explicitly submitted VIN returns a current, non-cancelled result, it
sends the standard Meta `Search` event through the existing GTM-initialized
`window.fbq`. Typing, invalid/unrecognized VINs, provider errors, stale requests,
ordinary part searches and catalog pagination do not trigger this hook.
`ViewContent` remains the product-page event and is not reused for a VIN action.

Example payload (not a claim about any actual customer's vehicle):

```js
fbq("track", "Search", {
  search_string: "Toyota Prius 2015",
  search_type: "vin",
  vehicle_make: "Toyota",
  vehicle_model: "Prius",
  vehicle_year: 2015,
  vin_outcome: "matched"
});
```

Decoded `no_coverage` and `not_in_catalog` results also emit Search with their
actual outcome: the visitor searched, but catalog coverage was missing. They
must not be presented as product availability or a sale. Raw VIN, signed interest
token, account/session identifiers, free search input, trim/provider response,
invented product IDs and financial value are excluded by construction.

Existing combined analytics + marketing consent, canonical flexdrive.ge, valid
GTM configuration and non-business/non-internal browser gates apply. The existing
Pixel queue may load after the decoder: at most ten sanitized events are retained
in memory for up to ten seconds, checking availability every 250ms only while
pending. Revocation, scope disposal or entering an excluded context clears them.
No later-consent replay, extra Pixel initialization, new script or CAPI call.
Pixel errors cannot block VIN results. Ad blockers/denied consent can prevent
delivery; calling fbq is not evidence that Meta received an event.

**Single event owner:** the frontend sends this VIN event directly to the Pixel
installed by GTM. Do not add a second GTM tag forwarding the same action without
removing this dispatcher, or it will double-count. Existing commerce and GA4
part-search tags are unchanged. No new GA4 VIN event or dimension is configured.

## Existing business panel

`/business/vehicle-demand` remains the separate, first-party demand report from
`docs/VEHICLE_DEMAND.md`. It includes VIN and manual vehicle selection and counts
distinct search sessions rather than every explicit Search event. It requires
analytics consent; Meta additionally requires marketing consent. Counts therefore
need not match and the panel does not claim verified Meta delivery or ad results.
No second copy of the demand table or misleading connected/received status added.

## Deployment and practical verification

This addition requires a **frontend deployment only**, no new migration/ENV/job,
GTM publication or paid service. The earlier demand feature independently still
requires both deployments and business.0002 if not already applied.

After deployment, use a non-internal browser with both consents and no Pixel
blocker. Submit a valid public sample VIN. In Meta Events Manager / Test events
for FlexDrive Web Pixel 1020718363721235, confirm one Search event and its safe
parameters, including search_type=vin and the correct vin_outcome. Do not treat
these unit checks as a live receipt test. Do not fabricate a customer event from
the agent or count existing internal tests as actual customer demand.

For future advertising, a custom conversion such as "VIN search" can use
Search + search_type=vin; optionally vin_outcome=matched to focus on covered cars.
It must be created/selected in the appropriate ad account after the event is
received, with actual eligibility checked in Ads Manager. No conversion, audience,
campaign or budget was created/changed here. Search optimization finds searches;
it does not guarantee purchases or equivalent performance to Purchase optimization.

## Required validation

Focused consent/privacy/result/delayed-Pixel/error tests and existing HeaderSearch
tests pass; scoped ESLint passes. No build, browser automation, real provider
event, production DB write or deployment performed.

Sources: [Meta Pixel standard events](https://developers.facebook.com/documentation/meta-pixel/reference),
[Custom conversions and event/parameter rules](https://developers.facebook.com/docs/marketing-api/reference/custom-conversion/).
