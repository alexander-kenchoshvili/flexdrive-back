# Header search filters — 2026-10-16

## Synchronization and empty-result corrections — 2026-10-17

Latest refinement-choice follow-up: all context-relevant brand/placement/side
options remain visible at count0 under price/stock/sale/refinement restrictions.
The context includes the current public text/vehicle/category selection; actual
counts still honor the other filters. This extends the selected-only correction
below.111 focused backend tests pass; no frontend change or migration is required
for this additional improvement. Deploy backend for the new option lists.

Catalog-only brand/placement/side/price/stock/sale/sort/page URL changes no longer
overwrite unsubmitted header drafts. Submitting header search combines those
refinements with its current text/vehicle/categories and resets page; explicit
Header Clear removes all refinements on submission. Applied header-route changes
still synchronize normally. Mobile active-state detection includes plural categories.

Selected refinement facets now retain real labels and count0 even when the complete
result set is empty. Desktop/mobile dropdowns always include All, including when
there are no available alternatives, and numeric brand links retain their label.
Shared BaseSelect and design tokens remain unchanged in this follow-up.

64 focused frontend tests,107 backend tests, frontend typecheck/scoped ESLint pass.
Chrome localhost confirms both synchronization directions, zero-result recovery,
mobile selected/All options and category indicator, light/dark. Existing local
backend restarted through unchanged start.ps1; no business data/env/provider edits,
migration or push/deploy. Both paired repos need rollout, backend first/together.
Backups and screenshots: ignored local-docs/search/fixes-20261017/.

## Current category visibility and removed image filter

The user's latest follow-up restores the original category visibility: header and
catalog lists request the default category endpoint, hiding categories with zero
published products. The empty New category disappears. Stored categories and
category detail/SEO routes are unchanged; optional include_empty API compatibility
remains, but UI lists no longer enable it. This supersedes the original all-active,
including-empty category requirement below.

Removed the photo-only catalog filter from desktop/mobile controls, applied chips,
props/drafts/reset/apply state, route parsing/building, API request construction,
frontend types and analytics filter keys. Legacy has_image=true/false listing URLs
no longer constrain product requests; newly built pagination/filter URLs omit it.
Backend has_image API compatibility remains unchanged.

52 focused frontend tests passed, including nonempty category calls on header and
catalog initial/reload, legacy image-filter URLs and actual SSR pagination links.
App typecheck, scoped ESLint and whitespace pass. Existing Chrome confirms eight
nonempty header/catalog categories and Stock/Sale only in desktop/mobile quick
filters. Original viewport/dark restored; no filter or search submitted, business
DB/provider/env writes, backend code change, server start, push or deployment.
Screenshots: `artifacts/search/header-nonempty-categories.jpg` and
`artifacts/search/catalog-without-image-filter-mobile.jpg`.

## Current trial: compact until a dropdown opens

Follow-up responsive fix: the parent Header shows its mobile search button below
768px, but HeaderSearch previously hid its Dialog at640px. The dialog and internal
mobile/desktop visibility now all use md768px, with a matching max767px media query.
Chrome verified actual click opening at640px/767px, desktop input opening at768px
and mobile sheet closing when resizing through768px. No horizontal overflow.
27 focused frontend tests, app typecheck, scoped ESLint and whitespace pass.
Temporary viewport override reset; no search submitted. Screenshot:
`artifacts/search/header-search-767-fixed.jpg`.

User authorized trying a compact idle panel that expands for the first opened list,
keeps its size when switching fields, then returns to compact when all lists close.
Only HeaderSearchFilters scoped CSS changes: at1024px+ :has on the existing ARIA
expanded trigger applies the shared menu reservation. Closing waits120ms to bridge
pointer/focus handoff, then padding transitions180ms; reopening cancels that delay.
Overflow:clip contains menus during the reveal. Global reduced-motion rules apply.
No shared BaseSelect, filter logic, backend behavior or mobile layout change.

