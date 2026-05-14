from django.db import migrations


CONTENT_NAME = "payment_methods_sections"

REPLACEMENTS = (
    (
        "\n  <li>მომავალი გადახდის მეთოდი არ ითვლება აქტიურად, სანამ checkout-ში რეალურად არ ჩაირთვება.</li>",
        "",
    ),
    (
        "ნაღდი ანგარიშსწორების შემთხვევაში მომხმარებელი თანხას იხდის შეკვეთის ჩაბარებისას. "
        "ამ მეთოდზე FlexDrive მომხმარებლის ანგარიშიდან თანხას წინასწარ არ აჭრის.",
        "ნაღდი ანგარიშსწორების შემთხვევაში მომხმარებელი თანხას იხდის შეკვეთის ჩაბარებისას.",
    ),
    (
        "\n<p>თუ შეკვეთა ვერ დადასტურდა, გაუქმდა ან მომხმარებელმა პროდუქტი არ ჩაიბარა, ნაღდი გადახდა შესრულებულად არ ითვლება.</p>",
        "",
    ),
    (
        "\n  <li>ჩაბარებამდე ონლაინ ტრანზაქცია არ სრულდება.</li>",
        "",
    ),
    (
        "<p>ონლაინ გადახდის ჩართვის შემდეგ მომხმარებელს შეეძლება გადახდა ბარათით, განვადებით ან ნაწილ-ნაწილ გადახდის სერვისით, თუ შესაბამისი მეთოდი checkout-ში აქტიურია.</p>\n",
        "",
    ),
)


def trim_payment_methods_extra_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")
    items = ContentItem.objects.filter(content__name=CONTENT_NAME)

    for item in items:
        if not item.editor:
            continue

        next_editor = item.editor
        for old_text, new_text in REPLACEMENTS:
            next_editor = next_editor.replace(old_text, new_text)

        if next_editor != item.editor:
            item.editor = next_editor
            item.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0059_refresh_flexdrive_payment_methods_content"),
    ]

    operations = [
        migrations.RunPython(
            trim_payment_methods_extra_copy,
            migrations.RunPython.noop,
        ),
    ]
