"""Replace only obsolete public shipping copy; accepted order snapshots are historical."""

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


OLD_TIMING = ("ორშაბათიდან შაბათის ჩათვლით, 13:00 საათამდე გაფორმებულ შეკვეთას იმავე დღეს მოგაწვდით, "
              "ხოლო 13:00 საათიდან გაფორმებულ შეკვეთას — მომდევნო დღეს. კვირას მიწოდება არ ხორციელდება — "
              "შაბათს 13:00 საათიდან და კვირას გაფორმებულ შეკვეთებს ორშაბათს მოგაწვდით.")
NEW_TIMING = ("თბილისში სტანდარტული და სწრაფი მიტანა ხელმისაწვდომია სამუშაო დღეებში. "
              "იმავე დღეს სწრაფი მიტანის არჩევა შესაძლებელია ჩექაუთში მითითებულ მიღების დროში. "
              "მომსახურების ფასი და სავარაუდო მიწოდების დღე ჩანს ჩექაუთში, მისამართის მითითების შემდეგ. "
              "შაბათსა და კვირას მიწოდება არ ხორციელდება.")
NEW_SUBTITLE = ("თბილისში შეგიძლიათ აირჩიოთ სტანდარტული ან სწრაფი მიტანა სამუშაო დღეებში. "
                "ფასი და სავარაუდო დღე ჩანს ჩექაუთში. რეგიონებში მიწოდების ვადაა 3–5 სამუშაო დღე.")
NEW_FAQ = ("მიწოდების ფასი დამოკიდებულია შეფუთულ წონაზე, მისამართსა და არჩეულ მომსახურებაზე. "
           + NEW_TIMING + " რეგიონებში მიწოდების ვადაა 3–5 სამუშაო დღე, მარშრუტის გრაფიკის მიხედვით.")


def update_delivery_copy(apps, schema_editor):
    alias = schema_editor.connection.alias
    Item = apps.get_model("pages", "ContentItem")
    sections = Q(content__name="delivery_sections", content_type="delivery_section") | Q(content__name="terms_sections", content_type="terms_section")
    for item in Item.objects.using(alias).filter(sections):
        changes = {}
        for field in ("description", "editor"):
            value = getattr(item, field) or ""
            updated = value.replace("თბილისში: " + OLD_TIMING, NEW_TIMING).replace(OLD_TIMING, NEW_TIMING)
            if updated != value:
                changes[field] = updated
        if changes:
            Item.objects.using(alias).filter(pk=item.pk).update(**changes, updated_at=timezone.now())
    for item in Item.objects.using(alias).filter(content_type="faq", title="რა ღირს მიწოდება და რამდენ ხანში მივიღებ შეკვეთას?"):
        if "13:00" in ((item.description or "") + (item.editor or "")):
            Item.objects.using(alias).filter(pk=item.pk).update(description=NEW_FAQ, editor=f"<p>{NEW_FAQ}</p>", updated_at=timezone.now())
    Component = apps.get_model("pages", "Component")
    Component.objects.using(alias).filter(content__name="delivery_sections", subtitle__contains="შაბათის").update(
        subtitle=NEW_SUBTITLE, updated_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("pages", "0082_regional_delivery_3_5_days")]
    operations = [migrations.RunPython(update_delivery_copy, migrations.RunPython.noop)]
