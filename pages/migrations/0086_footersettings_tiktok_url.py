from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0085_launch_control"),
    ]

    operations = [
        migrations.AddField(
            model_name="footersettings",
            name="tiktok_url",
            field=models.URLField(blank=True, null=True),
        ),
    ]
