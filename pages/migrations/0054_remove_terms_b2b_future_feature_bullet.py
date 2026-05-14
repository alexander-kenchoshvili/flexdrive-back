from django.db import migrations


CONTENT_NAME = "terms_sections"
TEXT_TO_REMOVE = (
    "  <li>იურიდიული პირებისთვის განკუთვნილი ფუნქციები საიტზე ეტაპობრივად დაემატება.</li>\n"
)


def remove_terms_b2b_future_feature_bullet(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    for section in ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        editor__icontains="იურიდიული პირებისთვის განკუთვნილი ფუნქციები",
    ):
        updated_editor = section.editor.replace(TEXT_TO_REMOVE, "")
        if updated_editor != section.editor:
            section.editor = updated_editor
            section.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0053_refine_terms_installed_part_return_copy"),
    ]

    operations = [
        migrations.RunPython(
            remove_terms_b2b_future_feature_bullet,
            migrations.RunPython.noop,
        ),
    ]
