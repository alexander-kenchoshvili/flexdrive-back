from django.db import migrations


SECTION_TITLE = "ავტონაწილების შერჩევა Flex[[Drive]]-თან ერთად"
SECTION_SUBTITLE = (
    "შეარჩიე საჭირო ავტონაწილები ონლაინ, დაზოგე დრო ძებნაზე და მიიღე შეკვეთა "
    "შენთვის მოსახერხებელი პირობებით."
)
COMPONENT_TYPE_NAME = "ValueProposition"
CONTENT_NAME = "value_proposition_cards"
CARD_CONTENT_TYPE = "value_proposition_card"

HOME_COMPONENT_ORDER = {
    "HeroSection": 10,
    "FeaturedProducts": 20,
    "CategoryShortcuts": 30,
    "ValueProposition": 40,
    "OrderConfidence": 50,
    "HowItWorks": 60,
    "BlogSection": 70,
}

CARD_DEFINITIONS = (
    {
        "position": 1,
        "title": "დაზოგე დრო ძებნაზე",
        "description": (
            "შეარჩიე საჭირო ავტონაწილები ონლაინ, სხვადასხვა ადგილზე გადაადგილებისა "
            "და ხანგრძლივი ძებნის გარეშე."
        ),
    },
    {
        "position": 2,
        "title": "ისარგებლე მოქნილი გადახდით",
        "description": (
            "თუ თანხის ერთიანად გადახდა არ გსურს, შეგიძლია ისარგებლო ნაწილ-ნაწილ "
            "გადახდის შესაძლებლობით."
        ),
    },
    {
        "position": 3,
        "title": "მიიღე შეკვეთა მისამართზე",
        "description": (
            "შეკვეთილ ნაწილებს მიიღებ შენთვის მოსახერხებელ მისამართზე, სწრაფად "
            "და ორგანიზებულად."
        ),
    },
)


def _update_home_component_positions(Component, Page):
    main_page = Page.objects.filter(slug="main").first()
    if main_page is None:
        return

    components = list(
        Component.objects
        .filter(page_id=main_page.id)
        .select_related("component_type")
        .order_by("id")
    )

    assigned_ids = set()
    next_position = 10

    for component_name, position in HOME_COMPONENT_ORDER.items():
        matched = next(
            (
                component for component in components
                if component.id not in assigned_ids
                and getattr(component.component_type, "name", "") == component_name
            ),
            None,
        )
        if matched is None:
            continue

        Component.objects.filter(pk=matched.pk).update(position=position)
        assigned_ids.add(matched.id)
        next_position = max(next_position, position + 10)

    for component in components:
        if component.id in assigned_ids:
            continue
        Component.objects.filter(pk=component.pk).update(position=next_position)
        next_position += 10


def seed_value_proposition_component(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    main_page, _ = Page.objects.get_or_create(
        slug="main",
        defaults={
            "name": "მთავარი",
            "show_in_menu": True,
            "order": 0,
        },
    )

    component_type, _ = ComponentType.objects.get_or_create(name=COMPONENT_TYPE_NAME)
    content, _ = Content.objects.get_or_create(name=CONTENT_NAME)

    component = (
        Component.objects
        .filter(page=main_page, component_type=component_type)
        .order_by("id")
        .first()
    )
    if component is None:
        Component.objects.create(
            page=main_page,
            component_type=component_type,
            content=content,
            position=HOME_COMPONENT_ORDER[COMPONENT_TYPE_NAME],
            title=SECTION_TITLE,
            subtitle=SECTION_SUBTITLE,
            button_text=None,
            enabled=True,
        )

    for card in CARD_DEFINITIONS:
        ContentItem.objects.get_or_create(
            content=content,
            position=card["position"],
            defaults={
                "title": card["title"],
                "description": card["description"],
                "content_type": CARD_CONTENT_TYPE,
                "icon_svg": None,
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": None,
                "editor": None,
            },
        )

    _update_home_component_positions(Component, Page)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0040_alter_footersettings_brand_name_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_value_proposition_component, migrations.RunPython.noop),
    ]
