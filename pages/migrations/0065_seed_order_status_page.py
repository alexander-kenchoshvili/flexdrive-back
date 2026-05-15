from django.db import migrations


COMPONENT_TYPE_NAME = "OrderStatus"
CONTENT_NAME = "order_status_content"
PAGE_SLUG = "order-status"
PAGE_NAME = "შეკვეთის სტატუსი"
FOOTER_LABEL = "შეკვეთის სტატუსი"
SECTION_TITLE = "შეკვეთის სტატუსი"
SECTION_SUBTITLE = (
    "შეიყვანეთ შეკვეთის ნომერი და ტელეფონის ნომერი, რომ ნახოთ შეკვეთის "
    "მიმდინარე მდგომარეობა."
)
SEO_TITLE = "შეკვეთის სტატუსის შემოწმება | FlexDrive"
SEO_DESCRIPTION = (
    "FlexDrive-ზე სტუმრის შეკვეთის სტატუსის შემოწმება შეკვეთის ნომრით და "
    "ტელეფონის ნომრით."
)


def seed_order_status_page(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    Page = apps.get_model("pages", "Page")

    page, _created = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": PAGE_NAME,
            "show_in_menu": False,
            "show_in_footer": True,
            "footer_group": "help",
            "footer_order": 40,
            "footer_label": FOOTER_LABEL,
            "seo_title": SEO_TITLE,
            "seo_description": SEO_DESCRIPTION,
            "seo_noindex": True,
        },
    )

    page_updates = {
        "name": PAGE_NAME,
        "show_in_menu": False,
        "show_in_footer": True,
        "footer_group": "help",
        "footer_order": 40,
        "footer_label": FOOTER_LABEL,
        "seo_title": SEO_TITLE,
        "seo_description": SEO_DESCRIPTION,
        "seo_noindex": True,
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
        Component.objects.create(
            page=page,
            component_type=component_type,
            content=content,
            position=10,
            title=SECTION_TITLE,
            subtitle=SECTION_SUBTITLE,
            button_text=None,
            enabled=True,
        )
        return

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


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0064_remove_contact_support_footer_settings_copy"),
    ]

    operations = [
        migrations.RunPython(
            seed_order_status_page,
            migrations.RunPython.noop,
        ),
    ]
