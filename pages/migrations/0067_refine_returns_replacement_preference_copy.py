from django.db import migrations


CONTENT_NAME = "returns_sections"
SECTION_POSITION = 4

OLD_DECISION_PARAGRAPH = (
    "<p>გადამოწმების შემდეგ FlexDrive მომხმარებელს შესთავაზებს შესაბამის გადაწყვეტას "
    "კონკრეტული შემთხვევის მიხედვით: პროდუქტის შეცვლას, ალტერნატიულ პროდუქტს ან "
    "თანხის დაბრუნებას. თუ პრობლემა გამოწვეულია ჩვენი შეცდომით, დაბრუნების საჭირო "
    "პირდაპირ ხარჯს FlexDrive ფარავს.</p>"
)
NEW_DECISION_PARAGRAPH = (
    "<p>გადამოწმების შემდეგ FlexDrive მომხმარებელს შესთავაზებს შესაბამის გადაწყვეტილებას "
    "კონკრეტული შემთხვევის მიხედვით: პროდუქტის შეცვლას ან ალტერნატიული პროდუქტის "
    "მიწოდებას. თუ პრობლემა გამოწვეულია ჩვენი შეცდომით, შეცვლასთან დაკავშირებულ "
    "საჭირო პირდაპირ ხარჯს FlexDrive ფარავს.</p>"
)
OLD_EVIDENCE_BULLET = (
    "<li>ფოტო/ვიდეო და აღწერა გვჭირდება იმის დასადგენად, პროდუქტი შეიცვლება "
    "თუ თანხა დაბრუნდება.</li>"
)
NEW_EVIDENCE_BULLET = (
    "<li>ფოტო/ვიდეო და მოკლე აღწერა დაგვეხმარება მდგომარეობის შეფასებაში და "
    "იმის დადგენაში, შესაძლებელია თუ არა პროდუქტის შეცვლა.</li>"
)

REPLACEMENTS = (
    (OLD_DECISION_PARAGRAPH, NEW_DECISION_PARAGRAPH),
    (OLD_EVIDENCE_BULLET, NEW_EVIDENCE_BULLET),
)
REVERSE_REPLACEMENTS = tuple((new, old) for old, new in reversed(REPLACEMENTS))


def update_returns_replacement_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    section = ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        position=SECTION_POSITION,
    ).first()
    if not section or not section.editor:
        return

    next_editor = section.editor
    for old, new in REPLACEMENTS:
        next_editor = next_editor.replace(old, new)

    if next_editor != section.editor:
        section.editor = next_editor
        section.save(update_fields=["editor", "updated_at"])


def revert_returns_replacement_copy(apps, schema_editor):
    ContentItem = apps.get_model("pages", "ContentItem")

    section = ContentItem.objects.filter(
        content__name=CONTENT_NAME,
        position=SECTION_POSITION,
    ).first()
    if not section or not section.editor:
        return

    next_editor = section.editor
    for old, new in REVERSE_REPLACEMENTS:
        next_editor = next_editor.replace(old, new)

    if next_editor != section.editor:
        section.editor = next_editor
        section.save(update_fields=["editor", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0066_refine_legal_return_delivery_copy"),
    ]

    operations = [
        migrations.RunPython(
            update_returns_replacement_copy,
            revert_returns_replacement_copy,
        ),
    ]
