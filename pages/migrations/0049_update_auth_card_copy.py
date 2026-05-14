from django.db import migrations


LOGIN_CONTENT_NAME = "login_highlights"
REGISTER_CONTENT_NAME = "register_benefits"

LOGIN_ITEMS = (
    {
        "match_titles": ("შეკვეთების ისტორია", "შეკვეთების კონტროლი"),
        "position": 1,
        "title": "შეკვეთების კონტროლი",
        "description": "ნახე მიმდინარე სტატუსები და წინა შეკვეთები ერთ ადგილას.",
    },
    {
        "match_titles": ("სასურველები", "სურვილების სია", "რჩეულები და კალათა"),
        "position": 2,
        "title": "რჩეულები და კალათა",
        "description": "ნახე შენახული ნაწილები და გააგრძელე შეკვეთა იქიდან, სადაც გაჩერდი.",
    },
)

REGISTER_ITEMS = (
    {
        "match_titles": ("მისამართების შენახვა", "სწრაფი checkout", "შენახული მონაცემები"),
        "position": 1,
        "title": "შენახული მონაცემები",
        "description": "შეკვეთის გაფორმებისას საკონტაქტო და მიწოდების ინფორმაცია ავტომატურად შეივსება.",
    },
    {
        "match_titles": ("პროცესის გამარტივება", "შეკვეთების ისტორია"),
        "position": 2,
        "title": "შეკვეთების ისტორია",
        "description": "ყველა შეკვეთა და მიმდინარე სტატუსი შენს პროფილში დაგხვდება.",
    },
    {
        "match_titles": ("მხარდაჭერა ერთ სივრცეში", "სურვილების სია"),
        "position": 3,
        "title": "სურვილების სია",
        "description": "შეინახე საჭირო ნაწილები და ყიდვამდე მარტივად დაუბრუნდი.",
    },
)


def _find_item(items, used_ids, match_titles, fallback_position):
    for item in items:
        if item.id in used_ids:
            continue
        if item.title in match_titles:
            used_ids.add(item.id)
            return item

    for item in items:
        if item.id in used_ids:
            continue
        if item.position == fallback_position:
            used_ids.add(item.id)
            return item

    return None


def _sync_items(Content, ContentItem, content_name, item_definitions):
    content, _ = Content.objects.get_or_create(name=content_name)
    items = list(ContentItem.objects.filter(content=content).order_by("position", "id"))
    used_ids = set()

    for item_definition in item_definitions:
        item = _find_item(
            items,
            used_ids,
            item_definition["match_titles"],
            item_definition["position"],
        )
        values = {
            "position": item_definition["position"],
            "title": item_definition["title"],
            "description": item_definition["description"],
            "content_type": None,
            "icon_svg": None,
            "catalog_category_id": None,
            "singlePageRoute_id": None,
            "slug": None,
            "editor": None,
        }

        if item is None:
            created_item = ContentItem.objects.create(content=content, **values)
            used_ids.add(created_item.id)
            continue

        for field_name, value in values.items():
            setattr(item, field_name, value)
        item.save(update_fields=list(values.keys()))

    ContentItem.objects.filter(content=content).exclude(id__in=used_ids).delete()


def update_auth_card_copy(apps, schema_editor):
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    _sync_items(Content, ContentItem, LOGIN_CONTENT_NAME, LOGIN_ITEMS)
    _sync_items(Content, ContentItem, REGISTER_CONTENT_NAME, REGISTER_ITEMS)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0048_refresh_register_component"),
    ]

    operations = [
        migrations.RunPython(update_auth_card_copy, migrations.RunPython.noop),
    ]