Existing Chrome localhost checked: panel195px idle,459px for category/make,
195px after Escape; category-to-make and reverse retain459px. Lists256px remain
inside the panel. Desktop light/dark and375x812 mobile checked without horizontal
overflow. Original viewport and dark theme restored, no search submitted.27 focused
search/select/catalog tests and scoped ESLint/whitespace pass. No server start,
business DB/provider/env edits, push or deployment. No type changes in this CSS trial.

Screenshots: `artifacts/search/header-compact-idle.jpg` and
`artifacts/search/header-compact-expanded.jpg`. Previous component preserved in
`local-docs/search/header-search-reserved-space-20261016.vue` for easy local rollback.

## Always-reserved menu space - historical

The user requested the overlay behavior again, with enough space reserved inside
its search panel for the entire opened list. Four desktop fields remain in one row.
Only HeaderSearchFilters scoped CSS changes: at1024px+ lists are absolute within
existing select wrappers, and grid bottom padding reserves the matching menu height
plus its8px gap. A shared CSS variable caps both reservation and list at160-256px
based on viewport height. No fixed positioning, portal or shared BaseSelect change.
Below1024px the existing two/one-column inline layout and mobile Dialog scrolling
remain, avoiding an empty menu area after every mobile field.

Verified in the existing Chrome localhost: at1905x967 the panel stays459px closed,
category-open and make-open, with all triggers at134px. Lists are256px and end at
444px inside the panel ending544px. At1280x600 the list is248px and contained;
outer panel scrolling remains available. At375x812 the inline category list fits
its single column without horizontal overflow. Desktop light/dark visually checked.
Original viewport and dark theme restored, no search submitted.27 focused frontend
tests, app typecheck, scoped ESLint and whitespace pass. No backend behavior change,
server start, business DB/provider/env edits, push or deployment.

Reserved-space screenshot: `artifacts/search/header-contained-dropdowns.jpg`.

## Four-column rollback layout - historical

The floating dropdown trial below was reverted at the user's request. Its four
backed-up files were restored and the trial-only selectOverlayLayout.ts removed,
preserving the earlier search/filter implementation. All four header selects now
use the previous inline expanding behavior. Categories moved into the same grid as
make/model/year: four columns at1024px+, two at640px+, one on narrow mobile. Category
multiple selection/removal and the absence of internal search inputs remain.
Verified in the existing Chrome localhost: desktop four controls share the same
top134px; category/make switching retains the expanded panel height459px. At900px
the grid has two columns; at375px one column; neither introduced horizontal scroll.
Original viewport restored.27 focused tests and scoped ESLint/whitespace pass.
Rollback screenshot: `artifacts/search/header-four-dropdowns.jpg`.

## Floating dropdown trial — historical, reverted

The user requested trying anchored overlay lists in all four HEADER selects to
remove form expansion and the close/reopen jump. These selects now opt into
BaseSelect `floatingOptions`; existing scalar/search/multiple/inline defaults and
other select instances stay unchanged. Lists use fixed viewport coordinates, keep
the trigger width, cap their scrolling height at 256px and open above when space
below is insufficient. Position updates follow scroll/resize/visual viewport and
element resizing, with listeners disconnected when lists close. The header panel
transition now fades without a transform so fixed positioning stays viewport-based.

Verified in the user's existing Chrome localhost tab through browser access:
desktop dark/light, 375x812 dark/light and 375x667 dark. Category-to-make switching
retained panel top85px/height285px in both states; the mobile list stayed inside
the viewport and opened above on the shorter viewport. Multiple selection, undoing
only the test selections and Escape closing worked. Original desktop size, dark
theme and BMW/5 Series/2021 desktop draft restored; no catalog search submitted.
31 focused frontend tests and typecheck passed; this is a local UI trial, not a
production deployment. The previous browser-pending note below predates this trial.
Screenshot: `artifacts/search/header-dropdown-overlay-trial.jpg`.

The four pre-trial files are backed up outside the repo in the user's temporary
directory `flexdrive-header-overlay-20261016`, preserving all earlier search work:
BaseSelect.vue, HeaderSearchFilters.vue, HeaderSearch.vue and baseSelect.test.mjs.
To undo this trial, restore only those files and remove the trial-only
`app/utils/selectOverlayLayout.ts`; do not revert the whole uncommitted search task.

