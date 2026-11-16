# Recommended catalog order

Prepared2026-11-16 for local user review; no push/deployment or production action.

Default listing, including make/model/year/category filters without a text query,
now mixes principal parts before ordinary parts and small accessories. The same
behavior is available with `ordering=recommended`. The existing frontend already
uses the default API order for its Recommended option.

Current principal families: hoods, headlamps/tail lamps/fog lamps, complete
bumpers, fenders, complete doors, mirror assemblies, radiators, grilles, and
reinforcement/body support panels. Matching uses whole Georgian part nouns;
possessive accessory names and explicit brackets/rails/caps/bolts do not inherit
the principal part's priority. Rules are centralized in catalog/recommendations.py.
Unknown names remain ordinary parts. Classification affects order only.

Ordering:

1. Existing customer-stock availability rule first.
2. Principal, ordinary, then small accessory tier.
3. Round-robin across the available principal families: one item or left/right
   pair from each family, then their second groups, etc. A large number of hoods cannot crowd other
   principal families out of the first round. Once other families are exhausted,
   remaining products still appear; nothing is repeated to manufacture variety.
4. Stable product/group ID hashes mix models/items within families; featured items lead within
   their family. No random() or changing date/session seed is used.

Left/right pairs (2026-11-16):

- Whole side labels (LH/RH, left/right, მარცხენა/მარჯვენა) are removed from
  otherwise identical names for comparison. All remaining variant words remain.
  Structured side fields must agree with a name's side label when both exist.
- Category, brand, placement, universal status and the ENTIRE fitment set must
  match: model, engine, exact year range and notes. Fitment notes retain steering
  side and trim differences. Filtered matching-fitment subsets are not used to
  infer a pair. Non-universal products without fitments remain independent.
- Only one unambiguous left and one right candidate are paired within the same
  availability/family tier. Duplicates or conflicting sides stay independent.
  An unavailable opposite does not move ahead of stocked products.
- A pair occupies one family turn, with its two products consecutive. Other
  families still mix between groups. If either side is featured, the group leads
  within its family. Ordinary parts and small accessories can also form pairs
  without changing their priority tier.
- Pair recognition uses two lightweight metadata queries; SQL group ranking
  happens before pagination. Product details/images are loaded only for the page.
  No product records, prices, stock or names are edited.
- Pagination is unchanged by explicit user request: the frontend still requests
  15 products per page (except the final page). A pair can straddle the last slot
  of one page and the first slot of the next. No variable page sizes or page gaps.
- Local read-only catalog sample:1995 published products,547 recognized pairs,
  all consecutive. Default/Subaru/Forester API responses200. These are LOCAL
  counts verified with the new source in Django's test client; no production
  audit or deployment was performed for this change. The already running
  localhost8000 process still returns the previous order and needs a backend
  restart before UI review. No frontend change/build is required.

SQL window numbering is applied AFTER requested filters and unique product-ID
selection, BEFORE pagination. Multiple matching fitments or image rows cannot
duplicate the product. Stability applies to unchanged matching data; publishing,
stock changes or new products can naturally move page boundaries.

Text/OEM/SKU searches retain existing relevance order, including an exact bolt
search. Explicit newest/oldest/name/price orders retain their existing rules.
Product eligibility, prices, stock, compatibility and facet counts are preserved.
No model/schema/data migration is required for this ordering change.

Verification:60 focused backend tests pass, including12 recommendation tests:
100-hood diversity, accessory exclusions, complete/unique/stable multi-page
results, make/model joins, image joins, filters/facets, exact search and explicit
ordering, adjacent pairs across pages, unchanged15-item pagination, complete
fitment/variant safeguards, ambiguity handling and stock/filter preservation.
Existing CKEditor/staticfiles warnings only. No new migrations detected.

Local browser verified default catalog, Subaru, Forester, page1->2->Back (15
unique links on each page, zero overlap, exact restored order), and390px mobile
layout without horizontal overflow. Local API examples returned1995/1231/465
matching rows; these are local catalog counts, not current production totals.
Measured three local requests roughly0.12–0.65 seconds; this isn't a production
performance measurement. Nuxt dev timing warnings are unrelated to API results.

Local review now works at the user's ordinary https://localhost:3000/catalog/,
using their localhost8000 backend. Initially an isolated frontend/backend used
an ignored copy of the existing local SQLite DB at
tmp/measurements-20261015/catalog-recommendations-20261116/preview.sqlite3.
The original local DB was still missing the prior price-review field, causing
catalog/wishlist500 on8000. After full SQLite backup, existing catalog0031/0032
prerequisites were also applied to the original local DB: all2037 original
product rows/columns and24 commerce tables hash-preserved. Actual8000 catalog,
wishlist and Forester requests now200; actual3000 browser renders15 products
with0 console errors/warnings. Temporary3001/8001 servers have been stopped.
Production DB was not changed. No real payment/email/
supplier operation was performed. Local process overrides were used; .env files
were not edited. The user owns later code push/build/deployment after review.
