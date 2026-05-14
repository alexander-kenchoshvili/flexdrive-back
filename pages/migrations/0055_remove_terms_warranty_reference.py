from django.db import migrations


CONTENT_NAME = "terms_sections"
OLD_TEXT = (
    "B2B შეკვეთებზე შეიძლება მოქმედებდეს ცალკე შეთავაზება, ინვოისი, გადახდის ვადა, "
    "მიწოდების პირობა, საგარანტიო დოკუმენტი ან წერილობითი შეთანხმება."
)
NEW_TEXT = (
    "B2B შეკვეთებზე შეიძლება მოქმედებდეს ცალკე შეთავაზება, ინვოისი, გადახდის ვადა, "
    "მიწოდების პირობა ან წერილობითი შეთანხმება."
)


def remove_terms_warranty_reference(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    for section in ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        editor__icontains="საგარანტიო დოკუმენტი",
    ):
        updated_editor = section.editor.replace(OLD_TEXT, NEW_TEXT)
        if updated_editor != section.editor:
            section.editor = updated_editor
            section.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0054_remove_terms_b2b_future_feature_bullet"),
    ]

    operations = [
        migrations.RunPython(
            remove_terms_warranty_reference,
            migrations.RunPython.noop,
        ),
    ]
