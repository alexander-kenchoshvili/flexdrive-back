from django.db import migrations


CONTENT_NAME = "how_it_works_main"
COMPONENT_TYPE_NAME = "HowItWorks"
SECTION_TITLE = "აირჩიე გზა შეკვეთამდე Flex[[Drive]]-ზე"
SECTION_SUBTITLE = (
    "სწრაფი checkout სტუმრისთვის ან სრული კონტროლი ავტორიზებული მომხმარებლისთვის - "
    "ორივე გზით შეკვეთა მარტივად სრულდება."
)

TAB_DEFINITIONS = (
    {
        "key": "guest_tab",
        "position": 10,
        "match_titles": ("სტუმრის შეკვეთა", "სტუმრად ყიდვა"),
        "fallback_position": 10,
        "title": "სტუმრად ყიდვა",
        "description": "",
    },
    {
        "key": "registered_tab",
        "position": 20,
        "match_titles": ("ავტორიზებულის შეკვეთა", "ანგარიშით ყიდვა"),
        "fallback_position": 20,
        "title": "ანგარიშით ყიდვა",
        "description": "",
    },
)

STEP_DEFINITIONS = (
    {
        "key": "guest_search",
        "content_type": "guest_step",
        "position": 100,
        "match_titles": ("იპოვე პროდუქტი", "იპოვე საჭირო ნაწილი"),
        "fallback_position": 100,
        "title": "იპოვე საჭირო ნაწილი",
        "description": "მოძებნე კატეგორიით, ბრენდით ან ნაწილის დასახელებით.",
    },
    {
        "key": "guest_cart",
        "content_type": "guest_step",
        "position": 101,
        "match_titles": ("კალათაში დამატება", "დაამატე კალათაში"),
        "fallback_position": 101,
        "title": "დაამატე კალათაში",
        "description": "გადაამოწმე ფასი, რაოდენობა და ხელმისაწვდომობა.",
    },
    {
        "key": "guest_details",
        "content_type": "guest_step",
        "position": 102,
        "match_titles": ("შეიყვანე მონაცემები", "შეავსე მონაცემები"),
        "fallback_position": 102,
        "title": "შეავსე მონაცემები",
        "description": "მიუთითე სახელი, ტელეფონი და მიწოდების დეტალები.",
    },
    {
        "key": "guest_confirm",
        "content_type": "guest_step",
        "position": 103,
        "match_titles": ("მიიღე სახლამდე", "დაადასტურე შეკვეთა"),
        "fallback_position": 103,
        "title": "დაადასტურე შეკვეთა",
        "description": "შეკვეთის სტატუსს მიიღებ SMS-ით ან ოპერატორისგან.",
    },
    {
        "key": "registered_account",
        "content_type": "registered_step",
        "position": 500,
        "match_titles": ("შექმენი ანგარიში", "შედი ანგარიშში"),
        "fallback_position": 500,
        "title": "შედი ანგარიშში",
        "description": "შენახული მონაცემებით checkout უფრო სწრაფად სრულდება.",
    },
    {
        "key": "registered_wishlist",
        "content_type": "registered_step",
        "position": 501,
        "match_titles": ("შეაგროვე კალათა", "გამოიყენე Wishlist და ისტორია"),
        "fallback_position": 501,
        "title": "გამოიყენე Wishlist და ისტორია",
        "description": "დაიმახსოვრე ნაწილები ან ხელახლა შეუკვეთე წინა არჩევანი.",
    },
    {
        "key": "registered_checkout",
        "content_type": "registered_step",
        "position": 502,
        "match_titles": ("სწრაფი Checkout", "დაასრულე Checkout სწრაფად"),
        "fallback_position": 502,
        "title": "დაასრულე Checkout სწრაფად",
        "description": "მისამართი და საკონტაქტო ინფორმაცია უკვე მზად არის.",
    },
    {
        "key": "registered_tracking",
        "content_type": "registered_step",
        "position": 503,
        "match_titles": ("Tracking & ისტორია", "აკონტროლე შეკვეთა"),
        "fallback_position": 503,
        "title": "აკონტროლე შეკვეთა",
        "description": "ნახე შეკვეთის სტატუსი, მიწოდება და წინა შესყიდვები.",
    },
)

