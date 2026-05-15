from django.db import migrations


REPLACEMENTS = (
    (
        "თუ კურიერი მომხმარებელთან დაკავშირებას ვერ ახერხებს, მიწოდება შეიძლება ხელახლა დაიგეგმოს.",
        "თუ ჩაბარება მითითებული მონაცემებით ვერ ხერხდება, FlexDrive მომხმარებელს დაუკავშირდება და მიწოდების გაგრძელების პირობებს შეათანხმებს.",
    ),
    (
        "დეფექტიანი ან არასწორი პროდუქტის შემთხვევა ცალკე განიხილება და არ ფასდება მხოლოდ ჩვეულებრივი დაბრუნების წესით.",
        "თუ მიღებული ნივთი დაზიანებულია ან შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა, შემთხვევა ცალკე განიხილება და ჩვეულებრივი დაბრუნების წესებით არ შემოიფარგლება.",
    ),
    (
        "დეფექტიანი ან არასწორი პროდუქტის შემთხვევაში შეფასება მოხდება კონკრეტული პრობლემის ხასიათის მიხედვით.",
        "დაზიანებული ან შეკვეთასთან შეუსაბამო ნივთის შემთხვევაში შეფასება მოხდება კონკრეტული პრობლემის ხასიათის მიხედვით.",
    ),
    (
        "დეფექტიანი ან არასწორი პროდუქტის შემთხვევაში დაგვიმატეთ ვიზუალური მასალა.",
        "თუ მიღებული ნივთი დაზიანებულია ან შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა, დაგვიმატეთ ვიზუალური მასალა.",
    ),
    (
        "დეფექტის, დაზიანების ან არასწორი პროდუქტის შემთხვევაში რეკომენდებულია ფოტოს ან ვიდეოს დართვა.",
        "თუ მიღებული ნივთი დაზიანებულია ან შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა, რეკომენდებულია ფოტოს ან ვიდეოს დართვა.",
    ),
    (
        "თუ პროდუქტი დეფექტიანია, არასწორად არის მიწოდებული ან არ შეესაბამება იმ არსებით ინფორმაციას, რომელიც შეკვეთამდე იყო დადასტურებული.",
        "თუ მიღებული ნივთი დაზიანებულია, შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა ან არ შეესაბამება იმ არსებით ინფორმაციას, რომელიც შეკვეთამდე იყო დადასტურებული.",
    ),
    (
        "ნივთი არ უნდა იყოს დაზიანებული მომხმარებლის მხრიდან და სასურველია ახლდეს ყველა ის ნაწილი, შეფუთვა, სამაგრი, აქსესუარი ან დოკუმენტი, რაც შეკვეთისას მიიღო მომხმარებელმა.",
        "ნივთი არ უნდა იყოს დაზიანებული მომხმარებლის მხრიდან და აუცილებლად უნდა ახლდეს ყველა ის ნაწილი, შეფუთვა, სამაგრი, აქსესუარი ან დოკუმენტი, რაც შეკვეთისას მიიღო მომხმარებელმა.",
    ),
    (
        "დეფექტიანი ან არასწორი პროდუქტი",
        "დაზიანებული ან შეკვეთასთან შეუსაბამო პროდუქტი",
    ),
)

REVERSE_REPLACEMENTS = tuple((new, old) for old, new in reversed(REPLACEMENTS))


def apply_replacements(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    for item in ContentItem.objects.all():
        changed = False

        if item.title:
            next_title = item.title
            for old, new in REPLACEMENTS:
                next_title = next_title.replace(old, new)
            if next_title != item.title:
                item.title = next_title
                changed = True

        if item.description:
            next_description = item.description
            for old, new in REPLACEMENTS:
                next_description = next_description.replace(old, new)
            if next_description != item.description:
                item.description = next_description
                changed = True

        if item.editor:
            next_editor = item.editor
            for old, new in REPLACEMENTS:
                next_editor = next_editor.replace(old, new)
            if next_editor != item.editor:
                item.editor = next_editor
                changed = True

        if changed:
            item.save(update_fields=["title", "description", "editor", "updated_at"])


def revert_replacements(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    for item in ContentItem.objects.all():
        changed = False

        if item.title:
            next_title = item.title
            for old, new in REVERSE_REPLACEMENTS:
                next_title = next_title.replace(old, new)
            if next_title != item.title:
                item.title = next_title
                changed = True

        if item.description:
            next_description = item.description
            for old, new in REVERSE_REPLACEMENTS:
                next_description = next_description.replace(old, new)
            if next_description != item.description:
                item.description = next_description
                changed = True

        if item.editor:
            next_editor = item.editor
            for old, new in REVERSE_REPLACEMENTS:
                next_editor = next_editor.replace(old, new)
            if next_editor != item.editor:
                item.editor = next_editor
                changed = True

        if changed:
            item.save(update_fields=["title", "description", "editor", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0065_seed_order_status_page"),
    ]

    operations = [
        migrations.RunPython(apply_replacements, revert_replacements),
    ]
