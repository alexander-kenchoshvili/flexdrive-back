from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
    ]
