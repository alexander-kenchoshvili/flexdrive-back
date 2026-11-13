from django.db import migrations, models


def create_control(apps, schema_editor):
    apps.get_model("pages", "LaunchControl").objects.using(schema_editor.connection.alias).create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("pages", "0084_wingo_delivery_copy_complete")]
    operations = [
        migrations.CreateModel(
            name="LaunchControl",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("public_open", models.BooleanField(default=False)),
                ("preview_version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "საიტის საჯარო გახსნა",
                "verbose_name_plural": "საიტის საჯარო გახსნა",
                "constraints": [models.CheckConstraint(condition=models.Q(id=1), name="pages_launch_singleton")],
            },
        ),
        migrations.RunPython(create_control, migrations.RunPython.noop),
    ]
