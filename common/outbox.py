from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import OutboundTask


def enqueue_outbound_task(*, task_type, payload, unique_key=None):
    def create_task():
        if unique_key:
            OutboundTask.objects.get_or_create(
                unique_key=unique_key,
                defaults={"task_type": task_type, "payload": payload},
            )
            return
        OutboundTask.objects.create(task_type=task_type, payload=payload)

    transaction.on_commit(create_task)


def retry_delay(attempts):
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 60))
