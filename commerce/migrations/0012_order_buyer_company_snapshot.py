from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0011_stockreservation_paymenttransaction_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="buyer_type",
            field=models.CharField(
                choices=[
                    ("individual", "Individual"),
                    ("legal_entity", "Legal entity"),
                ],
                db_index=True,
                default="individual",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="company_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="company_identification_code",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="order",
            name="company_legal_address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
