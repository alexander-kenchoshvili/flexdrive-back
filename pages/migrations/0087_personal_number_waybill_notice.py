from django.db import migrations
from django.db.models import Max


SECTION_SLUG = "transport-waybill-buyer-details"
SECTION_HTML = """
<p>ფიზიკური პირის შეკვეთის გაფორმებისას ვითხოვთ 11-ნიშნა პირად ნომერს ტრანსპორტირების ზედნადების მოსამზადებლად. იურიდიული პირის შემთხვევაში ვიღებთ კომპანიის დასახელებასა და საიდენტიფიკაციო კოდს, ასევე საკონტაქტო პირის სახელს, გვარსა და მიწოდების მისამართს.</p>
<p>ეს მონაცემები ინახება შეკვეთასთან და ხელმისაწვდომია შესაბამისი წვდომის მქონე თანამშრომლებისა და ბუღალტრისთვის შეკვეთისა და ტრანსპორტირების დოკუმენტების დასამუშავებლად. პირად ნომერს არ ვიყენებთ ანალიტიკისა და მარკეტინგისთვის.</p>
""".strip()


def add_waybill_notice(apps, schema_editor):
    alias = schema_editor.connection.alias
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    content = Content.objects.using(alias).filter(name="privacy_policy_sections").first()
    if content is None:
        return
    items = ContentItem.objects.using(alias).filter(content=content)
    if items.filter(slug=SECTION_SLUG).exists():
        return
    position = (items.aggregate(last=Max("position"))["last"] or 0) + 1
    items.create(content=content, slug=SECTION_SLUG, position=position, content_type="policy_section",
        title="პირადი ნომერი და ტრანსპორტირების ზედნადები",
        description="რა მიზნით ვითხოვთ პირად ნომერსა და კომპანიის საიდენტიფიკაციო მონაცემებს.",
        editor=SECTION_HTML, icon_svg=None)


class Migration(migrations.Migration):
    dependencies = [("pages", "0086_footersettings_tiktok_url")]
    operations = [migrations.RunPython(add_waybill_notice, migrations.RunPython.noop)]
