from django.db import migrations


CONTENT_NAME = "terms_sections"
SECTION_POSITION = 2
OLD_TEXT = (
    "<li>ანგარიშის ავტორიზაციის მონაცემების დაცვაზე პასუხისმგებელია მომხმარებელი.</li>"
)
NEW_TEXT = (
    "<li>მომხმარებელმა არ უნდა გადასცეს თავისი ანგარიშის მონაცემები მესამე პირს; "
    "FlexDrive კი იყენებს გონივრულ ტექნიკურ და ორგანიზაციულ ზომებს ანგარიშებისა და "
    "მონაცემების დასაცავად.</li>"
)


def refine_terms_account_security_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    section = (
        ContentItem.objects.filter(
            content__name=CONTENT_NAME,
            position=SECTION_POSITION,
        )
        .order_by("id")
        .first()
    )
    if section is None or not section.editor:
        return

    updated_editor = section.editor.replace(OLD_TEXT, NEW_TEXT)
    if updated_editor != section.editor:
        section.editor = updated_editor
        section.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0050_refresh_flexdrive_terms_content"),
    ]

    operations = [
        migrations.RunPython(
            refine_terms_account_security_copy,
            migrations.RunPython.noop,
        ),
    ]
