from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0077_add_account_data_deletion_instructions"),
    ]

    operations = [
        migrations.AddField(
            model_name="footersettings",
            name="linkedin_url",
            field=models.URLField(blank=True, null=True),
        ),
    ]
