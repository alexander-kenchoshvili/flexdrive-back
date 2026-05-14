from django.db import migrations


CONTENT_NAME = "terms_sections"
OLD_TEXT = (
    "<p>ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა იყოს ისეთ მდგომარეობაში, რომ შესაძლებელი იყოს მისი "
    "შემოწმება და დაბრუნების საფუძვლის შეფასება. თუ ავტონაწილი უკვე დამონტაჟდა, გამოყენების კვალი აქვს, "
    "დაზიანდა მომხმარებლის მხრიდან, აკლია კომპლექტაცია ან მისი ხელახლა გაყიდვა შეუძლებელია იმავე "
    "მდგომარეობით, დაბრუნება შეიძლება შეიზღუდოს ან დასაბრუნებელი თანხა შემცირდეს კანონით დაშვებულ "
    "ფარგლებში.</p>"
)
NEW_TEXT = (
    "<p>ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა იყოს ისეთ მდგომარეობაში, რომ შესაძლებელი იყოს მისი "
    "შემოწმება და დაბრუნების საფუძვლის შეფასება. თუ ავტონაწილი დამონტაჟდა ან გამოყენებულია იმაზე მეტად, "
    "ვიდრე მისი მდგომარეობისა და თავსებადობის შესამოწმებლად იყო საჭირო, დაბრუნების მოთხოვნა "
    "ინდივიდუალურად შეფასდება. თუ ნივთს აქვს მომხმარებლის მხრიდან დაზიანება, გამოყენების აშკარა კვალი "
    "ან აკლია კომპლექტაცია, FlexDrive მომხმარებელს აცნობებს, შესაძლებელია თუ არა ჩვეულებრივი დაბრუნება "
    "და რა პირობებით.</p>"
)


def refine_terms_installed_part_return_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    for section in ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        editor__icontains="დასაბრუნებელი თანხა შემცირდეს",
    ):
        updated_editor = section.editor.replace(OLD_TEXT, NEW_TEXT)
        if updated_editor != section.editor:
            section.editor = updated_editor
            section.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0052_fix_terms_customer_contact_grammar"),
    ]

    operations = [
        migrations.RunPython(
            refine_terms_installed_part_return_copy,
            migrations.RunPython.noop,
        ),
    ]
