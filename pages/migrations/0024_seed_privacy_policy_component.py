from django.db import migrations


COMPONENT_TYPE_NAME = "PrivacyPolicy"
CONTENT_NAME = "privacy_policy_sections"
PAGE_SLUG = "privacy-policy"
SECTION_TITLE = "Privacy Policy"
SECTION_SUBTITLE = (
    "This page stores the privacy policy content and explains how AutoMate collects, "
    "uses, and protects customer data."
)


def seed_privacy_policy_component(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    Page = apps.get_model("pages", "Page")

    page, _ = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": "Privacy Policy",
            "show_in_menu": False,
            "show_in_footer": True,
            "footer_group": "legal",
            "footer_order": 10,
            "seo_noindex": True,
        },
    )

    component_type, _ = ComponentType.objects.get_or_create(name=COMPONENT_TYPE_NAME)
    content, _ = Content.objects.get_or_create(name=CONTENT_NAME)

    component = (
        Component.objects
        .filter(page=page, component_type=component_type)
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

    update_fields = []

    if component.content_id != content.id:
        component.content = content
        update_fields.append("content")

    if component.position != 10:
        component.position = 10
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


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0023_footer_settings_and_page_footer_fields"),
    ]

    operations = [
        migrations.RunPython(seed_privacy_policy_component, migrations.RunPython.noop),
    ]
