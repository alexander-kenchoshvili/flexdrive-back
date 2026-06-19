from django.test import TestCase

from .models import OutboundTask


class OutboundTaskTests(TestCase):
    def test_unique_key_prevents_duplicate_tasks(self):
        task = OutboundTask.objects.create(
            task_type="meta_purchase",
            payload={"order_id": 1},
            unique_key="meta-purchase:1",
        )

        self.assertEqual(task.status, OutboundTask.Status.PENDING)
