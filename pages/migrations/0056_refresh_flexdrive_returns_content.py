from django.db import migrations


COMPONENT_TYPE_NAME = "Returns"
CONTENT_NAME = "returns_sections"
PAGE_SLUG = "returns"
PAGE_NAME = "დაბრუნება"
FOOTER_LABEL = "დაბრუნება"
SECTION_TITLE = "დაბრუნება და თანხის დაბრუნება"
SECTION_SUBTITLE = (
    "ამ გვერდზე აღწერილია FlexDrive-ზე შეძენილი ავტონაწილების დაბრუნების მოთხოვნის "
    "ძირითადი წესი, ვადები, ნივთის მდგომარეობის მოთხოვნები და თანხის დაბრუნების პროცესი."
)
SEO_TITLE = "დაბრუნება და თანხის დაბრუნება | FlexDrive"
SEO_DESCRIPTION = (
    "FlexDrive-ის დაბრუნების პირობები: დაბრუნების მოთხოვნა, ნივთის მდგომარეობა, "
    "დეფექტიანი ან არასწორი პროდუქტი, დაბრუნების ხარჯი და თანხის დაბრუნება."
)
SECTION_CONTENT_TYPE = "returns_section"


SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "დაბრუნების მოთხოვნის გაგზავნა",
        "description": (
            "დაბრუნების პროცესი იწყება წერილობითი მოთხოვნით. მოთხოვნა განიხილება შეკვეთის, "
            "პროდუქტის მდგომარეობისა და დაბრუნების საფუძვლის გადამოწმების შემდეგ."
        ),
        "editor": """
<p>დაბრუნების მოთხოვნა უნდა გამოიგზავნოს ელფოსტაზე <a href="mailto:returns@flexdrive.ge">returns@flexdrive.ge</a>. წერილში მიუთითეთ შეკვეთის ნომერი, სახელი, საკონტაქტო ტელეფონი, დასაბრუნებელი პროდუქტი და მოკლე მიზეზი, რის გამოც ითხოვთ დაბრუნებას.</p>
<p>მოთხოვნის მიღება ავტომატურად არ ნიშნავს დაბრუნების დადასტურებას. FlexDrive ამოწმებს შეკვეთის მონაცემებს, ვადებს, პროდუქტის მდგომარეობას და იმას, შეესაბამება თუ არა მოთხოვნა დაბრუნების პირობებს.</p>
<ul>
  <li>შეკვეთის ნომერი და სწორი საკონტაქტო მონაცემები ამცირებს განხილვის დროს.</li>
  <li>თუ მოთხოვნა ეხება დაზიანებას, დეფექტს ან არასწორ პროდუქტს, წერილს დაურთეთ ფოტო ან ვიდეო.</li>
  <li>პროდუქტის უკან გამოგზავნა შეთანხმებამდე არ არის რეკომენდებული; ჯერ უნდა მიიღოთ ინსტრუქცია ჩვენი გუნდისგან.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "ჩვეულებრივი დაბრუნების ვადა",
        "description": (
            "დისტანციურ შეკვეთაზე დაბრუნების მოთხოვნა მიიღება პროდუქტის მიღებიდან "
            "14 კალენდარული დღის განმავლობაში, კანონით გათვალისწინებული პირობებისა და გამონაკლისების დაცვით."
        ),
        "editor": """
