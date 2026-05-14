from django.db import migrations


CONTENT_NAME = "terms_sections"
OLD_TEXT = "მომხმარებელმა უნდა დაგვიკავშირდეს"
NEW_TEXT = "მომხმარებელი უნდა დაგვიკავშირდეს"


def fix_terms_customer_contact_grammar(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    for section in ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        editor__icontains=OLD_TEXT,
    ):
        updated_editor = section.editor.replace(OLD_TEXT, NEW_TEXT)
        if updated_editor != section.editor:
            section.editor = updated_editor
            section.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0051_refine_terms_account_security_copy"),
    ]

    operations = [
        migrations.RunPython(
            fix_terms_customer_contact_grammar,
            migrations.RunPython.noop,
        ),
    ]
