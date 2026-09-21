# Cross Motors scheduled sync on DigitalOcean App Platform

Prepared locally; this document does not create a paid resource or enable a schedule.

Verification on 2026-09-22: 52 tests passed across `catalog.test_crossmotors_import`,
`catalog.test_supplier_sync`, and `commerce.test_supplier_stock_holds`; migration
0020 applied locally. A real supplier dry run returned pages 1000/1000/30, 2030 valid
rows, 0 validation errors, and 7 local Published products to archive. There were 189
existing category-inference warnings; existing product categories remain preserved.
No committed supplier refresh was run. PostgreSQL advisory-lock behavior is mocked
in unit tests; the production database/job still needs the deployment verification below.

## Product rules

- New SKU: created as **Draft** in the existing `ახალი` category.
- Draft: remains Draft on every refresh, including disappearance/reappearance.
- Published: supplier price and stock update using the existing markup and sale-hold rules.
- `--archive-missing`: a Published CM product absent from the complete feed becomes Archived,
  with `supplier_missing=True`. Zero stock alone does not archive a product.
- A returning automatically archived product becomes Published and clears that marker.
- Manual/legacy Archived products remain Archived. Existing archived rows are deliberately
  not assumed to have been approved for automatic return.
- Supplier product blocks are still skipped. The admin block action also clears the
  automatic-return marker. Use this action to exclude an unwanted SKU permanently.
- Admin status changes and publish/draft actions clear the automatic-return marker.

To prepare a new product: Catalog → Products → Status: Draft; edit its category,
markup/price settings and images, then use **Publish selected products**.
Supplier-priced products continue to use category markup or the per-product markup
override; the importer does not introduce a new fixed-price override.
The read-only **Supplier missing** field/filter identifies automatic archiving.

## Deploy and verify before enabling a schedule

1. Deploy this backend revision. Apply migrations through `catalog.0021_supplier_sync_report`
   through the existing deployment migration step before running the new importer:
   `python manage.py migrate --noinput`.
2. Use the backend App Platform console for a dry run against the intended database:

   ```sh
   python manage.py import_crossmotors_products --page-size 1000 --sample-size 0 --bulk --archive-missing
   ```

3. Review page sizes, validation failures, new/existing counts and
   `Published products to archive as missing`. Then run once with `--commit`:

   ```sh
   python manage.py import_crossmotors_products --page-size 1000 --sample-size 0 --bulk --archive-missing --commit
   ```

4. Check Products in admin: new rows are Draft, known live products remain Published,
   missing ones are Archived with Supplier missing enabled. Confirm customer-visible
   prices/stock and images. Run again to confirm Draft rows stay hidden.

These Linux commands use the App Platform runtime. Locally use
`.\venv\Scripts\python.exe manage.py ...`.
The migration does not hide existing Published products or publish old drafts.

## Add the scheduled job after verification

In **Apps → backend app → Add components → Create resources from source code**:

- Use the same backend repository, deployment branch, source directory and runtime/build
  setup as the web component; choose resource type **Job**.
- Name: `crossmotors-sync`.
- Run command: the temporary alternate-day wrapper below (not the web server command).
- Job trigger: **On a schedule**.
- Temporary pre-launch cron expression: `0 0 * * *`, time zone `UTC`.
  The small wrapper starts daily at 04:00 Tbilisi time but runs the importer only
  on alternate UTC dates (every 48 hours). Other days exit without fetching or writing.
  This avoids the month-boundary irregularity of `*/2` in the day-of-month field.
- At launch, replace the wrapper with the direct committed bulk command above and
  change the cron expression to `0 */2 * * *` (every two hours).
- Use one job instance. Choose the resource size after observing the manual run's
  duration/memory; review DigitalOcean's cost display before creating it.
- Make the backend's required runtime environment available to this component, including
  the same production database, supplier API token, cache connection and cache prefix.
  Component-scoped web environment variables are not automatically job-scoped.
  Reuse secret bindings in DigitalOcean; never paste credentials into Git or logs.
- Permit the new component to reach the managed database and Valkey using the same
  trusted-source/network configuration as the backend.
