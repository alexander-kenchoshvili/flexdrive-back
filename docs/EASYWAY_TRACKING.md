# EasyWay delivery tracking

Prepared on 2026-09-22. Backend implementation and local migration are ready;
production deployment and scheduled job activation are separate steps.
No customer UI, public API fields, refunds or cancellation workflow was added.

## Mapping

| Carrier status | FlexDrive order action |
| --- | --- |
| new | Preserve current order status |
| taking | Advance to processing |
| taken, in_store, taken_store | Advance to shipped |
| delivered | Advance to delivered |
| canceled | Store carrier cancellation only; no refund, stock or order cancellation |

The mapping uses the provider's supplied status list and the observed test response
from `GET /order/tracking/{order_id}?lang=en`: a list of `status` / `created_at`
events with timezone-qualified timestamps. No assumption about array ordering is made.
Only paid, non-cancelled orders advance. Intermediate steps may be missed between
polls, so a delivered response can advance directly from an earlier order step.
Order progress never moves backwards. New/confirmed remain operator-managed.
The existing frontend reads the unchanged order `status` field when fetching orders.
An already open customer page is not given live polling or push notifications.

## Admin and error handling

Order admin has **Refresh EasyWay tracking** with POST/CSRF and change permission.
It displays the latest carrier state, event time, last successful read, last attempt,
error/review message and history (up to the newest 1000 distinct events).
Extra response fields are discarded; only status/time are retained.

Malformed/empty responses and HTTP failures preserve the last successful state.
Unknown codes and conflicting same-time events require review rather than guessed
mapping. Later contradictory terminal events are retained in history without
overwriting the accepted terminal state. A cancelled/refunding local order is not
reactivated. Carrier cancellation does not change `easyway_shipment_state`; that
field continues to describe the existing submission/cancellation action workflow.
Review flags are visible in admin and scheduled runs exit nonzero for attention.
No external operator notifications are configured.

Each refresh claims an atomic five-minute database lease. No network request runs
under a row lock. Results recheck the lease, carrier ID, payment and order state
inside a short transaction. An expired worker cannot overwrite a newer worker.
Use request timeouts shorter than the lease (the existing default timeouts qualify).

## Command

```sh
python manage.py sync_easyway_tracking --dry-run
python manage.py sync_easyway_tracking --limit 100 --min-age-minutes 10 --max-seconds 600
```

Only regional EasyWay orders with a carrier ID are eligible. Carrier-terminal
tracking states and locally cancelled/cancelling shipments are excluded from cron;
manual refresh remains available for investigation. A locally cancelled *order*
with a still-active carrier shipment remains eligible so the discrepancy is visible.

No eligible orders means no API calls and no tracking writes. The scheduler itself
still starts. Dry-run does not call the carrier or write. Older/unattempted shipments
go first. Each run handles at most 100 shipments and starts no further request after
600 seconds; one in-progress request may finish after that budget. Increase the batch
only after checking carrier request limits and observed duration/backlog.

The 10-minute minimum age is a duplicate-attempt guard, not the schedule. Before
launch the sync runs every 10 days. At launch the cron changes to every 15 minutes;
the shorter guard avoids accidentally skipping every second run because of startup
jitter. Each request, successful or failed, is throttled.
Expected carrier errors do not prevent processing other orders. Database failures
abort the run. Process termination is recoverable after lease expiry.

## DigitalOcean App Platform activation

1. Deploy the backend changes and apply `python manage.py migrate --noinput`,
   including `commerce.0029_easyway_tracking`, before any scheduled execution.
2. In the production backend console run the dry-run above; review eligible test
   shipments before enabling the job. Use the admin refresh on a known test shipment.
3. Add a **Job** component from the same backend source/branch/runtime.
   Name: `easyway-tracking`. Trigger: **On a schedule**.
   Before launch: use the ten-day wrapper below with `0 0 * * *`, time zone `UTC`,
   one instance. The daily trigger only checks the date; the Django command runs
   once every 10 days. Other dates exit before loading Django or querying the DB/API.
   At public launch: replace the wrapper with
   `python manage.py sync_easyway_tracking --limit 100 --min-age-minutes 10 --max-seconds 600`
   and change the schedule to `*/15 * * * *`.
