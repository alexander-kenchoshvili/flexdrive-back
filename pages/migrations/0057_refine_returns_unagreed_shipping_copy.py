from django.db import migrations


CONTENT_NAME = "returns_sections"
OLD_TEXT = (
    "შეუთანხმებლად გაგზავნილი ამანათის მიღება ან ხარჯის ანაზღაურება "
    "წინასწარ გარანტირებული არ არის."
)
NEW_TEXT = (
    "შეუთანხმებლად გაგზავნილი ამანათის მიღება ან ხარჯის ანაზღაურება "
    "წინასწარ დადასტურებული არ არის."
)


def refine_returns_unagreed_shipping_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")
    items = ContentItem.objects.filter(content__name=CONTENT_NAME, editor__contains=OLD_TEXT)
    for item in items:
        item.editor = item.editor.replace(OLD_TEXT, NEW_TEXT)
        item.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0056_refresh_flexdrive_returns_content"),
    ]

    operations = [
        migrations.RunPython(
            refine_returns_unagreed_shipping_copy,
            migrations.RunPython.noop,
        ),
    ]