- Inspect **Activity → Jobs** and job logs for successful executions and reported counts.
  A nonzero exit is a failed sync and should be inspected, not treated as a refreshed catalog.

Temporary run command (parity is anchored to the calendar, not to deployment time):

```sh
python -c "from datetime import datetime, timezone; import subprocess, sys; due = datetime.now(timezone.utc).date().toordinal() % 2 == 0; print('Supplier sync due' if due else 'Supplier sync skipped: alternate-day schedule', flush=True); sys.exit(subprocess.call([sys.executable, 'manage.py', 'import_crossmotors_products', '--page-size', '1000', '--sample-size', '0', '--bulk', '--archive-missing', '--commit']) if due else 0)"
```

App-spec schedule fragment (merge into the existing app; not a standalone deploy file):

```yaml
jobs:
  - name: crossmotors-sync
    kind: SCHEDULED
    schedule:
      cron: "0 0 * * *"
      time_zone: UTC
    run_command: >-
      python -c "from datetime import datetime, timezone; import subprocess, sys; due = datetime.now(timezone.utc).date().toordinal() % 2 == 0; print('Supplier sync due' if due else 'Supplier sync skipped: alternate-day schedule', flush=True); sys.exit(subprocess.call([sys.executable, 'manage.py', 'import_crossmotors_products', '--page-size', '1000', '--sample-size', '0', '--bulk', '--archive-missing', '--commit']) if due else 0)"
    # Copy the backend source/build/runtime and required env bindings here.
```

DigitalOcean bills scheduled jobs for running time, not idle intervals. Setup, schedule
syntax and billing are documented in
[Manage Cron Jobs and Deployment Jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/)
(checked 2026-09-22).

## Failure protections and limitations

- The command acquires a PostgreSQL transaction advisory lock before fetching the feed;
  overlapping command runs fail before fetching/writing. The lock is released at transaction
  end or connection loss and works with transaction pooling. Local SQLite uses a file lock.
  Production should invoke this management command, not call the importer functions directly.
- Pagination/request failures, changing supplier snapshot timestamps, duplicate SKUs,
  validation errors, and empty/no-importable feeds stop the archive-enabled run before writes.
- The full import is transactional. Failed imports do not release stock holds from stale data.
- By default, if more than **20%** of currently Published CM products would disappear,
  the entire run stops. This is a conservative operational threshold, not a supplier guarantee.
  Only after verifying a real large supplier change, use a manually reviewed dry run and
  one-off commit with `--max-missing-percent N` (0–100). Do not raise it in the scheduled job
  merely to suppress failures.
- The supplier API's short-page pagination contract is still relied upon. An apparently
  successful but silently incomplete feed below the threshold cannot be conclusively
  detected without an authoritative supplier total/snapshot guarantee. Review the first
  production dry run and any unexpected archive counts.
- Successful imports invalidate catalog category and vehicle-search caches, including
  bulk updates. The job must use the same Valkey/cache namespace as the web process.

No payment reconciliation or payment alerts are added by this supplier job.

## Admin reports and cleanup

Each committed management-command run stores a report in
**Catalog → სინქრონიზაციის ანგარიშები**. Dry runs and alternate-day skips create no report.
The list shows start/end time, success/failure and a compact summary. Open a report
for new Draft products, sellable-stock exhaustion/return, archiving/restoration and
supplier-price changes. Ordinary stock quantity changes are not listed. Each group
stores the full count and up to 50 product names/SKUs; price changes include old/new costs.
These are private staff reports, never customer API data.

Use date/status filters, tick individual rows or the header checkbox, select
**Delete selected**, and confirm. Django's **Select all ...** link selects all matching
reports across pages; the header checkbox alone selects the current page. A report
can also be deleted from its detail page. Report deletion never deletes products or
changes synchronization behavior. There is no automatic retention/deletion schedule.

Success reports commit with the import; rollback saves a separate failure report.
Failure summaries contain the failed phase, not raw exception text, credentials or feed
payloads; consult the job logs for diagnosis. If the database is unavailable or the
process is forcibly terminated, saving a report is not guaranteed, so job activity/logs
remain the source for such execution failures.
