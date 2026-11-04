from django.db import migrations
from django.db.models import Q
from django.utils import timezone


def update_delivery_cutoff(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")
    alias = schema_editor.connection.alias
    sections = (
        Q(content__name="delivery_sections", content_type="delivery_section")
        | Q(content__name="terms_sections", content_type="terms_section")
    )
    items = ContentItem.objects.using(alias).filter(sections).filter(
        Q(editor__contains="14:00") | Q(description__contains="14:00")
    )
    for item in items:
        changes = {}
        for field in ("description", "editor"):
            value = getattr(item, field)
            if value and "14:00" in value:
                changes[field] = value.replace("14:00", "13:00")
        if changes:
            changes["updated_at"] = timezone.now()
            ContentItem.objects.using(alias).filter(pk=item.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("pages", "0078_footersettings_linkedin_url")]

    operations = [
        migrations.RunPython(update_delivery_cutoff, migrations.RunPython.noop),
    ]
