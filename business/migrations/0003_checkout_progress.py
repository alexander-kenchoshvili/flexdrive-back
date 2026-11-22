from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("business", "0002_vehicle_interest")]

    operations = [
        migrations.CreateModel(
            name="CheckoutProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("basket_key", models.CharField(max_length=64)),
                ("event_key", models.CharField(max_length=64, unique=True)),
                ("source", models.CharField(max_length=8)),
                ("stage", models.CharField(max_length=24)),
                ("items", models.JSONField()),
                ("delivery_amount", models.DecimalField(decimal_places=2, max_digits=12, null=True)),
                ("delivery_service", models.CharField(blank=True, max_length=8)),
            ],
        ),
    ]
