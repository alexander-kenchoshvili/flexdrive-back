from django.db import migrations


CONTENT_NAME = "how_it_works_main"
CONTENT_TYPE = "guest_step"
CARD_POSITION = 103
OLD_TITLE = "დაადასტურე შეკვეთა"
OLD_DESCRIPTION = "შეკვეთის სტატუსს მიიღებ SMS-ით ან ოპერატორისგან."
NEW_TITLE = "შეკვეთის შემოწმება"
NEW_DESCRIPTION = "პროდუქტის ყიდვის შემდეგ მიიღებ შეკვეთის ნომერს, რისი მეშვეობითაც შეგიძლია გადაამოწმო შენი შეკვეთის სტატუსი."


def _update_order_check_copy(apps, title, description):
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    content = Content.objects.filter(name=CONTENT_NAME).first()
    if content is None:
        return

    item = (
        ContentItem.objects
        .filter(content=content, content_type=CONTENT_TYPE, title__in=(OLD_TITLE, NEW_TITLE))
        .order_by("position", "id")
        .first()
    )

    if item is None:
        item = (
            ContentItem.objects
            .filter(content=content, content_type=CONTENT_TYPE, position=CARD_POSITION)
            .order_by("id")
            .first()
        )

    if item is None:
        return

    item.title = title
    item.description = description
    item.save(update_fields=["title", "description"])


def apply_copy(apps, schema_editor):
    _update_order_check_copy(apps, NEW_TITLE, NEW_DESCRIPTION)


def revert_copy(apps, schema_editor):
    _update_order_check_copy(apps, OLD_TITLE, OLD_DESCRIPTION)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0072_refresh_order_confidence_payment_copy"),
    ]

    operations = [
        migrations.RunPython(apply_copy, revert_copy),
    ]