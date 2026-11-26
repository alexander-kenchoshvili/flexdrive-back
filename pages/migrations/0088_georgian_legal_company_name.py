"""Use the owner-provided registered Georgian name in current public CMS copy."""
from django.db import migrations


OLD_NAME = "შპს FlexDrive"
LEGAL_NAME = "შპს ფლექსდრაივი"
TEXT_FIELDS = {
    "ContentItem": ("title", "description", "editor"),
    "Component": ("title", "subtitle", "button_text"),
    "Page": ("name", "seo_title", "seo_description", "footer_label"),
    "FooterSettings": ("brand_name", "brand_description", "copyright_text"),
    "SiteSettings": ("site_name", "default_seo_title", "default_seo_description"),
}


def use_georgian_legal_name(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, fields in TEXT_FIELDS.items():
        model = apps.get_model("pages", model_name)
        for row in model.objects.using(alias).only("pk", *fields).iterator():
            updates = {}
            for field in fields:
                value = getattr(row, field)
                if value and OLD_NAME in value:
                    updates[field] = value.replace(OLD_NAME, LEGAL_NAME)
            if updates:
                # Preserve editorial timestamps, HTML and all unrelated fields.
                model.objects.using(alias).filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("pages", "0087_personal_number_waybill_notice")]
    # Do not undo the registered name or rewrite historical order/terms snapshots.
    operations = [migrations.RunPython(use_georgian_legal_name, migrations.RunPython.noop)]
