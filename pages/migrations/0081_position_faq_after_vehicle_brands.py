from django.db import migrations
from django.db.models import F


def position_faq_after_vehicle_brands(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    components = Component.objects.using(schema_editor.connection.alias).filter(page__slug="main")
    brand = components.filter(component_type__name="VehicleBrandSwiper").order_by("position", "id").first()
    faq = components.filter(component_type__name="Faq").order_by("position", "id").first()
    if brand is None or faq is None:
        return
    position = brand.position + 1
    others = components.exclude(pk=faq.pk)
    if others.filter(position=position).exists():
        others.filter(position__gte=position).update(position=F("position") + 1)
    components.filter(pk=faq.pk).update(position=position)


class Migration(migrations.Migration):
    dependencies = [("pages", "0080_seed_homepage_faq")]

    operations = [
        migrations.RunPython(position_faq_after_vehicle_brands, migrations.RunPython.noop),
    ]
