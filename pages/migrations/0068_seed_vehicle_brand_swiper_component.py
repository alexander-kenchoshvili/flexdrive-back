from django.db import migrations


SECTION_TITLE = "ნაწილები მარკის მიხედვით"
SECTION_SUBTITLE = (
    "აირჩიე ავტომობილის მარკა და პირდაპირ გადადი შესაბამისი ნაწილების კატალოგში."
)
SECTION_BUTTON_TEXT = "ყველა მარკის ნახვა"

COMPONENT_TYPE_NAME = "VehicleBrandSwiper"
CONTENT_NAME = "vehicle_brand_cards"
CARD_CONTENT_TYPE = "vehicle_brand"

HOME_COMPONENT_ORDER = {
    "HeroSection": 10,
    "FeaturedProducts": 20,
    "CategoryShortcuts": 30,
    "VehicleBrandSwiper": 40,
    "ValueProposition": 50,
    "OrderConfidence": 60,
    "HowItWorks": 70,
    "BlogSection": 80,
}

FALLBACK_BRAND_DEFINITIONS = (
    {
        "position": 1,
        "title": "Subaru",
        "slug": "subaru",
    },
    {
        "position": 2,
        "title": "Volkswagen",
        "slug": "volkswagen",
    },
    {
        "position": 3,
        "title": "Audi",
        "slug": "audi",
    },
    {
        "position": 4,
        "title": "Honda",
        "slug": "honda",
    },
    {
        "position": 5,
        "title": "Toyota",
        "slug": "toyota",
    },
    {
        "position": 6,
        "title": "Ford",
        "slug": "ford",
    },
    {
        "position": 7,
        "title": "Lexus",
        "slug": "lexus",
    },
    {
        "position": 8,
        "title": "Mitsubishi",
        "slug": "mitsubishi",
    },
    {
        "position": 9,
        "title": "Mazda",
        "slug": "mazda",
    },
    {
        "position": 10,
        "title": "BMW",
        "slug": "bmw",
    },
    {
        "position": 11,
        "title": "Mercedes",
        "slug": "mercedes",
    },
    {
        "position": 12,
        "title": "Tesla",
        "slug": "tesla",
    },
)


def _update_home_component_positions(Component, Page):
    main_page = Page.objects.filter(slug="main").first()
    if main_page is None:
        return

    components = list(
        Component.objects.filter(page_id=main_page.id)
        .select_related("component_type")
        .order_by("id")
    )

    assigned_ids = set()
    next_position = 10

    for component_name, position in HOME_COMPONENT_ORDER.items():
        matched = next(
            (
                component
                for component in components
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


def _vehicle_brand_definitions(apps):
    VehicleMake = apps.get_model("catalog", "VehicleMake")
    makes = list(
        VehicleMake.objects.filter(is_active=True)
        .order_by("sort_order", "name")
        .values("name", "slug")
    )
    if not makes:
        return FALLBACK_BRAND_DEFINITIONS

    return tuple(
        {
            "position": index,
            "title": make["name"],
            "slug": make["slug"],
        }
        for index, make in enumerate(makes, start=1)
    )


def seed_vehicle_brand_swiper_component(apps, schema_editor):
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
        Component.objects.filter(page=main_page, component_type=component_type)
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
            button_text=SECTION_BUTTON_TEXT,
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
        if component.button_text != SECTION_BUTTON_TEXT:
            component.button_text = SECTION_BUTTON_TEXT
            update_fields.append("button_text")
        if not component.enabled:
            component.enabled = True
            update_fields.append("enabled")
        if update_fields:
            component.save(update_fields=update_fields)

    used_ids = []
    for brand in _vehicle_brand_definitions(apps):
        item, _ = ContentItem.objects.update_or_create(
            content=content,
            position=brand["position"],
            defaults={
                "title": brand["title"],
                "description": f'{brand["title"]}-სთვის შერჩეული ავტონაწილები.',
                "content_type": CARD_CONTENT_TYPE,
                "icon_svg": None,
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": brand["slug"],
                "editor": None,
            },
        )
        used_ids.append(item.id)

    ContentItem.objects.filter(content=content).exclude(id__in=used_ids).delete()
    _update_home_component_positions(Component, Page)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_reorganize_catalog_categories"),
        ("pages", "0067_refine_returns_replacement_preference_copy"),
    ]

    operations = [
        migrations.RunPython(
            seed_vehicle_brand_swiper_component,
            migrations.RunPython.noop,
        ),
    ]
