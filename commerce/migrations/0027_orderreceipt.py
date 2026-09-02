import django.db.models.deletion
import django.utils.timezone
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0026_supplierstockhold"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderReceipt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "public_token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("template_version", models.CharField(max_length=32)),
                ("document_snapshot", models.JSONField(default=dict)),
                ("content_hash", models.CharField(db_index=True, max_length=64)),
                (
                    "issued_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                    ),
                ),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="receipt",
                        to="commerce.order",
                    ),
                ),
            ],
            options={
                "ordering": ("-issued_at", "-id"),
            },
        ),
    ]