The paired frontend header now opens a compact filter form in place of the quick
search explanation, recent searches and popular-category navigation cards.

## Interaction

- Text accepts the existing product name/OEM/company SKU search. No search parsing,
  identifier ranking or stored product content was changed.
- Vehicle controls are make, model and year only. Changing make clears model/year;
  changing model clears year. Year can also be selected with make alone, using the
  existing API contract. There is no engine control in the header.
- Header make/model/year dropdowns also omit their internal search inputs per user
  follow-up. The reusable BaseSelect searchable capability remains available elsewhere.
- Original requirement (superseded above): all active categories, including empty categories, were available in the shared
  BaseSelect, without an extra category-search input (user follow-up). Multiple
  selections mean products in any selected category.
  Selected categories have individual removal buttons.
- Edits and clearing are drafts. Search/Enter applies text and selected filters
  together to `/catalog`; typing or selecting a category does not navigate.
  An empty form opens the whole catalog; one-character text cannot submit.
- Suggestions still appear for text of at least two characters and use the same
  selected category/vehicle constraints. Queued/stale results cannot overwrite a
  newer query, filter choice, closed panel or unmounted component.
- Catalog requests, pagination, sort, active-category label and mobile filter apply
  retain the plural category selection. Reset removes it.
- Search history is no longer recorded. Old header history is removed when mounted;
  blocked browser storage cannot prevent the search from initializing.

## Additive API changes

- `GET /api/catalog/products/?categories=lights,mirrors`
- `GET /api/catalog/products/suggestions/?q=part&categories=lights,mirrors&make=subaru&model=forester&year=2018`
- `GET /api/catalog/categories/?include_empty=true`

`categories` accepts 1–100 IDs/slugs, comma separated or repeated. Unknown/inactive
values, empty tokens, oversized values and invalid IDs return 400. Selections are
ORed within the category group, then intersected with text/vehicle/other filters.
The existing `category` parameter retains its behavior; if supplied together, it
also constrains the plural selection. The category-list default still excludes
empty categories. Suggestions retain their five-product limit and public visibility.

## UI implementation and verification limits

The existing BaseSelect gains opt-in multiple selection and inline options without
changing existing scalar v-model events. Inline options remain within scrollable
panels. The header uses the existing BaseButton, BasePicture and design tokens,
one shared filter component on desktop/mobile, and the installed Headless UI Dialog
for mobile focus/scroll management. Dropdown text input keeps typing separate from
listbox keyboard selection. Headless UI's documented `multiple`/array selection
and Dialog behavior were checked through Context7.

Responsive styles use three columns from 640px and one column below, bounded
desktop panel height, a scrollable 100dvh mobile dialog and safe-area padding.
Light/dark colors derive from existing tokens. Browser/Playwright verification was
not run because project instructions require an explicit browser-check request.
Visual checks at 375px/640px/1440px in both themes remain for user review, including
keyboard/touch dropdown use, long category names, mobile keyboard and short screens.

## Validation and rollout

- 78 focused backend tests passed on disposable SQLite: header filters, existing
  search/OEM whitespace/vehicle parsing, search performance and internal SKU tests.
- 40 frontend search/filter/shared-select/analytics tests passed. Expanded checks
  passed 57 of 59 tests, including title/consent/catalog error checks. Two unrelated
  product SEO tests fail because the older test harness lacks a gallery-preloader
  mock; the same two failures were reproduced against committed HEAD source.
- Final Nuxt production build and typecheck passed. Scoped ESLint, Python
  compilation, migration drift and whitespace checks passed.
- No model/schema migration, real catalog/DB edits, supplier/provider requests,
  environment changes, browser/server start, push or deployment.

Deploy the backend changes before or with the paired frontend. Both repositories
need push/deployment by the user; no migration is required. Production PostgreSQL
and deployed/browser behavior have not been verified in this task.
