from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0027_orderreceipt")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="company_is_vat_registered",
            field=models.BooleanField(
                verbose_name="დღგ-ის გადამხდელი (მყიდველის მითითებით)",
                null=True, blank=True, default=None,
                help_text="მყიდველის პასუხი შეკვეთის გაფორმებისას; სტატუსი ავტომატურად არ მოწმდება.",
            ),
        ),
    ]
