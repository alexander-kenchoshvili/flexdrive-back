from django.db import migrations


def remove_contact_form_helper(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    ContentItem.objects.filter(
        content__name="contact_page_content",
        content_type="contact_notice",
        slug="form_helper",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0032_contact_page_content"),
    ]

    operations = [
        migrations.RunPython(
            remove_contact_form_helper,
            migrations.RunPython.noop,
        ),
    ]
