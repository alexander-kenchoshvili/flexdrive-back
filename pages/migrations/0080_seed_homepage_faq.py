from django.db import migrations
from django.db.models import Max


def seed_homepage_faq(apps, schema_editor):
    alias = schema_editor.connection.alias
    Page = apps.get_model("pages", "Page")
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")

    # Remove only the unused placeholder page; never cascade through real content.
    faq_page = Page.objects.using(alias).filter(slug="faq").first()
    if faq_page:
        if (
            Component.objects.using(alias).filter(page_id=faq_page.pk).exists()
            or Page.objects.using(alias).filter(parent_id=faq_page.pk).exists()
            or ContentItem.objects.using(alias).filter(singlePageRoute_id=faq_page.pk).exists()
        ):
            raise RuntimeError("The FAQ page has linked content; review it before removing it.")
        Page.objects.using(alias).filter(pk=faq_page.pk).delete()

    main_page = Page.objects.using(alias).get(slug="main")
    component_type, _ = ComponentType.objects.using(alias).get_or_create(name="Faq")
    content, _ = Content.objects.using(alias).get_or_create(name="faq_questions")
    components = Component.objects.using(alias).filter(page_id=main_page.pk)
    if not components.filter(component_type_id=component_type.pk).exists():
        position = (components.aggregate(last=Max("position"))["last"] or 0) + 10
        Component.objects.using(alias).create(
            page_id=main_page.pk,
            component_type_id=component_type.pk,
            content_id=content.pk,
            title="ხშირად დასმული კითხვები",
            subtitle=None,
            position=position,
            enabled=True,
        )
    # Final questions/answers will be entered later in admin; no sample copy is published.


class Migration(migrations.Migration):
    dependencies = [("pages", "0079_delivery_cutoff_1300")]

    operations = [
        migrations.RunPython(seed_homepage_faq, migrations.RunPython.noop),
    ]
