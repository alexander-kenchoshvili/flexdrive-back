import re

from django.db import migrations
from django.utils import timezone


def update_regional_delivery_window(apps, schema_editor):
    alias = schema_editor.connection.alias
    pattern = re.compile(r"(?<!\d)4(?=\s*[-–—]\s*5\s+სამუშაო\s+დღ)")
    for model_name, fields in (
        ("ContentItem", ("title", "description", "editor")),
        ("Component", ("title", "subtitle")),
    ):
        Model = apps.get_model("pages", model_name)
        for item in Model.objects.using(alias).all().iterator():
            changes = {}
            for field in fields:
                value = getattr(item, field)
                if value:
                    updated = pattern.sub("3", value)
                    if updated != value:
                        changes[field] = updated
            if changes:
                if model_name == "ContentItem":
                    changes["updated_at"] = timezone.now()
                Model.objects.using(alias).filter(pk=item.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("pages", "0081_position_faq_after_vehicle_brands")]

    operations = [
        migrations.RunPython(update_regional_delivery_window, migrations.RunPython.noop),
    ]