CARD_DEFINITIONS = (
    {
        "key": "guest_note",
        "content_type": "guest_card",
        "position": 200,
        "match_titles": ("სტუმრის შეკვეთა:", "სტუმრად ყიდვა სწრაფია"),
        "fallback_position": 0,
        "title": "სტუმრად ყიდვა სწრაფია",
        "description": (
            "შეკვეთას ასრულებ ანგარიშის შექმნის გარეშე. სტატუსს მიიღებ SMS-ით ან "
            "ოპერატორისგან. [[დარეგისტრირდი]], თუ გინდა შეკვეთების ისტორია და Wishlist შეინახო."
        ),
    },
    {
        "key": "registered_wishlist_card",
        "content_type": "registered_card",
        "position": 700,
        "match_titles": ("Wishlist", "Wishlist და განმეორებითი არჩევანი"),
        "fallback_position": 700,
        "title": "Wishlist და განმეორებითი არჩევანი",
        "description": "შეინახე ხშირად საჭირო ნაწილები და დაბრუნდი მათთან მოგვიანებით.",
    },
    {
        "key": "registered_address_card",
        "content_type": "registered_card",
        "position": 701,
        "match_titles": ("შენახული მისამართები",),
        "fallback_position": 701,
        "title": "შენახული მისამართები",
        "description": "Checkout-ში აღარ დაგჭირდება იმავე მონაცემების ხელახლა შეყვანა.",
    },
    {
        "key": "registered_history_card",
        "content_type": "registered_card",
        "position": 702,
        "match_titles": ("დაბრუნების მოთხოვნა", "შეკვეთების ისტორია"),
        "fallback_position": 702,
        "title": "შეკვეთების ისტორია",
        "description": "ნახე სტატუსები, წინა შეკვეთები და განმეორებითი ყიდვის დეტალები.",
    },
)

ALL_ITEM_DEFINITIONS = TAB_DEFINITIONS + STEP_DEFINITIONS + CARD_DEFINITIONS


def _find_item(items, used_ids, content_type, match_titles, fallback_position):
    for item in items:
        if item.id in used_ids:
            continue
        if item.content_type == content_type and item.title in match_titles:
            used_ids.add(item.id)
            return item

    for item in items:
        if item.id in used_ids:
            continue
        if item.content_type == content_type and item.position == fallback_position:
            used_ids.add(item.id)
            return item

    return None


def refresh_how_it_works_component(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    main_page, _ = Page.objects.get_or_create(
        slug="main",
        defaults={"name": "მთავარი", "show_in_menu": True, "order": 0},
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
            position=60,
            title=SECTION_TITLE,
            subtitle=SECTION_SUBTITLE,
            button_text=None,
            enabled=True,
        )
    else:
        component.content = content
        component.position = 60
        component.title = SECTION_TITLE
        component.subtitle = SECTION_SUBTITLE
        component.button_text = None
        component.enabled = True
        component.save(
            update_fields=[
                "content",
                "position",
                "title",
                "subtitle",
                "button_text",
                "enabled",
            ]
        )

    items = list(ContentItem.objects.filter(content=content).order_by("position", "id"))
    used_ids = set()

    for item_definition in ALL_ITEM_DEFINITIONS:
        content_type = item_definition["content_type"] if "content_type" in item_definition else item_definition["key"]
        item = _find_item(
            items,
            used_ids,
            content_type,
            item_definition["match_titles"],
            item_definition["fallback_position"],
        )
        values = {
            "position": item_definition["position"],
            "title": item_definition["title"],
            "description": item_definition["description"],
            "content_type": content_type,
            "icon_svg": None,
            "catalog_category_id": None,
            "singlePageRoute_id": None,
            "slug": None,
            "editor": None,
        }

        if item is None:
            ContentItem.objects.create(content=content, **values)
            continue

        for field_name, value in values.items():
            setattr(item, field_name, value)
        item.save(update_fields=list(values.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0043_shorten_order_confidence_registration_title"),
    ]

    operations = [
        migrations.RunPython(refresh_how_it_works_component, migrations.RunPython.noop),
    ]
