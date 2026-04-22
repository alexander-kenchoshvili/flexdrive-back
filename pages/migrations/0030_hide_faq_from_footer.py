from django.db import migrations


PAGE_SLUG = "faq"
PAGE_NAME = "ხშირად დასმული კითხვები"
SEO_TITLE = "ხშირად დასმული კითხვები | AutoMate"
SEO_DESCRIPTION = "AutoMate-ის ხშირად დასმული კითხვები."


def hide_faq_from_footer(apps, schema_editor):
    Page = apps.get_model("pages", "Page")

    page, _ = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": PAGE_NAME,
            "show_in_menu": False,
            "show_in_footer": False,
            "footer_group": "navigation",
            "footer_order": 40,
            "seo_title": SEO_TITLE,
            "seo_description": SEO_DESCRIPTION,
            "seo_noindex": True,
        },
    )

    update_fields = []

    if page.name != PAGE_NAME:
        page.name = PAGE_NAME
        update_fields.append("name")
    if page.show_in_footer:
        page.show_in_footer = False
        update_fields.append("show_in_footer")
    if page.seo_title != SEO_TITLE:
        page.seo_title = SEO_TITLE
        update_fields.append("seo_title")
    if page.seo_description != SEO_DESCRIPTION:
        page.seo_description = SEO_DESCRIPTION
        update_fields.append("seo_description")
    if not page.seo_noindex:
        page.seo_noindex = True
        update_fields.append("seo_noindex")

    if update_fields:
        page.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0029_payment_methods_georgian_content"),
    ]

    operations = [
        migrations.RunPython(
            hide_faq_from_footer,
            migrations.RunPython.noop,
        ),
    ]
