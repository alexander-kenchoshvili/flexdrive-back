from django.db import migrations


CONTENT_NAME = "order_confidence_cards"
CARD_TITLE = "გადახდა შენზეა მორგებული"
CARD_POSITION = 3
OLD_DESCRIPTION = "აირჩიე შენთვის მოსახერხებელი გადახდის გზა, მათ შორის ნაწილ-ნაწილ გადახდის შესაძლებლობა."
NEW_DESCRIPTION = "გადაიხადე საკრედიტო ან სადებეტო ბარათით უსაფრთხოდ და სწრაფად."


def _update_payment_card_description(apps, description):
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    content = Content.objects.filter(name=CONTENT_NAME).first()
    if content is None:
        return

    item = (
        ContentItem.objects
        .filter(content=content, title=CARD_TITLE)
        .order_by("position", "id")
        .first()
    )

    if item is None:
        item = (
            ContentItem.objects
            .filter(content=content, position=CARD_POSITION)
            .order_by("id")
            .first()
        )

    if item is None:
        return

    item.title = CARD_TITLE
    item.description = description
    item.save(update_fields=["title", "description"])


def apply_copy(apps, schema_editor):
    _update_payment_card_description(apps, NEW_DESCRIPTION)


def revert_copy(apps, schema_editor):
    _update_payment_card_description(apps, OLD_DESCRIPTION)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0071_refresh_value_proposition_payment_copy"),
    ]

    operations = [
        migrations.RunPython(apply_copy, revert_copy),
    ]