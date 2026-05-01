from django.db import migrations


CONTENT_NAME = "how_it_works_main"
OLD_TITLE = "დაამატე კალათაში"
NEW_TITLE = "აირჩიე ყიდვის გზა"
NEW_DESCRIPTION = (
    "ერთი ნივთისთვის გამოიყენე ახლავე ყიდვა, რამდენიმე ნაწილისთვის კი კალათაში შეაგროვე."
)


def refine_guest_choice_step(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        content_type="guest_step",
        title=OLD_TITLE,
        position=101,
    ).update(
        title=NEW_TITLE,
        description=NEW_DESCRIPTION,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0044_refresh_how_it_works_component"),
    ]

    operations = [
        migrations.RunPython(refine_guest_choice_step, migrations.RunPython.noop),
    ]