<p>ონლაინ შეძენილ პროდუქტზე მომხმარებელს შეუძლია დაბრუნების მოთხოვნის გამოგზავნა პროდუქტის მიღებიდან 14 კალენდარული დღის განმავლობაში, თუ დაბრუნება არ ექვემდებარება კანონით ან ამ გვერდზე აღწერილ გამონაკლისს.</p>
<p>ვადის დაცვას ამოწმებს FlexDrive შეკვეთისა და მიწოდების მონაცემების მიხედვით. თუ მოთხოვნა ვადის გასვლის შემდეგ გაიგზავნა, ჩვეულებრივი დაბრუნება შეიძლება არ დადასტურდეს.</p>
<ul>
  <li>14-დღიანი ვადა ითვლება მომხმარებლის ან მის მიერ განსაზღვრული მიმღების მიერ ნივთის მიღებიდან.</li>
  <li>დაბრუნების შესახებ შეტყობინება ამ ვადის ამოწურვამდე უნდა გამოგვიგზავნოთ.</li>
  <li>დეფექტიანი ან არასწორი პროდუქტის შემთხვევა ცალკე განიხილება და არ ფასდება მხოლოდ ჩვეულებრივი დაბრუნების წესით.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "პროდუქტის მდგომარეობა",
        "description": (
            "ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა იყოს შემოწმებადი, დაუზიანებელი და სრულ "
            "კომპლექტაციაში. დამონტაჟებული ან გამოყენებული ავტონაწილი ინდივიდუალურად ფასდება."
        ),
        "editor": """
<p>ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა დაბრუნდეს ისეთ მდგომარეობაში, რომ შესაძლებელი იყოს მისი შემოწმება და დაბრუნების საფუძვლის შეფასება. ნივთი არ უნდა იყოს დაზიანებული მომხმარებლის მხრიდან და სასურველია ახლდეს ყველა ის ნაწილი, შეფუთვა, სამაგრი, აქსესუარი ან დოკუმენტი, რაც შეკვეთისას მიიღო მომხმარებელმა.</p>
<p>თუ ავტონაწილი დამონტაჟდა, გამოყენებულია, აქვს ექსპლუატაციის კვალი, დაზიანება ან აკლია კომპლექტაცია, დაბრუნების მოთხოვნა ინდივიდუალურად შეფასდება. ასეთ შემთხვევაში FlexDrive მომხმარებელს აცნობებს, შესაძლებელია თუ არა ჩვეულებრივი დაბრუნება და რა პირობებით.</p>
<ul>
  <li>პროდუქტის შემოწმება არ უნდა გასცდეს იმ ფარგლებს, რაც საჭიროა მისი მდგომარეობისა და თავსებადობის დასადგენად.</li>
  <li>მცირე ნაწილები, სამაგრები და შეფუთვა შეინახეთ, სანამ საბოლოოდ გადაწყვეტთ პროდუქტის დატოვებას.</li>
  <li>თუ პროდუქტი უკვე დამონტაჟდა მანქანაზე, დაბრუნების მოთხოვნაში ეს ინფორმაცია უნდა მიუთითოთ.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "დეფექტიანი ან არასწორი პროდუქტი",
        "description": (
            "თუ პროდუქტი დაზიანებულია, დეფექტიანია ან შეკვეთას არ შეესაბამება, მოთხოვნა "
            "განიხილება პრიორიტეტულად და საჭიროებს პრობლემის აღწერას ან ვიზუალურ მასალას."
        ),
        "editor": """
<p>თუ მიიღეთ დაზიანებული, დეფექტიანი ან შეკვეთასთან შეუსაბამო პროდუქტი, დაგვიკავშირდით რაც შეიძლება მალე. ასეთ შემთხვევაში წერილში მიუთითეთ შეკვეთის ნომერი, აღწერეთ პრობლემა და დაურთეთ ფოტო ან ვიდეო, სადაც საკითხი მკაფიოდ ჩანს.</p>
<p>გადამოწმების შემდეგ FlexDrive მომხმარებელს შესთავაზებს შესაბამის გადაწყვეტას კონკრეტული შემთხვევის მიხედვით: პროდუქტის შეცვლას, ალტერნატიულ პროდუქტს ან თანხის დაბრუნებას. თუ პრობლემა გამოწვეულია ჩვენი შეცდომით, დაბრუნების საჭირო პირდაპირ ხარჯს FlexDrive ფარავს.</p>
<ul>
  <li>არასწორი ან დეფექტიანი პროდუქტის თვითნებურად შეკეთება, გადაკეთება ან დამატებითი დაზიანება შეიძლება დაბრუნების შეფასებაზე აისახოს.</li>
  <li>თუ პრობლემა მიწოდებისას შეამჩნიეთ, სასურველია კურიერის/მიწოდების ეტაპზევე დააფიქსიროთ და მოგვწეროთ.</li>
  <li>გადაწყვეტა მიიღება პროდუქტისა და მიწოდებული ინფორმაციის გადამოწმების შემდეგ.</li>
