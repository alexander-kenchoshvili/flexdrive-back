# Individual product pricing

Pricing is controlled per product. Category markup no longer affects calculations
or appears in the category/product admin. The legacy category database column is
retained for compatibility; there is no bulk pricing action.

The product admin accepts either the customer price in GEL or a markup percentage.
Editing either field updates the other. Saving an entered amount derives and stores
an individual percentage; it does not freeze the customer price.

Example: supplier 100 GEL, customer price 120 GEL -> 20% markup.
A later supplier import at 110 GEL produces a customer price of 132 GEL.
An empty individual markup means 0%, not category inheritance. New products default
to 0%; Cross Motors imports continue creating Draft products. Products without a
supplier price retain ordinary manual price entry. No pricing-pending UI is added.

Calculations are repeated server-side. Existing 0–1000% markup limits remain:
amount entry below supplier cost is rejected, and a positive amount cannot derive
a percentage from a zero supplier price. Public API price fields remain unchanged.

## Rollout

- `catalog.0025_precise_product_markup` increases individual percentage precision
  to 10 decimal places, preserving entered amounts to the cent on save.
- `catalog.0026_individual_product_pricing` sets the default to zero and performs
  the user-authorized one-time reset of ALL existing product markups to 0%. It
  resets supplier-backed customer prices to supplier prices; manual product prices
  remain unchanged. It does not touch orders, their price snapshots or statuses.
- Take a pricing snapshot before 0026 on each environment. It deliberately has no
  automatic reverse because prior pricing cannot be reconstructed. Apply this
  cutover BEFORE entering the final individual prices in that environment.
- The migration refuses existing old_price values at/below supplier_price, requiring
  review instead of silently clearing discount information.
- Apply migrations together with backend deployment and collect/deploy the updated
  admin static asset. No frontend response-shape change is needed.

Local 2026-09-28 verification: 2,037 products assigned 0%; all actual prices were
already equal to supplier prices, so their numeric prices stayed unchanged.
Hashes verified every other product field and all 26 other catalog/commerce tables
unchanged. Staging and production were not modified.

## Verification

Use the repository virtual environment for Django commands:

- `python manage.py test catalog.test_admin_pricing catalog.test_supplier_sync catalog.test_sku_allocation --noinput`
- `node --test catalog/test_admin_pricing_preview.cjs`

Additional sheet-import pricing tests cover individual markup and category
independence. Tests verify public numeric prices before/after an admin edit,
normal/bulk supplier imports, exact cent rounding, form rendering, validation and
cutover preservation. PostgreSQL-only SKU concurrency is skipped on SQLite.

Admin percentage display uses two decimal places (including the editable field).
Stored percentages retain ten decimal places. Merely saving a rounded display or
editing supplier cost preserves the original precise rate; explicitly editing the
percentage uses the entered rate. Amount entry derives the precise rate server-side.
Display-only follow-up verified by 21 Django pricing tests and 8 JavaScript tests.
