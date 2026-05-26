from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0012_order_buyer_company_snapshot"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="company_legal_address",
        ),
    ]
