from django.db import migrations


FOOTER_SETTINGS_DEFAULTS = {
    "brand_name": "FlexDrive",
    "brand_description": (
        "FlexDrive გეხმარება ავტონაწილების მარტივად მოძებნასა და შეძენაში."
    ),
    "email": "support@flexdrive.ge",
    "copyright_text": "© 2026 FlexDrive. ყველა უფლება დაცულია.",
}


def refresh_footer_settings(apps, schema_editor):
    FooterSettings = apps.get_model("pages", "FooterSettings")

    FooterSettings.objects.update_or_create(pk=1, defaults=FOOTER_SETTINGS_DEFAULTS)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0045_refine_how_it_works_guest_choice"),
    ]

    operations = [
        migrations.RunPython(refresh_footer_settings, migrations.RunPython.noop),
    ]
