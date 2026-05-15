from django.db import migrations


def remove_contact_support_footer_settings_copy(apps, schema_editor):
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    try:
        contact_content = Content.objects.get(name="contact_page_content")
    except Content.DoesNotExist:
        return

    ContentItem.objects.filter(
        content=contact_content,
        content_type="contact_notice",
        slug="support_intro",
    ).update(description="", editor="")


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0063_refresh_flexdrive_delivery_content"),
    ]

    operations = [
        migrations.RunPython(
            remove_contact_support_footer_settings_copy,
            migrations.RunPython.noop,
        ),
    ]
