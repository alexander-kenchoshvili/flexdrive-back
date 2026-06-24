from django.db import migrations


CONTENT_NAME = "how_it_works_main"
CONTENT_TYPE = "registered_step"
TITLE_UPDATES = (
    {
        "position": 501,
        "old_title": "გამოიყენე Wishlist და ისტორია",
        "new_title": "გამოიყენე Wishlist",
    },
    {
        "position": 503,
        "old_title": "აკონტროლე შეკვეთა",
        "new_title": "სწრაფი Checkout",
    },
)


def _update_titles(apps, use_new_titles):
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    content = Content.objects.filter(name=CONTENT_NAME).first()
    if content is None:
        return

    for item_definition in TITLE_UPDATES:
        old_title = item_definition["old_title"]
        new_title = item_definition["new_title"]
        target_title = new_title if use_new_titles else old_title
        current_titles = (old_title, new_title)

        item = (
            ContentItem.objects
            .filter(
                content=content,
                content_type=CONTENT_TYPE,
                position=item_definition["position"],
            )
            .order_by("id")
            .first()
        )

        if item is None:
            item = (
                ContentItem.objects
                .filter(
                    content=content,
                    content_type=CONTENT_TYPE,
                    title__in=current_titles,
                )
                .order_by("position", "id")
                .first()
            )

        if item is None:
            continue

        item.title = target_title
        item.save(update_fields=["title"])


def apply_titles(apps, schema_editor):
    _update_titles(apps, use_new_titles=True)


def revert_titles(apps, schema_editor):
    _update_titles(apps, use_new_titles=False)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0073_refresh_how_it_works_order_check_copy"),
    ]

    operations = [
        migrations.RunPython(apply_titles, revert_titles),
    ]