4. Reuse the backend's production runtime environment and secret bindings, including
   `DATABASE_URL`, required Django deployment settings, `EASYWAY_API_USER`,
   `EASYWAY_API_KEY`, `EASYWAY_API_BASE_URL` and HTTP timeouts. Web-component-only
   variables are not automatically available to the job. Use the production EasyWay
   account. Never commit secrets. Permit the job's database/network access; confirm
   any carrier IP allowlist applies to the job's outbound traffic too.
5. Review the cost shown by DigitalOcean with the owner before creating the component.
   Confirm the polling/request limits with EasyWay before activation.
6. Inspect **Activity -> Jobs** for the first two runs and exit statuses. With no
   eligible shipments the expected output is `synced=0 review=0 skipped=0 failed=0`.
   With a test shipment, confirm admin state/time and the existing customer order status.

Pre-launch run command, anchored to 2026-09-22 (first due dates: October 2 and 12,
at 00:00 UTC / 04:00 Tbilisi). This is a planned schedule, not an activated job.
Do not use `*/10` in the day-of-month field: that resets at each month boundary
and does not mean a consistent ten-day interval. Missed scheduled dates are not
automatically caught up; an operator can run the direct command if needed.

```sh
python -c "from datetime import date, datetime, timezone; import subprocess, sys; days = (datetime.now(timezone.utc).date() - date(2026, 9, 22)).days; due = days > 0 and days % 10 == 0; print('EasyWay tracking due' if due else 'EasyWay tracking skipped: pre-launch ten-day schedule', flush=True); sys.exit(subprocess.call([sys.executable, 'manage.py', 'sync_easyway_tracking', '--limit', '100', '--min-age-minutes', '10', '--max-seconds', '600']) if due else 0)"
```

Pre-launch merge fragment (not a complete app spec; retain existing source/build/env):

```yaml
jobs:
  - name: easyway-tracking
    kind: SCHEDULED
    schedule:
      cron: "0 0 * * *"
      time_zone: UTC
    run_command: >-
      python -c "from datetime import date, datetime, timezone; import subprocess, sys; days = (datetime.now(timezone.utc).date() - date(2026, 9, 22)).days; due = days > 0 and days % 10 == 0; print('EasyWay tracking due' if due else 'EasyWay tracking skipped: pre-launch ten-day schedule', flush=True); sys.exit(subprocess.call([sys.executable, 'manage.py', 'sync_easyway_tracking', '--limit', '100', '--min-age-minutes', '10', '--max-seconds', '600']) if due else 0)"
```

DigitalOcean's minimum schedule interval is 15 minutes. Scheduled jobs are billed
for runtime, including startup/empty checks, not idle time. This is not a promise of
free execution. See [DigitalOcean job documentation](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/)
(checked 2026-09-22). Do not add a public HTTP endpoint or a loop inside Gunicorn.

## Verification and remaining limits

Tests cover the observed cancelled response, complete mapped cycle, missed steps,
stale/duplicate/malformed/unknown histories, terminal conflicts, refund/cancellation
protection, expired/replaced leases, overlapping requests on separate DB connections,
admin permissions/CSRF, public serializer compatibility, empty/dry-run batches and
continuation after carrier failure. HTTP failures/status variations use controlled
responses because real delivery transitions cannot be triggered locally.

The real cancelled test shipment was successfully read with the new client/parser.
71 tests passed across tracking, EasyWay client/shipments, BOG refunds and supplier
stock holds. Migration consistency check passed, local migration 0029 was applied,
and local dry-run found zero eligible shipments. Frontend files were unchanged.
Actual pickup/delivery transitions, production PostgreSQL concurrency and deployed
job execution still require deployment verification. Do not describe them as tested.
The project has an existing CKEditor support/security warning unrelated to tracking.
Existing refund tests also report a missing local collected-static directory; the
new tracking admin tests use an isolated static storage fixture.
