from django.db import migrations


SECTION_TITLE = "შეკვეთა Auto[[Mate]]-ზე წინასწარ გასაგებია"
SECTION_SUBTITLE = (
    "ონლაინ ყიდვისას ყველაზე ხშირად რაც აჩენს ეჭვს, აქ წინასწარ ნათელია: პროცესი, "
    "გადახდა, რეგისტრაცია და მიწოდება."
)
COMPONENT_TYPE_NAME = "OrderConfidence"
CONTENT_NAME = "order_confidence_cards"

HOME_COMPONENT_ORDER = {
    "HeroSection": 10,
    "ProblemSolving": 20,
    "FeaturedProducts": 30,
    "OrderConfidence": 40,
    "HowItWorks": 50,
    "BlogSection": 60,
}

CARD_DEFINITIONS = (
    {
        "position": 1,
        "title": "პროცესი წინასწარ ნათელია",
        "description": (
            "არჩევიდან შეკვეთამდე გზა მოკლე და გასაგებია, ისე რომ checkout-ში "
            "სიურპრიზები არ დაგხვდეს."
        ),
        "content_type": "trust_card",
        "icon_svg": """
<svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M15 4.5 L17.3 10.2 L23.5 10.8 L18.9 14.9 L20.4 21.2 L15 18.1 L9.6 21.2 L11.1 14.9 L6.5 10.8 L12.7 10.2 Z" stroke="#ff6b35" stroke-width="1.8" stroke-linejoin="round"/>
  <circle cx="15" cy="15" r="3.2" fill="#ff6b35" opacity=".16"/>
  <path d="M15 9.8 L15 15 L18.2 16.9" stroke="#ff6b35" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip(),
    },
    {
        "position": 2,
        "title": "გადახდა ისე, როგორც გაწყობს",
        "description": (
            "შეუკვეთე შენთვის კომფორტული ფორმით, ზედმეტი დაბრკოლებების და "
            "იძულებითი ნაბიჯების გარეშე."
        ),
        "content_type": "trust_card",
        "icon_svg": """
<svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="4.5" y="7" width="21" height="15.5" rx="3.5" stroke="#ff6b35" stroke-width="1.8"/>
  <path d="M4.5 11.5 H25.5" stroke="#ff6b35" stroke-width="1.8" stroke-linecap="round"/>
  <rect x="8" y="16" width="5.5" height="2.6" rx="1.3" fill="#ff6b35" opacity=".45"/>
  <rect x="15.5" y="16" width="2.8" height="2.6" rx="1.3" fill="#ff6b35" opacity=".25"/>
  <rect x="19.7" y="16" width="2.8" height="2.6" rx="1.3" fill="#ff6b35" opacity=".25"/>
  <circle cx="23.5" cy="7.5" r="1.2" fill="#ff6b35" opacity=".35"/>
</svg>
""".strip(),
    },
    {
        "position": 3,
        "title": "რეგისტრაცია სავალდებულო არ არის",
        "description": (
            "თუ უბრალოდ სწრაფად შეძენა გინდა, პროფილის შექმნა არ გაჩერებს და "
            "შეკვეთას პირდაპირ აგზავნი."
        ),
        "content_type": "trust_card",
        "icon_svg": """
<svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="13" cy="11" r="4.2" stroke="#ff6b35" stroke-width="1.8"/>
  <path d="M5.5 24 C5.5 19.8 9 16.8 13 16.8 C17 16.8 20.5 19.8 20.5 24" stroke="#ff6b35" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M21 10.8 L23.1 12.9 L26.8 8.8" stroke="#ff6b35" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="23.8" cy="10.8" r="4.2" fill="#ff6b35" opacity=".08"/>
</svg>
""".strip(),
    },
    {
        "position": 4,
        "title": "მიწოდებაზე გაურკვევლობა არ რჩება",
        "description": (
            "მიღების პროცესი მკაფიოა და შეკვეთის ბოლო ეტაპზეც იცი რას უნდა ელოდო."
        ),
        "content_type": "trust_card",
        "icon_svg": """
<svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M4.5 18.5 V10 H17.5 V21 H9.2" stroke="#ff6b35" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M17.5 13 H21.5 L25.5 17 V21 H17.5" stroke="#ff6b35" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="10.2" cy="22.2" r="2" stroke="#ff6b35" stroke-width="1.6"/>
  <circle cx="21.6" cy="22.2" r="2" stroke="#ff6b35" stroke-width="1.6"/>
  <path d="M8 10 V7 H14" stroke="#ff6b35" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" opacity=".45"/>
</svg>
""".strip(),
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


def seed_order_confidence_component(apps, schema_editor):
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
    else:
        update_fields = []
        if component.content_id != content.id:
            component.content = content
            update_fields.append("content")
        if component.position != HOME_COMPONENT_ORDER[COMPONENT_TYPE_NAME]:
            component.position = HOME_COMPONENT_ORDER[COMPONENT_TYPE_NAME]
            update_fields.append("position")
        if component.title != SECTION_TITLE:
            component.title = SECTION_TITLE
            update_fields.append("title")
        if component.subtitle != SECTION_SUBTITLE:
            component.subtitle = SECTION_SUBTITLE
            update_fields.append("subtitle")
        if component.button_text is not None:
            component.button_text = None
            update_fields.append("button_text")
        if not component.enabled:
            component.enabled = True
            update_fields.append("enabled")
        if update_fields:
            component.save(update_fields=update_fields)

    for card in CARD_DEFINITIONS:
        ContentItem.objects.update_or_create(
            content=content,
            position=card["position"],
            defaults={
                "title": card["title"],
                "description": card["description"],
                "content_type": card["content_type"],
                "icon_svg": card["icon_svg"],
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": None,
                "editor": None,
            },
        )

    _update_home_component_positions(Component, Page)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0021_component_position"),
    ]

    operations = [
        migrations.RunPython(seed_order_confidence_component, migrations.RunPython.noop),
    ]
