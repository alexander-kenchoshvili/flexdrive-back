from django.db import migrations


CONTENT_NAME = "value_proposition_cards"
CARD_TITLE = "ისარგებლე მოქნილი გადახდით"
CARD_POSITION = 2
OLD_DESCRIPTION = "თუ თანხის ერთიანად გადახდა არ გსურს, შეგიძლია ისარგებლო ნაწილ-ნაწილ გადახდის შესაძლებლობით."
NEW_DESCRIPTION = "პროდუქტის შეძენა შეგიძლია სადებეტო ან საკრედიტო ბარათით."


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

    item.description = description
    item.save(update_fields=["description"])


def apply_copy(apps, schema_editor):
    _update_payment_card_description(apps, NEW_DESCRIPTION)


def revert_copy(apps, schema_editor):
    _update_payment_card_description(apps, OLD_DESCRIPTION)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0070_component_pages_comp_page_en_pos_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(apply_copy, revert_copy),
    ]
