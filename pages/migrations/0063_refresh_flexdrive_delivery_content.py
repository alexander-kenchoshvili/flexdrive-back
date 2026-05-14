from django.db import migrations


COMPONENT_TYPE_NAME = "Delivery"
CONTENT_NAME = "delivery_sections"
PAGE_SLUG = "delivery"
PAGE_NAME = "მიწოდება"
FOOTER_LABEL = "მიწოდება"
SECTION_TITLE = "მიწოდების პირობები"
SECTION_SUBTITLE = (
    "FlexDrive-ზე მიწოდების ვადა დამოკიდებულია შეკვეთის დადასტურებაზე, "
    "მისამართზე და კურიერის სამუშაო პროცესზე. თბილისში სტანდარტული ვადაა "
    "1-2 სამუშაო დღე, რეგიონებში - 4-5 სამუშაო დღე."
)
SEO_TITLE = "მიწოდების პირობები | FlexDrive"
SEO_DESCRIPTION = (
    "FlexDrive-ის მიწოდების პირობები: შეკვეთის დადასტურება, მიწოდების ვადები "
    "თბილისსა და რეგიონებში, მისამართის სიზუსტე და მხარდაჭერა."
)
SECTION_CONTENT_TYPE = "delivery_section"


SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "როდის იწყება მიწოდების ვადა",
        "description": (
            "მიწოდების ვადა ითვლება შეკვეთის დადასტურებიდან, მას შემდეგ რაც "
            "შეკვეთის მონაცემები, მარაგი და მიწოდების მისამართი გადამოწმებულია."
        ),
        "editor": """
<p>შეკვეთის გაგზავნის შემდეგ FlexDrive ამოწმებს შეკვეთის მონაცემებს, პროდუქტის ხელმისაწვდომობას, საკონტაქტო ნომერს და მიწოდების მისამართს. მიწოდების ვადის ათვლა იწყება შეკვეთის დადასტურებიდან.</p>
<p>თუ შეკვეთას სჭირდება მისამართის, ტელეფონის, პროდუქტის ან გადახდის დეტალის დაზუსტება, მიწოდების ვადა აითვლება მას შემდეგ, რაც საჭირო ინფორმაცია დადასტურდება.</p>
<ul>
  <li>ნაღდი ანგარიშსწორებისას შეკვეთა მუშავდება დადასტურებული მონაცემების მიხედვით.</li>
  <li>ონლაინ გადახდისას შეკვეთის დამუშავება დამოკიდებულია გადახდის წარმატებულ დადასტურებაზეც.</li>
  <li>მიწოდების შესაძლო ხარჯი, თუ ასეთი არსებობს, checkout-ში გამოჩნდება შეკვეთის დადასტურებამდე.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "მიწოდების ვადები",
        "description": (
            "თბილისში მიწოდების სტანდარტული ვადაა 1-2 სამუშაო დღე, რეგიონებში - "
            "4-5 სამუშაო დღე შეკვეთის დადასტურებიდან."
        ),
        "editor": """
<p>დადასტურებული შეკვეთის მიწოდება თბილისში ჩვეულებრივ ხორციელდება 1-2 სამუშაო დღეში. რეგიონებში მიწოდების სტანდარტული ვადაა 4-5 სამუშაო დღე.</p>
<p>ზუსტი დრო დამოკიდებულია მისამართზე, კურიერის მარშრუტზე, დასვენების დღეებზე და მიმდინარე დატვირთვაზე. თუ კონკრეტულ შეკვეთაზე სხვა ვადა იქნება საჭირო, მომხმარებელს დამატებით დავუკავშირდებით.</p>
<ul>
  <li>თბილისი: 1-2 სამუშაო დღე.</li>
  <li>რეგიონები: 4-5 სამუშაო დღე.</li>
  <li>ვადები ითვლება შეკვეთის დადასტურებიდან.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "მისამართი და ჩაბარება",
        "description": (
            "სწორი მისამართი და აქტიური ტელეფონის ნომერი აუცილებელია შეკვეთის დროულად "
            "ჩასაბარებლად."
        ),
        "editor": """
<p>შეკვეთის გაფორმებისას მიუთითეთ სრული მისამართი, აქტიური ტელეფონის ნომერი და საჭიროების შემთხვევაში დამატებითი მითითება კურიერისთვის. არაზუსტი ან არასრული მონაცემები მიწოდებას აფერხებს.</p>
<p>შეკვეთის ჩაბარებისას მომხმარებელმა უნდა გადაამოწმოს ამანათის ვიზუალური მდგომარეობა. თუ შეფუთვა ან პროდუქტი დაზიანებული ჩანს, გადაიღეთ ფოტო და რაც შეიძლება მალე დაგვიკავშირდით.</p>
<ul>
  <li>მისამართის ცვლილებისას მოგვწერეთ შეკვეთის გაგზავნამდე ან რაც შეიძლება სწრაფად.</li>
  <li>თუ კურიერი მომხმარებელთან დაკავშირებას ვერ ახერხებს, მიწოდება შეიძლება ხელახლა დაიგეგმოს.</li>
  <li>სტუმრის შეკვეთაზე სტატუსის დასაზუსტებლად საჭიროა შეკვეთის ნომერი და საკონტაქტო ტელეფონი.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "შეფერხებები და დახმარება",
        "description": (
            "მიწოდება შეიძლება გადაიწიოს ამინდის, დასვენების დღეების, მაღალი დატვირთვის, "
            "კურიერის შეზღუდვის ან მონაცემების დაზუსტების საჭიროების გამო."
        ),
        "editor": """
<p>FlexDrive ცდილობს დაიცვას მითითებული ვადები, თუმცა მიწოდება შეიძლება გადაიწიოს ამინდის, დასვენების დღეების, მაღალი დატვირთვის, სატრანსპორტო შეზღუდვის, კურიერის სამუშაო გრაფიკის ან შეკვეთის მონაცემების დაზუსტების საჭიროების გამო.</p>
<p>თუ შეკვეთის სტატუსის დაზუსტება გჭირდებათ, დაგვიკავშირდით შეკვეთის ნომრით. რეგისტრირებულ მომხმარებელს შეკვეთების ისტორიის ნახვა შეუძლია საკუთარ პროფილშიც.</p>
<ul>
  <li>ელფოსტა: <a href="mailto:support@flexdrive.ge">support@flexdrive.ge</a></li>
  <li>ტელეფონი: <a href="tel:+995555010203">+995 555 01 02 03</a></li>
  <li>შეკვეთის ნომერი დაგვეხმარება სტატუსის სწრაფად მოძებნაში.</li>
</ul>
""".strip(),
    },
)


def refresh_flexdrive_delivery_content(apps, schema_editor):
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
            "footer_order": 10,
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
        "footer_order": 10,
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
        ("pages", "0062_refine_privacy_policy_copy"),
    ]

    operations = [
        migrations.RunPython(
            refresh_flexdrive_delivery_content,
            migrations.RunPython.noop,
        ),
    ]
