from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0009_order_checkout_source_buynowsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("authorized", "Authorized"),
                    ("paid", "Paid"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                    ("refund_pending", "Refund pending"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["payment_status", "created_at"],
                name="commerce_or_payment_7463c0_idx",
            ),
        ),
    ]
