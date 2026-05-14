from django.db import migrations


CONTENT_NAME = "privacy_policy_sections"
OLD_WORKS_COPY = "სწორად იმუშაოს"
NEW_WORKS_COPY = "სწორად მუშაობდეს"
REMOVE_MARKETING_RIGHT_BULLET = (
    "\n  <li>შეგიძლიათ გააპროტესტოთ პირდაპირი მარკეტინგი ან გამოიხმოთ თანხმობა "
    "იმ დამუშავებაზე, რომელიც თანხმობას ეფუძნება.</li>"
)


def refine_privacy_policy_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")
    items = ContentItem.objects.filter(content__name=CONTENT_NAME)

    for item in items:
        if not item.editor:
            continue

        next_editor = item.editor.replace(OLD_WORKS_COPY, NEW_WORKS_COPY)
        next_editor = next_editor.replace(REMOVE_MARKETING_RIGHT_BULLET, "")

        if next_editor != item.editor:
            item.editor = next_editor
            item.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0061_refresh_flexdrive_privacy_policy_content"),
    ]

    operations = [
        migrations.RunPython(
            refine_privacy_policy_copy,
            migrations.RunPython.noop,
        ),
    ]
