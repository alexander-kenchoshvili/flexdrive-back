from django.db import migrations


CONTENT_NAME = "register_benefits"
COMPONENT_TYPE_NAME = "RegisterForm"
PAGE_SLUG = "register"

SECTION_TITLE = "შექმენი Flex[[Drive]] ანგარიში"
SECTION_SUBTITLE = (
    "შეინახე შეკვეთები, სურვილების სია და მიწოდების მონაცემები ერთ პროფილში."
)
SECTION_BUTTON_TEXT = "FlexDrive პროფილი"

BENEFIT_ITEMS = (
    {
        "match_titles": ("მისამართების შენახვა", "სწრაფი checkout"),
        "position": 1,
        "title": "სწრაფი checkout",
        "description": "შენახული მონაცემებით შეკვეთის გაფორმება უფრო სწრაფად სრულდება.",
    },
    {
        "match_titles": ("პროცესის გამარტივება", "შეკვეთების ისტორია"),
        "position": 2,
        "title": "შეკვეთების ისტორია",
        "description": "პროფილში ნახავ შეკვეთების სტატუსებს და წინა შესყიდვებს.",
    },
    {
        "match_titles": ("მხარდაჭერა ერთ სივრცეში", "სურვილების სია"),
        "position": 3,
        "title": "სურვილების სია",
        "description": "შეინახე საჭირო ნაწილები და მოგვიანებით სწრაფად დაუბრუნდი.",
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


def refresh_register_component(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    page, _ = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": "რეგისტრაცია",
            "show_in_menu": False,
            "order": 0,
        },
    )
    component_type, _ = ComponentType.objects.get_or_create(name=COMPONENT_TYPE_NAME)
    content, _ = Content.objects.get_or_create(name=CONTENT_NAME)

    component = (
        Component.objects
        .filter(page=page, component_type=component_type)
        .order_by("id")
        .first()
    )

    if component is None:
        Component.objects.create(
            page=page,
            component_type=component_type,
            content=content,
            position=1,
            title=SECTION_TITLE,
            subtitle=SECTION_SUBTITLE,
            button_text=SECTION_BUTTON_TEXT,
            enabled=True,
        )
    else:
        component.content = content
        component.title = SECTION_TITLE
        component.subtitle = SECTION_SUBTITLE
        component.button_text = SECTION_BUTTON_TEXT
        component.enabled = True
        component.save(
            update_fields=[
                "content",
                "title",
                "subtitle",
                "button_text",
                "enabled",
            ]
        )

    items = list(ContentItem.objects.filter(content=content).order_by("position", "id"))
    used_ids = set()

    for item_definition in BENEFIT_ITEMS:
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


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0047_refresh_login_component"),
    ]

    operations = [
        migrations.RunPython(refresh_register_component, migrations.RunPython.noop),
    ]
