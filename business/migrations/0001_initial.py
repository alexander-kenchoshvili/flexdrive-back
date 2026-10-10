from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DashboardAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ],
            options={
                "managed": False,
                "default_permissions": (),
                "permissions": [("view_dashboard", "ბიზნესპანელის ნახვა")],
                "verbose_name": "ბიზნესპანელის წვდომა",
                "verbose_name_plural": "ბიზნესპანელის წვდომა",
            },
        ),
    ]
