from django.db import migrations


OLD_COMPONENT_NAME = "ProblemSolving"
NEW_COMPONENT_NAME = "CategoryShortcuts"


def rename_component_type(apps, schema_editor):
    ComponentType = apps.get_model("pages", "ComponentType")
    Component = apps.get_model("pages", "Component")

    old_type = ComponentType.objects.filter(name=OLD_COMPONENT_NAME).first()
    new_type = ComponentType.objects.filter(name=NEW_COMPONENT_NAME).first()

    if old_type and new_type:
        Component.objects.filter(component_type=old_type).update(component_type=new_type)
        old_type.delete()
        return

    if old_type:
        old_type.name = NEW_COMPONENT_NAME
        old_type.save(update_fields=["name"])
        return

    ComponentType.objects.get_or_create(name=NEW_COMPONENT_NAME)


def reverse_rename_component_type(apps, schema_editor):
    ComponentType = apps.get_model("pages", "ComponentType")
    Component = apps.get_model("pages", "Component")

    new_type = ComponentType.objects.filter(name=NEW_COMPONENT_NAME).first()
    old_type = ComponentType.objects.filter(name=OLD_COMPONENT_NAME).first()

    if new_type and old_type:
        Component.objects.filter(component_type=new_type).update(component_type=old_type)
        new_type.delete()
        return

    if new_type:
        new_type.name = OLD_COMPONENT_NAME
        new_type.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0037_refresh_flexdrive_seo_copy"),
    ]

    operations = [
        migrations.RunPython(rename_component_type, reverse_rename_component_type),
    ]
