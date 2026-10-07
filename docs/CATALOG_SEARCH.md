# Catalog search audit and regression checks

Updated 2026-10-07. Changes are local; the user-started localhost site has been
browser-verified. Production deployment and PostgreSQL runtime verification remain.
No schema or catalog data change is needed.

## Behavior

- Every meaningful product word is required, in any order. Whitespace, surrounding
  punctuation, brackets, slash separators, copied zero-width characters and Georgian
  uppercase input are normalized. Hyphens/dots/underscores inside identifiers remain.
- Georgian and Latin keyboard spelling are supported per word. Ambiguous Latin
  letters use bounded character-class patterns, so long words no longer lose their
  correct Georgian variant at the old eight-variant cutoff.
- Side/placement words can match the saved field or recognized whole-word aliases
  in the name. `LH` is not a substring match inside `wheelhouse`. Numeric name terms
  do not confuse `Product 0` with `Product 10`; numeric identifier prefixes still work.
- Vehicle matches use all matching prefix candidates, resolve shared model names
  within the identified make, and normalize model punctuation (`CX-5` / `CX5`).
  A literal name match survives a word that also happens to be a vehicle prefix.
  Explicit category/vehicle/price/status filters still constrain these results.
- A single unambiguous standalone year (1900-2100) with an identified vehicle
  matches the inclusive saved fitment year range, not descriptions. Vehicle parsing
  runs first so model numbers such as Peugeot 2008 are preserved. Numeric-only
  searches without vehicle context still search names/IDs. Year and engine must
  match the same fitment; universal products retain their existing behavior.
  With a year constraint, literal name fallback also respects compatibility.
  Multiple distinct years are retained as text; this change does not infer ranges.
- Georgian vehicle spellings with a trailing ი (`ფორესტერი`) also resolve to the
  Latin model name. Product word matching is not broadened by that model rule.
- Company SKU and manufacturer part numbers remain searchable even when they
  coincide with a vehicle/attribute term. Standard `FD-03-0001` codes also work as
  `fd030001` or `fd 03 0001`. Supplier SKUs remain private.
- Exact identifier/name matches precede partial matches and stock preference in
  search results. Default listings retain their existing stock ordering.
- Suggestions remain limited to five, with name/code/fitment search. Catalog
  listing search additionally checks descriptions, as before. No response fields change.
- Blank/one-character suggestion queries return an empty list. Catalog one-character
  queries and either endpoint's queries above 255 characters return a validation error.
  The length bound now accommodates the entire `Product.name` field (previously 100).
- The paired frontend invalidates pending results on input changes, clearing,
  panel closure and unmount. Obsolete queued requests do not execute, and stale
  responses/errors cannot overwrite the latest query. Mobile opening explicitly
  fetches an existing query, including unchanged text after closing/reopening.

## Entire-catalog audit

Run from the backend repository with its virtual environment. The command permits
only local SQLite and reads published products in active categories. It does not
change products, fitments, users or schema, and does not contact suppliers/banks.
Environment assignments below apply only to the shell process, not `.env` files.

```powershell
$env:DATABASE_URL='sqlite:///db.sqlite3'
$env:CACHE_ENABLED='false'
.\venv\Scripts\python.exe manage.py audit_catalog_search --fail-on-missing --output local-docs/search-audit.json
```

`--limit 100` allows a diagnostic subset. `--fail-on-missing` exits unsuccessfully
if any expected product is missing, after writing the detailed JSON report.
Reports contain public product names/IDs and query diagnostics, not credentials.
Queries outside the supported length are reported separately as skipped checks.

The audit checks candidate membership using the same search helper used by both
APIs. It verifies each product can be found, including every product sharing a
name; it does not require every duplicate to appear in a five-item dropdown.
API regression tests separately check ranking, visibility, validation, side
isolation, vehicle constraints, duplicate fitments and bounded query counts.

On the local 2,037-product snapshot, with 1,947 nonempty manufacturer part numbers:

| Check | Product checks | Missing before broad fix | Missing after |
| --- | ---: | ---: | ---: |
| Full saved name | 2,037 | 47 | 0 |
| Extra whitespace | 2,037 | 336 | 0 |
| Punctuation removed | 2,037 | 213 | 0 |
| Reversed word order | 2,037 | 1,299 | 0 |
| Latin keyboard spelling | 2,037 | 158 | 0 |
| Company SKU, lowercase | 2,037 | 0 | 0 |
| Company SKU without separators | 2,037 | Not in initial audit | 0 |
| Vehicle before name | 2,037 | 65 | 0 |
| Vehicle after name | 2,037 | 65 | 0 |
| Saved manufacturer part number | 1,947 | 0 | 0 |

Initial broad fix: 20,280 product checks across 12,117 distinct queries. Baseline includes
the initial mirror-name fix; counts describe failed checks, not distinct defects.
This is local evidence, not a claim that every possible future query is covered.

The year follow-up checks every fitment and adds these suites:

| Check | Product checks | Missing after |
| --- | ---: | ---: |
| Vehicle + starting year + name | 2,037 | 0 |
| Name + vehicle + starting year | 2,037 | 0 |
| Vehicle + ending year + name, when different | 737 | 0 |

Latest total: **25,091 checks / 16,316 distinct queries**, zero failures and no
length skips. An independent read-only comparison of 216 make/model/year queries
against the saved fitment snapshot (range endpoints, midpoint and outside years)
found no missing or extra products.

## Local browser verification

Verified the user-started `https://localhost:3000` with the updated code:

- `Subaru Forester სარკის ქვედა`: four covers; adding `2019`: only the two 2019
  covers. Adding the full name and `LH`: one correct cover in dropdown and catalog.
- `2018`: only two covers for the 2012-2018 range; `2020`: no covers.
- Original full `სარკის ქვედა ხუფი (LH)`: five covers, no RH products.
- Mobile 375px: opening with an applied query, closing/reopening unchanged text,
  rapid replacement, reordered Latin query, compact SKU `fd020010`, and clearing
  an applied query all work. Desktop search/submission also verified; viewport reset.

The deployed site's mobile close/reopen also worked when checked earlier. The
mobile reload correction prevents a regression in the unshipped local changes;
it is not a claim that the deployed close/reopen flow was broken.

62 backend and 15 frontend regression tests plus frontend typecheck pass. Stock
fixtures exceed the five-unit reserve so stock-sensitive ranking is exercised.

## Regression commands

```powershell
.\venv\Scripts\python.exe manage.py test catalog.test_search catalog.tests.CatalogSearchPerformanceTests catalog.test_internal_skus --noinput
```

In `C:\Users\kench\Desktop\flexdrivefront`:

```powershell
node --test tests/headerSearch.test.mjs
npm run typecheck
```

Before release, deploy both repositories and verify the protected deployed site
against production PostgreSQL, including search results and response times.
The local SQLite audit does not substitute for that verification.
