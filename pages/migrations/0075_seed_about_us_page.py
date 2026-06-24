from django.db import migrations


COMPONENT_TYPE_NAME = "AboutUs"
CONTENT_NAME = "about_us_page_content"
PAGE_SLUG = "about-us"
PAGE_NAME = "ჩვენ შესახებ"
FOOTER_LABEL = "ჩვენ შესახებ"
SECTION_TITLE = "Flex[[Drive]]-ის შესახებ"
SECTION_SUBTITLE = (
    "Flex[[Drive]] ვქმნით ავტონაწილების ყიდვის უფრო მარტივ გზას: მკაფიო "
    "კატალოგი, გასაგები Checkout და შეკვეთის სტატუსი ერთ სივრცეში. ჩვენი მიზანია, "
    "მომხმარებელს შევთავაზოთ სრულიად ახალი გამოცდილება ხარისხსა და მომსახურებაში."
)
SEO_TITLE = "ჩვენ შესახებ | FlexDrive"
SEO_DESCRIPTION = (
    "FlexDrive ქმნის ავტონაწილების ყიდვის უფრო მარტივ გზას მკაფიო კატალოგით, "
    "გასაგები checkout-ით და შეკვეთის სტატუსის გადამოწმებით."
)

EYEBROW_ITEM = {
    "position": 5,
    "slug": "eyebrow",
    "title": "ავტონაწილების ონლაინ მაღაზია",
    "description": "",
    "content_type": "about_eyebrow",
}

PANEL_ITEM = {
    "position": 100,
    "slug": "summary",
    "title": "რას იღებს მომხმარებელი",
    "description": "Flex[[Drive]] არის პრაქტიკული სივრცე ნაწილის მოძებნისა და შეკვეთისთვის.",
    "content_type": "about_panel",
}

FEATURE_ITEMS = (
    {
        "position": 200,
        "slug": "catalog",
        "title": "კატალოგი",
        "description": "კატეგორიები, ბრენდები და სწრაფი ძიება.",
        "content_type": "about_feature",
    },
    {
        "position": 210,
        "slug": "payment",
        "title": "გადახდა",
        "description": "სწრაფი და უსაფრთხო ონლაინ ტრანზაქცია.",
        "content_type": "about_feature",
    },
    {
        "position": 220,
        "slug": "status",
        "title": "სტატუსი",
        "description": "შეკვეთის მიმდინარეობის მარტივი გადამოწმება.",
        "content_type": "about_feature",
    },
)

ACTION_ITEMS = (
    {
        "position": 300,
        "slug": "catalog",
        "title": "კატალოგის ნახვა",
        "description": "",
        "content_type": "about_action",
    },
    {
        "position": 310,
        "slug": "order-status",
        "title": "შეკვეთის სტატუსი",
        "description": "",
        "content_type": "about_action",
    },
)


def upsert_content_item(ContentItem, content, item):
    ContentItem.objects.update_or_create(
        content=content,
        position=item["position"],
        defaults={
            "title": item["title"],
            "description": item["description"] or None,
            "content_type": item["content_type"],
            "icon_svg": None,
            "editor": None,
            "catalog_category_id": None,
            "singlePageRoute_id": None,
            "slug": item["slug"],
        },
    )


def seed_about_us_page(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    page, _created = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": PAGE_NAME,
            "show_in_menu": True,
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 45,
            "footer_label": FOOTER_LABEL,
            "order": 45,
            "url": None,
            "seo_title": SEO_TITLE,
            "seo_description": SEO_DESCRIPTION,
            "seo_noindex": False,
        },
    )

    page_updates = {
        "name": PAGE_NAME,
        "show_in_menu": True,
        "show_in_footer": True,
        "footer_group": "navigation",
        "footer_order": 45,
        "footer_label": FOOTER_LABEL,
        "order": 45,
        "url": None,
        "seo_title": SEO_TITLE,
        "seo_description": SEO_DESCRIPTION,
        "seo_noindex": False,
    }
    page_update_fields = []
    for field_name, value in page_updates.items():
        if getattr(page, field_name) != value:
            setattr(page, field_name, value)
            page_update_fields.append(field_name)
    if page_update_fields:
        page.save(update_fields=page_update_fields)

    component_type, _created = ComponentType.objects.get_or_create(
        name=COMPONENT_TYPE_NAME
    )
    content, _created = Content.objects.get_or_create(name=CONTENT_NAME)

    component = (
        Component.objects.filter(page=page, component_type=component_type)
        .order_by("position", "id")
        .first()
    )

    if component is None:
        component = Component.objects.create(
            page=page,
            component_type=component_type,
            content=content,
            position=10,
            title=SECTION_TITLE,
            subtitle=SECTION_SUBTITLE,
            button_text=None,
            enabled=True,
        )
    else:
        component_updates = {
            "content": content,
            "position": 10,
            "title": SECTION_TITLE,
            "subtitle": SECTION_SUBTITLE,
            "button_text": None,
            "enabled": True,
        }
        component_update_fields = []
        for field_name, value in component_updates.items():
            if getattr(component, field_name) != value:
                setattr(component, field_name, value)
                component_update_fields.append(field_name)
        if component_update_fields:
            component.save(update_fields=component_update_fields)

    Component.objects.filter(page=page).exclude(pk=component.pk).update(enabled=False)

    items = [EYEBROW_ITEM, PANEL_ITEM, *FEATURE_ITEMS, *ACTION_ITEMS]
    valid_positions = [item["position"] for item in items]
    for item in items:
        upsert_content_item(ContentItem, content, item)

    ContentItem.objects.filter(content=content).exclude(
        position__in=valid_positions
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0074_refine_how_it_works_registered_titles"),
    ]

    operations = [
        migrations.RunPython(
            seed_about_us_page,
            migrations.RunPython.noop,
        ),
    ]