"""Bounded, private summaries; deleting a report never affects an order."""

from django.utils import timezone

from .models import EasywaySyncReport


DETAIL_LIMIT = 50


class TrackingReport:
    def __init__(self, *, source):
        self.source = source
        self.started_at = timezone.now()
        self.counts = dict(checked=0, changed=0, review=0, failed=0, skipped=0)
        self.items = []
        self.run_error = ""

    def record(self, result, detail=None):
        if result == "skipped":
            self.counts["skipped"] += 1
            return
        self.counts["checked"] += 1
        if result in {"review", "failed"}:
            self.counts[result] += 1
        changed = detail and (
            detail.get("carrier_before") != detail.get("carrier_after")
            or detail.get("order_before") != detail.get("order_after")
        )
        if changed:
            self.counts["changed"] += 1
        if (changed or result in {"review", "failed"}) and len(self.items) < DETAIL_LIMIT:
            self.items.append({**(detail or {}), "result": result})

    def save(self):
        counts = self.counts
        if not (counts["changed"] or counts["review"] or counts["failed"] or self.run_error):
            return None
        status = (
            EasywaySyncReport.Status.FAILED if counts["failed"] or self.run_error
            else EasywaySyncReport.Status.REVIEW if counts["review"]
            else EasywaySyncReport.Status.SUCCESS
        )
        summary = (
            f"შემოწმდა: {counts['checked']}; შეიცვალა: {counts['changed']}; "
            f"ყურადღებას საჭიროებს: {counts['review']}; შეცდომა: {counts['failed']}."
        )
        return EasywaySyncReport.objects.create(
            started_at=self.started_at, finished_at=timezone.now(), source=self.source,
            status=status, summary=summary,
            details={"counts": counts, "items": self.items, "run_error": self.run_error},
        )
