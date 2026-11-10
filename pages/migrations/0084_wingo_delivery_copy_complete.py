"""Complete the public delivery copy, including compact descriptions used by cards."""

from importlib import import_module

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


previous = import_module("pages.migrations.0083_wingo_delivery_choices_copy")
OLD_SHORT = ("თბილისში 13:00 საათამდე გაფორმებული შეკვეთა იმავე დღეს მოგეწოდებათ, "
             "ხოლო 13:00 საათიდან — მომდევნო დღეს, კვირის გარდა. შაბათს 13:00 საათიდან "
             "და კვირას გაფორმებული შეკვეთები ორშაბათს მოგეწოდებათ.")
NEW_TIMING = ("თბილისში სტანდარტული მიტანის სავარაუდო ვადაა 1–2 სამუშაო დღე. "
              "სწრაფი მიტანის არჩევისა და სამუშაო დღეს 12:30-მდე გადახდისას ნივთს იმავე დღეს მოგაწვდით; "
              "12:30-დან ან შაბათ-კვირას გადახდისას — მომდევნო სამუშაო დღეს. "
              "შაბათსა და კვირას მიწოდება არ ხორციელდება.")
NEW_SUBTITLE = ("თბილისში სტანდარტული მიტანა — 1–2 სამუშაო დღეში; სწრაფი — იმავე ან მომდევნო სამუშაო დღეს. "
                "რეგიონებში — 3–5 სამუშაო დღეში. მიტანის ფასი ჩანს ჩექაუთში.")
NEW_FAQ = ("მიწოდების ფასი დამოკიდებულია შეფუთულ წონაზე, მისამართსა და არჩეულ მომსახურებაზე და ჩანს ჩექაუთში. "
           + NEW_TIMING + " რეგიონებში მიწოდების სავარაუდო ვადაა 3–5 სამუშაო დღე, მარშრუტის გრაფიკის მიხედვით.")
OLD_INTRO = ("თბილისში მიწოდების დღე განისაზღვრება შეკვეთის გაფორმების დროის მიხედვით, "
             "ხოლო რეგიონებში მიწოდების ვადა ითვლება შეკვეთის დადასტურებიდან.")
NEW_INTRO = ("თბილისში მიწოდების ვადა დამოკიდებულია არჩეულ მომსახურებასა და გადახდის დროზე, "
             "ხოლო რეგიონებში — დასახლების მომსახურების გრაფიკზე.")
OLD_DETAIL_INTRO = ("თბილისში მიწოდების დღე განისაზღვრება შეკვეთის გაფორმების დროის მიხედვით, "
                    "ქვემოთ მოცემული გრაფიკის შესაბამისად. რეგიონებში მიწოდების ვადის ათვლა იწყება შეკვეთის დადასტურებიდან.")


def update_delivery_copy(apps, schema_editor):
    alias = schema_editor.connection.alias
    Item = apps.get_model("pages", "ContentItem")
    sections = (Q(content__name="delivery_sections", content_type="delivery_section") |
                Q(content__name="terms_sections", content_type="terms_section"))
    replacements = [("თბილისში: " + previous.OLD_TIMING, NEW_TIMING),
                    (previous.OLD_TIMING, NEW_TIMING), (previous.NEW_TIMING, NEW_TIMING),
                    (OLD_SHORT, NEW_TIMING), (OLD_INTRO, NEW_INTRO), (OLD_DETAIL_INTRO, NEW_INTRO)]
    # Older installations may still contain the original 14:00 copy.
    replacements += [(old.replace("13:00", "14:00"), new)
                     for old, new in replacements if "13:00" in old]
    for item in Item.objects.using(alias).filter(sections):
        changes = {}
        for field in ("description", "editor"):
            value = getattr(item, field) or ""
            updated = value
            for old, new in replacements:
                updated = updated.replace(old, new)
            if updated != value:
                changes[field] = updated
        if changes:
            Item.objects.using(alias).filter(pk=item.pk).update(**changes, updated_at=timezone.now())
    for item in Item.objects.using(alias).filter(content_type="faq", title="რა ღირს მიწოდება და რამდენ ხანში მივიღებ შეკვეთას?"):
        changes = {}
        for field in ("description", "editor"):
            value = getattr(item, field) or ""
            if previous.NEW_FAQ in value:
                changes[field] = value.replace(previous.NEW_FAQ, NEW_FAQ)
        if changes:
            Item.objects.using(alias).filter(pk=item.pk).update(**changes, updated_at=timezone.now())
    Component = apps.get_model("pages", "Component")
    Component.objects.using(alias).filter(content__name="delivery_sections", subtitle=previous.NEW_SUBTITLE).update(
        subtitle=NEW_SUBTITLE, updated_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("pages", "0083_wingo_delivery_choices_copy")]
    operations = [migrations.RunPython(update_delivery_copy, migrations.RunPython.noop)]
