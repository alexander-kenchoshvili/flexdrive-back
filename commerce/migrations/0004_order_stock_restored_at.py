from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0003_alter_order_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="stock_restored_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
