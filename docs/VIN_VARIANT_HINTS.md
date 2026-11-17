# Existing supplier version mentions in VIN search

Prepared 2026-11-17 on clean backend `1f86fa3` / frontend `d797a6f` worktrees.
User requested a reversible local implementation using existing supplier data.
No production deployment, commit/push, database schema/content or ENV changes.

## Behavior

- vPIC lookup additionally retains bounded optional Trim/Trim2/Series/Series2.
  It still requires complete VIN, ErrorCode 0 and exact internal make/model/year
  coverage. It does not infer a new model, engine, body type or part/OEM fitment.
- Recognized version mentions become a bounded `variant` catalog query context,
  e.g. `gli`, `sport,limited`, `ex_v6`. Missing/unrecognized version is explicitly
  `unspecified`; it is never assumed to mean all versions. Only canonical keys
  enter the URL; raw VIN and provider descriptions do not.
- Existing product names and only matching-vehicle/year fitment notes supply
  mentions. No importer, source fields, product names or fitments are rewritten.
  This deliberately does not require new supplier data or a manual catalog refill.
- Recommended results prioritize matching mentions within existing availability
  tiers. Search identifier/name relevance stays first; explicit price/name/date
  ordering remains unchanged. Suggestions retain the same version context.
- ALL products satisfying the existing vehicle/part filters stay in the result.
  A different, missing or negated mention never hides an item or proves it is
  incompatible. Conversely, a mention (including a styling/"look" reference)
  never proves exclusive or complete compatibility.
- Cards say `მოდელი და წელი ემთხვევა`. With version context they additionally say
  `მითითებულია: GLI` for a matching text mention or `ვერსია გადასამოწმებელია`.
  Existing explicit-engine and universal badges retain their separate behavior.
- The vehicle chip includes the version. Header part searches, refinements,
  sorting, pagination and Back preserve context. Changing vehicle/year/engine or
  resetting the car clears it; same-car mobile refinements retain it.

## Recognition and limits

Current controlled vocabulary: M Sport, R-Line, ST-Line, EX-V6, EX-L, GLI, GTI,
GTE, GTD, AMG, Sport, Limited, Hybrid, Premium, Touring, XLE, XSE, SEL, SE, LE,
LX and EX, with selected Georgian Sport/Hybrid/Limited spellings. Composite names
stay distinct; substrings in Sportage/Sportback/Sportline, lighting codes and
Sport Utility body-class text do not become trim hints.

Common explicit negatives (non/not/except/without and Georgian გარდა/გარეშე/
არ ერგება forms) and conflicting mentions prevent promotion. This is a limited,
conservative text parser, not an exhaustive natural-language compatibility engine.
An unknown supplier spelling or unsupported vPIC trim remains unverified.

vPIC identity cache is versioned to v2 so previous entries lacking optional trim
fields do not conceal newly available data. TTLs remain 7 days / 5 minutes / 20
seconds. Internal model/coverage matching and text hints are evaluated from current
catalog data, without durable derived metadata or per-item database queries.
Variant-specific ordering adds at most two lightweight name/note reads. Existing
catalog filtered-query SEO policy already gives these URLs noindex and base canonical.

## Verification

- 46 backend tests: parser boundaries/composites/negatives, malformed context,
  optional provider fields, honest metadata, stock/explicit order, part queries,
  suggestions, matching-fitment scope and stable complete pagination, plus existing
  VIN/header/recommendation behavior.
- 71 frontend tests: actual header/catalog behavior, preserving version across
  part search/sort/page/mobile refinements, removing it on manual car edits/reset,
  honest card labels, existing suggestion templates and filter controls.
- Scoped ESLint, strict Nuxt typecheck and isolated production build pass.
  Existing CKEditor/local staticfiles and Browserslist/DEP0155 warnings remain.
- Existing LOCAL SQLite checked under `PRAGMA query_only=ON`, no fixtures added:
  Volkswagen Jetta 2017 remains 117 products before/after. First results with
  `variant=gli`: FD-04-0250 `ცხაურა GLI`, FD-04-0328
  `წინა ბამპერის კომპლექტი (GLI)`. Unknown-version lamps/hood/bumper remain.
- No browser automation was run: project requires an explicit browser verification
  request. User will inspect local UI. Provider response tests use a public example
  VIN, never customer VINs or synthetic production analytics events.

Local review: restart backend and open the normal local frontend route:
`/catalog?make=volkswagen&model=jetta&year=2017&variant=gli`.
Then search `ბამპერი`, change sort/page, and change the car/year.

No migration, new ENV, paid service or cron is required. Both repositories must be
deployed together later. Rollback is the feature source diff from the base commits
above; no data rollback/backfill is necessary. Earlier base VIN functionality and
the user's removed explanatory lines remain preserved.
