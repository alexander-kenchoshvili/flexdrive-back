from django.db import models
from django.utils import timezone


class OutboundTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    task_type = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict)
    unique_key = models.CharField(max_length=160, blank=True, null=True, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("available_at", "id")
        indexes = [
            models.Index(
                fields=["status", "available_at"],
                name="common_outb_status_308ad9_idx",
            )
        ]
