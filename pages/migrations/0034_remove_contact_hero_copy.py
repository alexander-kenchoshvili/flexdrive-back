from django.db import migrations


def remove_contact_hero_copy(apps, schema_editor):
    Component = apps.get_model("pages", "Component")

    Component.objects.filter(
        page__slug="contact",
        component_type__name="Contact",
    ).update(
        title=None,
        subtitle=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0033_remove_contact_form_helper"),
    ]

    operations = [
        migrations.RunPython(
            remove_contact_hero_copy,
            migrations.RunPython.noop,
        ),
    ]
