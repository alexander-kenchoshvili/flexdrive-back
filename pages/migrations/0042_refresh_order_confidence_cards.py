from django.db import migrations


CONTENT_NAME = "order_confidence_cards"
COMPONENT_TYPE_NAME = "OrderConfidence"
OLD_SECTION_SUBTITLE = (
    "ონლაინ ყიდვისას ყველაზე ხშირად რაც აჩენს ეჭვს, აქ წინასწარ ნათელია: პროცესი, "
    "გადახდა, რეგისტრაცია და მიწოდება."
)
NEW_SECTION_SUBTITLE = (
    "ონლაინ ყიდვისას ყველაზე ხშირად რაც აჩენს ეჭვს, აქ წინასწარ ნათელია: პროცესი, "
    "რეგისტრაცია, გადახდა და მიწოდება."
)

CARD_CONTENT_TYPE = "trust_card"

CARD_DEFINITIONS = (
    {
        "key": "process",
        "position": 1,
        "match_titles": (
            "პროცესი წინასწარ ნათელია",
            "შეკვეთა მარტივად იწყება",
        ),
        "fallback_position": 1,
        "title": "შეკვეთა მარტივად იწყება",
        "description": (
            "საჭირო ავტონაწილს ირჩევ ონლაინ და შეკვეთის ნაბიჯები თავიდანვე "
            "გასაგებია, ზედმეტი დაბნეულობის გარეშე."
        ),
    },
    {
        "key": "registration",
        "position": 2,
        "match_titles": (
            "რეგისტრაცია სავალდებულო არ არის",
            "რეგისტრაცია აუცილებელი არ არის",
        ),
        "fallback_position": 3,
        "title": "რეგისტრაცია აუცილებელი არ არის",
        "description": (
            "თუ სწრაფად გჭირდება შეკვეთა, შეგიძლია პროცესი account-ის შექმნის "
            "გარეშე დაიწყო და დაასრულო."
        ),
    },
    {
        "key": "payment",
        "position": 3,
        "match_titles": (
            "გადახდა ისე, როგორც გაწყობს",
            "გადახდა შენზეა მორგებული",
        ),
        "fallback_position": 2,
        "title": "გადახდა შენზეა მორგებული",
        "description": (
            "აირჩიე შენთვის მოსახერხებელი გადახდის გზა, მათ შორის ნაწილ-ნაწილ "
            "გადახდის შესაძლებლობა."
        ),
    },
    {
        "key": "delivery",
        "position": 4,
        "match_titles": (
            "მიწოდებაზე გაურკვევლობა არ რჩება",
            "მიწოდება წინასწარ გასაგებია",
        ),
        "fallback_position": 4,
        "title": "მიწოდება წინასწარ გასაგებია",
        "description": (
            "შეკვეთამდე ხედავ მიწოდების პირობებს, რომ იცოდე როდის და როგორ "
            "მიიღებ საჭირო ნაწილს."
        ),
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


def refresh_order_confidence_cards(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    content = Content.objects.filter(name=CONTENT_NAME).first()
    if content is None:
        return

    component = (
        Component.objects
        .filter(content=content, component_type__name=COMPONENT_TYPE_NAME)
        .order_by("id")
        .first()
    )
    if component is not None and component.subtitle == OLD_SECTION_SUBTITLE:
        component.subtitle = NEW_SECTION_SUBTITLE
        component.save(update_fields=["subtitle"])

    items = list(ContentItem.objects.filter(content=content).order_by("position", "id"))
    used_ids = set()
    items_by_key = {}

    for card in CARD_DEFINITIONS:
        items_by_key[card["key"]] = _find_item(
            items,
            used_ids,
            card["match_titles"],
            card["fallback_position"],
        )

    for card in CARD_DEFINITIONS:
        item = items_by_key[card["key"]]
        if item is None:
            ContentItem.objects.create(
                content=content,
                position=card["position"],
                title=card["title"],
                description=card["description"],
                content_type=CARD_CONTENT_TYPE,
            )
            continue

        item.position = card["position"]
        item.title = card["title"]
        item.description = card["description"]
        item.content_type = CARD_CONTENT_TYPE
        item.save(update_fields=["position", "title", "description", "content_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0041_seed_value_proposition_component"),
    ]

    operations = [
        migrations.RunPython(refresh_order_confidence_cards, migrations.RunPython.noop),
    ]