</ul>
""".strip(),
    },
    {
        "position": 5,
        "title": "დაბრუნების ხარჯი",
        "description": (
            "ჩვეულებრივი დაბრუნებისას პროდუქტის უკან გამოგზავნის პირდაპირი ხარჯი მომხმარებელზეა, "
            "ხოლო ჩვენი შეცდომის ან დეფექტის დადასტურებისას ხარჯს FlexDrive ფარავს."
        ),
        "editor": """
<p>თუ დაბრუნება ხდება ჩვეულებრივი წესით და პროდუქტი არ არის დეფექტიანი ან არასწორად მიწოდებული, პროდუქტის უკან გამოგზავნის პირდაპირი ხარჯი ეკისრება მომხმარებელს. დაბრუნების არხი და მისამართი წინასწარ უნდა შეთანხმდეს FlexDrive-თან.</p>
<p>თუ დადასტურდა, რომ მომხმარებელმა მიიღო არასწორი, დაზიანებული ან შეკვეთასთან შეუსაბამო პროდუქტი და მიზეზი FlexDrive-ის მხარესაა, შესაბამის დაბრუნების ხარჯს FlexDrive ფარავს ან მომხმარებელს აძლევს ცალკე ინსტრუქციას, როგორ მოხდეს პროდუქტის დაბრუნება.</p>
<ul>
  <li>შეუთანხმებლად გაგზავნილი ამანათის მიღება ან ხარჯის ანაზღაურება წინასწარ დადასტურებული არ არის.</li>
  <li>გაგზავნამდე მომხმარებელმა უნდა მიიღოს დასაბრუნებელი მისამართი და ინსტრუქცია.</li>
  <li>დაბრუნებისას პროდუქტი უნდა შეფუთოთ ისე, რომ ტრანსპორტირებისას დამატებით არ დაზიანდეს.</li>
</ul>
""".strip(),
    },
    {
        "position": 6,
        "title": "თანხის დაბრუნება",
        "description": (
            "თანხის დაბრუნება მუშავდება დაბრუნების დადასტურების, პროდუქტის მიღების ან "
            "გაგზავნის დამადასტურებელი ინფორმაციის გადამოწმების შემდეგ."
        ),
        "editor": """
<p>თანხის დაბრუნება მუშავდება მას შემდეგ, რაც დაბრუნების მოთხოვნა დადასტურდება და FlexDrive მიიღებს დაბრუნებულ პროდუქტს ან მომხმარებლისგან მიიღებს პროდუქტის გამოგზავნის დამადასტურებელ ინფორმაციას, თუ კონკრეტულ შემთხვევაში სხვა რამ არ არის შეთანხმებული.</p>
<p>დადასტურებული დაბრუნების შემთხვევაში თანხა ბრუნდება იმავე გადახდის არხით, რომლითაც შეკვეთა გადაიხადა მომხმარებელმა, თუ სხვა მეთოდი წინასწარ არ შეთანხმდა და მომხმარებელს დამატებითი ხარჯი არ წარმოეშობა. ონლაინ გადახდისას თანხის ანგარიშზე ასახვის დრო შეიძლება დამოკიდებული იყოს ბანკზე ან საგადახდო პროვაიდერზე.</p>
<ul>
  <li>ნაღდი ანგარიშსწორებით მიღებულ შეკვეთაზე შეიძლება საჭირო გახდეს საბანკო რეკვიზიტების მოწოდება.</li>
  <li>ბარათით, განვადებით ან ნაწილ-ნაწილ გადახდილ შეკვეთებზე refund/cancel მუშავდება შესაბამისი გადახდის არხის წესებით.</li>
  <li>დაბრუნებასთან დაკავშირებული შეკითხვებისთვის გამოიყენეთ <a href="mailto:returns@flexdrive.ge">returns@flexdrive.ge</a>.</li>
</ul>
""".strip(),
    },
)


def refresh_flexdrive_returns_content(apps, schema_editor):
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
            "footer_order": 30,
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
        "footer_order": 30,
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
        ("pages", "0055_remove_terms_warranty_reference"),
    ]

    operations = [
        migrations.RunPython(
            refresh_flexdrive_returns_content,
            migrations.RunPython.noop,
        ),
    ]
