from django.db import migrations


OLD_CONTENT_NAME = "problem_solving_cards"
COMPONENT_NAME = "CategoryShortcuts"


def cleanup_problem_solving_content(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    Content = apps.get_model("pages", "Content")

    Component.objects.filter(component_type__name=COMPONENT_NAME).update(
        content=None,
        title="კატეგორიები",
        subtitle=None,
        button_text="ყველა კატეგორია",
        position=30,
    )
    Content.objects.filter(name=OLD_CONTENT_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0038_rename_problem_solving_component"),
    ]

    operations = [
        migrations.RunPython(cleanup_problem_solving_content, migrations.RunPython.noop),
    ]
