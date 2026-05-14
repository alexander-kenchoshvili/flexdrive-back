from django.db import migrations


COMPONENT_TYPE_NAME = "PaymentMethods"
CONTENT_NAME = "payment_methods_sections"
PAGE_SLUG = "payment-methods"
PAGE_NAME = "გადახდის მეთოდები"
FOOTER_LABEL = "გადახდის მეთოდები"
SECTION_TITLE = "გადახდის მეთოდები"
SECTION_SUBTITLE = (
    "FlexDrive-ზე შეკვეთის გადახდა ხდება checkout-ში ნაჩვენები აქტიური მეთოდით. "
    "საბოლოო თანხა, გადახდის პირობები და შესაძლო დამატებითი ხარჯი მომხმარებელს "
    "შეკვეთის დადასტურებამდე ეჩვენება."
)
SEO_TITLE = "გადახდის მეთოდები | FlexDrive"
SEO_DESCRIPTION = (
    "FlexDrive-ის გადახდის მეთოდები: ნაღდი ანგარიშსწორება, ონლაინ გადახდის "
    "წესი, გადახდის დადასტურება და თანხის დაბრუნება."
)
SECTION_CONTENT_TYPE = "payment_method_section"


SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "ხელმისაწვდომი მეთოდები",
        "description": (
            "შეკვეთის გაფორმებისას მომხმარებელი ხედავს მხოლოდ იმ გადახდის მეთოდებს, "
            "რომლებიც იმ მომენტში რეალურად ხელმისაწვდომია."
        ),
        "editor": """
<p>FlexDrive-ზე აქტიურ გადახდის მეთოდად ითვლება მხოლოდ ის ვარიანტი, რომლის არჩევა და დასრულება checkout-ში შესაძლებელია. ამ ეტაპზე სრულად ხელმისაწვდომია ნაღდი ანგარიშსწორება შეკვეთის ჩაბარებისას.</p>
<p>ბარათით გადახდა, განვადება ან ნაწილ-ნაწილ გადახდა აქტიურ მეთოდად ჩაითვლება მას შემდეგ, რაც შესაბამისი ბანკი ან საგადახდო პროვაიდერი ჩაირთვება და მეთოდი checkout-ში ხელმისაწვდომი გახდება.</p>
<ul>
  <li>მომხმარებელი შეკვეთამდე ხედავს გადასახდელ საბოლოო თანხას.</li>
  <li>მიწოდების შესაძლო ხარჯი, თუ ასეთი არსებობს, checkout-ში გამოჩნდება.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "ნაღდი ანგარიშსწორება",
        "description": (
            "ნაღდი ანგარიშსწორების არჩევისას თანხის გადახდა ხდება შეკვეთის "
            "ჩაბარებისას. ამ მეთოდზე თანხა წინასწარ არ იჭრება."
        ),
        "editor": """
<p>ნაღდი ანგარიშსწორების შემთხვევაში მომხმარებელი თანხას იხდის შეკვეთის ჩაბარებისას.</p>
<ul>
  <li>გადახდა ხდება შეკვეთის ფიზიკური მიღებისას.</li>
  <li>მისამართის ან მიღების დროის ცვლილებისას მომხმარებელმა დროულად უნდა დაგვიკავშირდეს.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "ონლაინ გადახდა",
        "description": (
            "ონლაინ გადახდა დასრულებულად ჩაითვლება მხოლოდ მაშინ, როცა ბანკი ან "
            "საგადახდო პროვაიდერი ოპერაციას წარმატებულად დაადასტურებს."
        ),
        "editor": """
<p>ბარათით გადახდა შესრულდება ბანკის ან საგადახდო პროვაიდერის დაცულ გარემოში. FlexDrive არ ინახავს ბარათის სრულ მონაცემებს. შეკვეთა გადახდილად ჩაითვლება მხოლოდ მაშინ, როცა პროვაიდერი გადახდას წარმატებულად დაადასტურებს.</p>
<ul>
  <li>წარუმატებელი ან შეწყვეტილი ონლაინ გადახდა შეკვეთას გადახდილად არ აქცევს.</li>
  <li>თუ პროვაიდერი თანხის წინასწარ ავტორიზაციას უზრუნველყოფს, შეკვეთის საბოლოო შესრულებამდე შეიძლება გამოყენებულ იქნეს თანხის დროებითი დაბლოკვა და არა დაუყოვნებლივი ჩამოჭრა.</li>
  <li>განვადებისა და ნაწილ-ნაწილ გადახდის დადასტურება დამოკიდებულია შესაბამისი ბანკის ან საფინანსო პარტნიორის წესებზე.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "გაუქმება და თანხის დაბრუნება",
        "description": (
            "ბარათით ან ონლაინ მეთოდით გადახდილი შეკვეთის refund/cancel მუშავდება "
            "იმავე გადახდის არხით, რომლითაც მომხმარებელმა თანხა გადაიხადა."
        ),
        "editor": """
