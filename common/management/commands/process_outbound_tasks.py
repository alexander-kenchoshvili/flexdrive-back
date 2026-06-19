from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from commerce.meta_conversions import send_meta_purchase_event
from commerce.models import Order
from common.models import OutboundTask
from common.outbox import retry_delay


class Command(BaseCommand):
    help = "Process pending email and third-party outbound tasks."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        processed = 0
        for _ in range(max(options["limit"], 0)):
            task = self._claim_next_task()
            if task is None:
                break
            self._process(task)
            processed += 1
        self.stdout.write(f"Processed {processed} outbound task(s).")

    @transaction.atomic
    def _claim_next_task(self):
        task = (
            OutboundTask.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=[
                    OutboundTask.Status.PENDING,
                    OutboundTask.Status.FAILED,
                ],
                available_at__lte=timezone.now(),
                attempts__lt=F("max_attempts"),
            )
            .order_by("available_at", "id")
            .first()
        )
        if task is None:
            return None
        task.status = OutboundTask.Status.PROCESSING
        task.attempts += 1
        task.save(update_fields=["status", "attempts", "updated_at"])
        return task

    def _process(self, task):
        try:
            self._dispatch(task)
        except Exception as error:
            task.status = OutboundTask.Status.FAILED
            task.last_error = str(error)[:2000]
            task.available_at = timezone.now() + retry_delay(task.attempts)
            task.save(
                update_fields=[
                    "status",
                    "last_error",
                    "available_at",
                    "updated_at",
                ]
            )
            return

        task.status = OutboundTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.last_error = ""
        task.save(
            update_fields=["status", "completed_at", "last_error", "updated_at"]
        )

    def _dispatch(self, task):
        if task.task_type == "meta_purchase":
            order = Order.objects.prefetch_related("items").get(
                pk=task.payload["order_id"]
            )
            if not send_meta_purchase_event(order=order):
                raise RuntimeError("Meta Purchase event was not sent.")
            return
        raise ValueError(f"Unsupported outbound task type: {task.task_type}")
