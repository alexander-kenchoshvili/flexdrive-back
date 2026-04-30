from django.db import migrations


CONTENT_NAME = "order_confidence_cards"
OLD_TITLE = "რეგისტრაცია აუცილებელი არ არის"
NEW_TITLE = "რეგისტრაციის გარეშე"


def shorten_registration_title(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        title=OLD_TITLE,
    ).update(title=NEW_TITLE)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0042_refresh_order_confidence_cards"),
    ]

    operations = [
        migrations.RunPython(shorten_registration_title, migrations.RunPython.noop),
    ]