<p>თუ გადახდილი შეკვეთის შესრულება ვერ ხერხდება მარაგის, ტექნიკური შეცდომის ან სხვა დადასტურებული მიზეზის გამო, FlexDrive მომხმარებელს დაუკავშირდება და თანხის დაბრუნებას შესაბამისი გადახდის არხით დაამუშავებს.</p>
<p>ბარათით გადახდილი შეკვეთის დაბრუნება ან გაუქმება მუშავდება იმავე გადახდის არხით, რომლითაც თანხა გადაიხადა მომხმარებელმა. თანხის ბარათზე ასახვის დრო დამოკიდებულია ბანკზე ან საგადახდო პროვაიდერზე.</p>
<ul>
  <li>ნაღდი ანგარიშსწორებით გადახდილ შეკვეთაზე თანხის დაბრუნებისთვის შეიძლება საჭირო გახდეს საბანკო რეკვიზიტები.</li>
  <li>განვადებით ან ნაწილ-ნაწილ გადახდილი შეკვეთის გაუქმება მუშავდება შესაბამისი საფინანსო პარტნიორის წესით.</li>
  <li>დაბრუნების დეტალური პირობები აღწერილია <a href="/returns">პროდუქტისა და თანხის დაბრუნების გვერდზე</a>.</li>
</ul>
""".strip(),
    },
)


def refresh_flexdrive_payment_methods_content(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    page, _created = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": PAGE_NAME,
            "show_in_menu": False,
            "show_in_footer": True,
            "footer_group": "help",
            "footer_order": 20,
            "footer_label": FOOTER_LABEL,
            "seo_title": SEO_TITLE,
            "seo_description": SEO_DESCRIPTION,
            "seo_noindex": True,
        },
    )

    page_updates = {
        "name": PAGE_NAME,
        "show_in_menu": False,
        "show_in_footer": True,
        "footer_group": "help",
        "footer_order": 20,
        "footer_label": FOOTER_LABEL,
        "seo_title": SEO_TITLE,
        "seo_description": SEO_DESCRIPTION,
        "seo_noindex": True,
    }
    page_update_fields = []
    for field_name, value in page_updates.items():
        if getattr(page, field_name) != value:
            setattr(page, field_name, value)
            page_update_fields.append(field_name)
    if page_update_fields:
        page.save(update_fields=page_update_fields)

    component_type, _created = ComponentType.objects.get_or_create(
        name=COMPONENT_TYPE_NAME
    )
    content, _created = Content.objects.get_or_create(name=CONTENT_NAME)

    component = (
        Component.objects.filter(page=page, component_type=component_type)
        .order_by("position", "id")
        .first()
    )

    if component is None:
        component = Component.objects.create(
            page=page,
            component_type=component_type,
            content=content,
            position=10,
            title=SECTION_TITLE,
            subtitle=SECTION_SUBTITLE,
            button_text=None,
            enabled=True,
        )
    else:
        component_updates = {
            "content": content,
            "position": 10,
            "title": SECTION_TITLE,
            "subtitle": SECTION_SUBTITLE,
            "button_text": None,
            "enabled": True,
        }
        component_update_fields = []
        for field_name, value in component_updates.items():
            if getattr(component, field_name) != value:
                setattr(component, field_name, value)
                component_update_fields.append(field_name)
        if component_update_fields:
            component.save(update_fields=component_update_fields)

    valid_positions = []
    for section in SECTION_DEFINITIONS:
        valid_positions.append(section["position"])
        ContentItem.objects.update_or_create(
            content=content,
            position=section["position"],
            defaults={
                "title": section["title"],
                "description": section["description"],
                "content_type": SECTION_CONTENT_TYPE,
                "icon_svg": None,
                "editor": section["editor"],
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": None,
            },
        )

    ContentItem.objects.filter(content=content).exclude(
        position__in=valid_positions
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0058_refine_returns_customer_copy"),
    ]

    operations = [
        migrations.RunPython(
            refresh_flexdrive_payment_methods_content,
            migrations.RunPython.noop,
        ),
    ]
