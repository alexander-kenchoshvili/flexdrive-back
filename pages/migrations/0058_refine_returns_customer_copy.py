from django.db import migrations


PAGE_SLUG = "returns"
COMPONENT_TYPE_NAME = "Returns"
CONTENT_NAME = "returns_sections"
NEW_TITLE = "პროდუქტისა და თანხის დაბრუნება"
NEW_SEO_TITLE = "პროდუქტისა და თანხის დაბრუნება | FlexDrive"
NEW_SEO_DESCRIPTION = (
    "FlexDrive-ის დაბრუნების პირობები: დაბრუნების მოთხოვნა, პროდუქტის მდგომარეობა, "
    "დეფექტიანი ან არასწორი პროდუქტი, დაბრუნების ხარჯი და თანხის დაბრუნება."
)

REMOVE_BEFORE_SHIPPING_BULLET = (
    "\n  <li>პროდუქტის უკან გამოგზავნა შეთანხმებამდე არ არის რეკომენდებული; "
    "ჯერ უნდა მიიღოთ ინსტრუქცია ჩვენი გუნდისგან.</li>"
)
OLD_REPAIR_BULLET = (
    "<li>არასწორი ან დეფექტიანი პროდუქტის თვითნებურად შეკეთება, გადაკეთება "
    "ან დამატებითი დაზიანება შეიძლება დაბრუნების შეფასებაზე აისახოს.</li>"
)
NEW_REPAIR_BULLET = (
    "<li>თუ პროდუქტი არასწორი ან დეფექტიანია, დაგვიკავშირდით მის დამონტაჟებამდე "
    "ან შეკეთებამდე.</li>"
)
OLD_DELIVERY_DAMAGE_BULLET = (
    "<li>თუ პრობლემა მიწოდებისას შეამჩნიეთ, სასურველია კურიერის/მიწოდების "
    "ეტაპზევე დააფიქსიროთ და მოგვწეროთ.</li>"
)
NEW_DELIVERY_DAMAGE_BULLET = (
    "<li>თუ დაზიანება მიწოდებისას ჩანს, გადაიღეთ ფოტო და რაც შეიძლება მალე "
    "მოგვწერეთ.</li>"
)
OLD_DECISION_BULLET = (
    "<li>გადაწყვეტა მიიღება პროდუქტისა და მიწოდებული ინფორმაციის გადამოწმების "
    "შემდეგ.</li>"
)
NEW_DECISION_BULLET = (
    "<li>ფოტო/ვიდეო და აღწერა გვჭირდება იმის დასადგენად, პროდუქტი შეიცვლება "
    "თუ თანხა დაბრუნდება.</li>"
)
OLD_UNAGREED_SHIPPING_BULLET = (
    "<li>შეუთანხმებლად გაგზავნილი ამანათის მიღება ან ხარჯის ანაზღაურება "
    "წინასწარ დადასტურებული არ არის.</li>"
)
NEW_UNAGREED_SHIPPING_BULLET = (
    "<li>დაბრუნების ხარჯი ანაზღაურდება მხოლოდ მაშინ, თუ ეს წინასწარ "
    "დადასტურდა და მიზეზი FlexDrive-ის მხარესაა.</li>"
)


def refine_returns_customer_copy(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    Page.objects.filter(slug=PAGE_SLUG).update(
        seo_title=NEW_SEO_TITLE,
        seo_description=NEW_SEO_DESCRIPTION,
    )
    Component.objects.filter(
        page__slug=PAGE_SLUG,
        component_type__name=COMPONENT_TYPE_NAME,
    ).update(title=NEW_TITLE)

    first_section = ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        position=1,
    ).first()
    if first_section and first_section.editor:
        first_section.editor = first_section.editor.replace(
            REMOVE_BEFORE_SHIPPING_BULLET,
            "",
        )
        first_section.save(update_fields=["editor"])

    deadline_section = ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        position=2,
    ).first()
    if deadline_section:
        deadline_section.description = (
            "დისტანციურ შეკვეთაზე დაბრუნების მოთხოვნა მიიღება პროდუქტის "
            "ჩაბარებიდან 14 კალენდარული დღის განმავლობაში, კანონით "
            "გათვალისწინებული პირობებისა და გამონაკლისების დაცვით."
        )
        if deadline_section.editor:
            deadline_section.editor = (
                deadline_section.editor.replace("მიღებიდან 14", "ჩაბარებიდან 14")
                .replace("ნივთის მიღებიდან", "ნივთის ჩაბარებიდან")
                .replace("მიღების შემდეგ", "ჩაბარების შემდეგ")
            )
        deadline_section.save(update_fields=["description", "editor"])

    mismatch_section = ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        position=4,
    ).first()
    if mismatch_section and mismatch_section.editor:
        mismatch_section.editor = (
            mismatch_section.editor.replace(OLD_REPAIR_BULLET, NEW_REPAIR_BULLET)
            .replace(OLD_DELIVERY_DAMAGE_BULLET, NEW_DELIVERY_DAMAGE_BULLET)
            .replace(OLD_DECISION_BULLET, NEW_DECISION_BULLET)
        )
        mismatch_section.save(update_fields=["editor"])

    cost_section = ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        position=5,
    ).first()
    if cost_section and cost_section.editor:
        cost_section.editor = cost_section.editor.replace(
            OLD_UNAGREED_SHIPPING_BULLET,
            NEW_UNAGREED_SHIPPING_BULLET,
        )
        cost_section.save(update_fields=["editor"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0057_refine_returns_unagreed_shipping_copy"),
    ]

    operations = [
        migrations.RunPython(
            refine_returns_customer_copy,
            migrations.RunPython.noop,
        ),
    ]
