# VIN → vehicle filters → part search

Implemented 2026-11-17; user owns backend and frontend push/deploy. No production
DB, inventory, price, provider-account or environment changes. No migration,
API key, new dependency, paid service or scheduled job required.

## Customer behavior

The common header search accepts a complete 17-character VIN (case insensitive,
outer whitespace trimmed). Enter or Search performs one explicit lookup, not a
lookup on every keystroke. `VIN: ...` can explicitly identify an incomplete input
and receive format guidance. Mobile uses the same flow.

A reliable match navigates to `/catalog?make=...&model=...&year=...`, clearing the
VIN/search draft and previous category, engine, price, brand, stock and page
refinements. Existing catalog vehicle labels and removable filters show the car.
Typing a part name, e.g. `კაპოტი`, searches within the same make/model/year.
Changing/removing the vehicle continues to use existing catalog controls.

A failed, ambiguous or unsupported match stays on the current page with feedback;
it never falls back to an unrelated model or the whole catalog. A decoded vehicle
with no published fitments for that year says parts are not currently listed.
Out-of-stock published products remain eligible under normal catalog behavior.
At the user's request, both lower explanatory lines and the search-as-part button
were removed from desktop/mobile feedback. Only primary lookup feedback remains.
VIN-shaped 17-character codes now use the decoder; other part queries keep their
ordinary search behavior.

## Contract and safeguards

`POST /api/catalog/vehicles/vin/` takes JSON `{ "vin": "..." }`. It is public,
read-only, subject to existing auth/launch middleware plus a dedicated 10/minute
per-user/IP scoped throttle and existing anonymous/user throttles. GET is 405.
Responses, including errors, have `private, no-store` and `noindex, nofollow`.

- 200 `matched`: normalized vehicle and internal make/model slugs/year filters.
- 200 `not_in_catalog`: decoded identity cannot map to exactly one active model.
- 200 `no_coverage`: exact model exists but no published, active-category fitment
  covers that year with an active/null engine.
- 200 `unrecognized`: provider reports incomplete/incorrect/unsupported decoding.
- 400 `invalid_vin`; 429 throttled; 503 `unavailable`.

Only the fixed official vPIC HTTPS host is requested. No redirects/retries or
caller URL; connect/read timeouts 3.05/6 seconds, response cap 256 KiB. Client uses
a 12-second timeout, no automatic retries and AbortController. Edited input,
closed panel, route change or unmount invalidates/aborts obsolete results.

Provider HTTP 200 is insufficient: one matching VIN row, ErrorCode exactly 0,
nonempty bounded make/model and a plausible model year are required. Suggested
VINs and warning/error data never silently select a vehicle. No engine/trim guesses.

Matching is exact after case/punctuation normalization against name/slug, scoped
to the make. Mercedes-Benz → Mercedes is a manufacturer spelling alias only.
No fuzzy or cross-market model equivalence (e.g. XV/Crosstrek), BMW trim→series
inference, new taxonomy/fitments, or fallback to a similarly named model. Such
vehicles require manual selection. Saved product compatibility remains authority;
VIN identification does not prove a part fits a trim/body/facelift/engine.

VINs are not added to catalog URLs, product suggestions, normal search analytics,
history or application logs by this flow. Request body goes to the backend and
VIN goes to NHTSA for decoding. Sidebar actions do not accidentally apply
an unsubmitted VIN as product q. Cache uses SHA256 keys and only normalized identity:
7 days decoded, 5 minutes unrecognized, 20 seconds unavailable. Internal mapping
and coverage re-evaluate every lookup so taxonomy/publication changes take effect.

## Verification

- 21 backend VIN/header-filter tests pass: anonymous POST, validation, provider
  warnings/malformed responses/timeouts/redirects/size, exact/ambiguous mappings,
  year/category/engine/publication, out-of-stock, cache with live taxonomy,
  throttling and subsequent scoped part search.
- 66 frontend header/catalog/refinement tests initially passed: desktop/mobile success then
  part query, stale/aborted/duplicate requests, route changes, errors/retries,
  explicit part-code fallback, actual Vue template feedback and POST contract.
  After the copy simplification, the obsolete fallback test was removed and all
  35 header/template tests passed again.
- Scoped ESLint and Nuxt strict typecheck pass.
- Isolated Nuxt production build completed successfully (client, SSR and Nitro).
  Existing Browserslist/Node DEP0155 warnings remain; no new build failure.
- Live decoder read against the public example VIN identifies Honda Accord 2003,
  ErrorCode 0; no customer VIN used and no production data written.
- Production build uses isolated generated/output directories; user dev services
  are untouched. Browser/viewport verification has not been run for this feature
  (project requires an explicit browser-verification request).

After deploying both repos, verify in the storefront with a known vehicle VIN:
car selected → VIN absent from q/input → part name keeps vehicle → remove/change
car normally. Also verify a VIN with no catalog coverage. Provider availability,
real taxonomy spellings and coverage can differ from unit fixtures; local tests
are not a claim of production end-to-end validation.

Official references:
[vPIC API](https://vpic.nhtsa.dot.gov/api/),
[coverage/FAQ](https://vpic.nhtsa.dot.gov/api/Home/Index/FAQ).
NHTSA documents partial decode support and automated rate control; our full-VIN,
strict-success policy deliberately avoids uncertain automatic catalog filtering.
Nuxt v4 documentation supports event-triggered POST via existing fetch wrapper,
without placing VIN body in useAsyncData keys or SSR payloads.
