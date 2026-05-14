from django.db import migrations


COMPONENT_TYPE_NAME = "PrivacyPolicy"
CONTENT_NAME = "privacy_policy_sections"
PAGE_SLUG = "privacy-policy"
PAGE_NAME = "კონფიდენციალურობის პოლიტიკა"
FOOTER_LABEL = "კონფიდენციალურობა"
SECTION_TITLE = "კონფიდენციალურობის პოლიტიკა"
SECTION_SUBTITLE = (
    "ამ გვერდზე მოკლედ არის აღწერილი რა მონაცემებს ამუშავებს FlexDrive, "
    "რისთვის ვიყენებთ მათ, ვის შეიძლება გადაეცეს ინფორმაცია და როგორ შეგიძლიათ "
    "თქვენი უფლებებით სარგებლობა."
)
SEO_TITLE = "კონფიდენციალურობის პოლიტიკა | FlexDrive"
SEO_DESCRIPTION = (
    "FlexDrive-ის კონფიდენციალურობის პოლიტიკა: პერსონალური მონაცემები, "
    "ქუქები, ანალიტიკა, მარკეტინგი, გადახდის პროვაიდერები და მომხმარებლის უფლებები."
)
SECTION_CONTENT_TYPE = "policy_section"


SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "რა მონაცემებს ვამუშავებთ",
        "description": (
            "ვაგროვებთ იმ ინფორმაციას, რომელიც საჭიროა ანგარიშის, კალათის, შეკვეთის, "
            "მიწოდების, მხარდაჭერისა და უსაფრთხოებისთვის."
        ),
        "editor": """
<p>FlexDrive-ის ვებგვერდზე პერსონალური მონაცემების დამუშავებაზე პასუხისმგებელია შპს FlexDrive, საიდენტიფიკაციო კოდი: 000000000. ეს მონაცემები დროებითი placeholder-ია და კომპანიის რეგისტრაციის შემდეგ რეალური ინფორმაციით ჩანაცვლდება.</p>
<p>მონაცემები მუშავდება მაშინ, როცა მომხმარებელი ქმნის ანგარიშს, შედის პროფილში, ამატებს პროდუქტს კალათაში ან სურვილების სიაში, აგზავნის შეკვეთას, იყენებს საკონტაქტო ფორმას ან გვიკავშირდება მხარდაჭერისთვის.</p>
<ul>
  <li>ანგარიში და პროფილი: სახელი, გვარი, ელფოსტა, ტელეფონი, ქალაქი, მისამართი, პაროლი დაშიფრული ფორმით.</li>
  <li>შეკვეთა: პროდუქტი, რაოდენობა, ფასი, გადახდის მეთოდი, მიწოდების ინფორმაცია, შეკვეთის სტატუსი და კომენტარი.</li>
  <li>საკონტაქტო ფორმა: სახელი, ტელეფონი, ელფოსტა, თემა, შეკვეთის ნომერი და შეტყობინების ტექსტი.</li>
  <li>ტექნიკური მონაცემები: IP მისამართი, ბრაუზერი, მოწყობილობა, სესიის მონაცემები, უსაფრთხოების ჩანაწერები და ქუქები.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "რისთვის ვიყენებთ მონაცემებს",
        "description": (
            "მონაცემები გვჭირდება შეკვეთის დასამუშავებლად, მომხმარებელთან დასაკავშირებლად, "
            "გადახდისა და დაბრუნების პროცესისთვის, უსაფრთხოებისთვის და სერვისის გასაუმჯობესებლად."
        ),
        "editor": """
<p>მონაცემებს ვიყენებთ იმ მიზნით, რომ საიტზე არსებული ძირითადი ecommerce ფუნქციები სწორად მუშაობდეს: ანგარიში, კალათა, სურვილების სია, checkout, შეკვეთების ისტორია, მიწოდება, გადახდა, დაბრუნება და მომხმარებლის მხარდაჭერა.</p>
<p>ასევე ვიყენებთ ტექნიკურ და ანალიტიკურ მონაცემებს საიტის სტაბილურობის, უსაფრთხოების, შეცდომების პოვნისა და პროდუქტის გამოცდილების გასაუმჯობესებლად. პირდაპირი მარკეტინგი, სარეკლამო აუდიტორიები ან remarketing გამოიყენება მხოლოდ შესაბამისი სამართლებრივი საფუძვლით, მათ შორის თანხმობით, როცა ასეთი თანხმობა საჭიროა.</p>
<ul>
  <li>ანგარიშის შექმნა, ავტორიზაცია, აქტივაცია და პაროლის აღდგენა.</li>
  <li>შეკვეთის მიღება, დადასტურება, მიწოდება, გაუქმება, დაბრუნება და refund.</li>
  <li>გადახდის სტატუსის გადამოწმება ბანკთან ან საგადახდო პროვაიდერთან.</li>
  <li>თაღლითობის, სპამის, ბოტების და არაავტორიზებული წვდომის შემცირება.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "ქუქები, ანალიტიკა და მარკეტინგი",
        "description": (
            "საიტი იყენებს აუცილებელ ქუქებს მუშაობისთვის, ხოლო ანალიტიკისა და მარკეტინგის "
            "ხელსაწყოები გამოიყენება საიტის გაუმჯობესებისა და რეკლამის გასაზომად."
        ),
        "editor": """
<p>აუცილებელი ქუქები და მსგავსი ტექნოლოგიები საჭიროა საიტის ფუნქციონირებისთვის: ავტორიზაციის სესია, CSRF დაცვა, კალათა, სურვილების სია, სწრაფი ყიდვის სესია და არჩეული ვიზუალური თემა. ასეთი ქუქების გარეშე საიტის ძირითადი ფუნქციები სრულად ვერ იმუშავებს.</p>
<p>ანალიტიკისა და მარკეტინგის მიზნით შეიძლება გამოყენებული იყოს Google Analytics, Google Tag Manager, Google Ads, Meta Pixel ან მსგავსი ხელსაწყოები. მათი მიზანია ვიზიტების გაზომვა, რეკლამის ეფექტიანობის შეფასება, აუდიტორიების შექმნა და საიტის გაუმჯობესება.</p>
<ul>
  <li>აუცილებელი ქუქები გამოიყენება უსაფრთხოების, სესიისა და ecommerce ფუნქციებისთვის.</li>
  <li>ანალიტიკური ქუქები გვეხმარება გავიგოთ როგორ გამოიყენება საიტი და სად არის გასაუმჯობესებელი ნაწილი.</li>
  <li>მარკეტინგული ქუქები შეიძლება გამოყენებულ იქნეს რეკლამისა და remarketing კამპანიებისთვის.</li>
  <li>არასავალდებულო ქუქების მართვა შესაძლებელია cookie banner-ით ან ბრაუზერის პარამეტრებიდან.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "ვის შეიძლება გადაეცეს ინფორმაცია",
        "description": (
            "მონაცემები შეიძლება გადაეცეს მხოლოდ იმ პარტნიორებს, რომლებიც საჭიროა საიტის, "
            "შეკვეთის, გადახდის, მიწოდების, ანალიტიკის ან უსაფრთხოების პროცესისთვის."
        ),
        "editor": """
<p>FlexDrive არ ყიდის მომხმარებლის პერსონალურ მონაცემებს. მონაცემები შეიძლება გადაეცეს მხოლოდ იმ მომსახურების მომწოდებლებსა და პარტნიორებს, რომლებიც საჭიროა კონკრეტული პროცესის შესასრულებლად.</p>
<ul>
  <li>ჰოსტინგის, ინფრასტრუქტურის, მონაცემთა ბაზისა და ელფოსტის/SMS სერვისის მომწოდებლებს.</li>
  <li>Google reCAPTCHA-ს და სხვა უსაფრთხოების ხელსაწყოებს, ბოტებისა და სპამის შესამცირებლად.</li>
  <li>Google-ის, Meta-ს ან სხვა ანალიტიკისა და რეკლამის პლატფორმებს, თუ შესაბამისი ხელსაწყო აქტიურია.</li>
  <li>ბანკებს, საგადახდო პროვაიდერებს და განვადების/ნაწილ-ნაწილ გადახდის პარტნიორებს.</li>
  <li>კურიერს ან მიწოდებაში ჩართულ პარტნიორს, მხოლოდ შეკვეთის ჩასაბარებლად საჭირო მოცულობით.</li>
  <li>უფლებამოსილ სახელმწიფო ორგანოს, თუ მონაცემის გადაცემა კანონით არის მოთხოვნილი.</li>
</ul>
""".strip(),
    },
    {
        "position": 5,
        "title": "შენახვა, უსაფრთხოება და უფლებები",
        "description": (
            "მონაცემებს ვინახავთ საჭირო ვადით და ვიყენებთ გონივრულ უსაფრთხოების ზომებს. "
            "მომხმარებელს შეუძლია მოითხოვოს მონაცემების ნახვა, შეცვლა ან წაშლა."
        ),
        "editor": """
<p>მონაცემებს ვინახავთ იმდენ ხანს, რამდენიც საჭიროა ანგარიშის, შეკვეთის, მიწოდების, გადახდის, დაბრუნების, მხარდაჭერის, უსაფრთხოების ან კანონით გათვალისწინებული მოთხოვნების შესასრულებლად. როცა მონაცემი აღარ არის საჭირო, ის იშლება, ანონიმიზდება ან ინახება მხოლოდ იმ მოცულობით, რაც კანონით ან ლეგიტიმური ინტერესით არის გამართლებული.</p>
<p>მონაცემების დასაცავად ვიყენებთ დაშიფრულ კავშირებს, უსაფრთხო ქუქებს, წვდომის შეზღუდვას, reCAPTCHA-ს, ადმინისტრაციულ კონტროლს და სხვა გონივრულ ტექნიკურ/ორგანიზაციულ ზომებს.</p>
<ul>
  <li>შეგიძლიათ მოითხოვოთ თქვენს შესახებ არსებული მონაცემების ნახვა ან ასლი.</li>
  <li>შეგიძლიათ მოითხოვოთ არაზუსტი მონაცემის გასწორება ან განახლება.</li>
  <li>შეგიძლიათ მოითხოვოთ მონაცემების წაშლა ან დამუშავების შეზღუდვა, თუ ამის სამართლებრივი საფუძველი არსებობს.</li>
</ul>
<p>კონფიდენციალურობასთან დაკავშირებულ საკითხებზე მოგვწერეთ: <a href="mailto:privacy@flexdrive.ge">privacy@flexdrive.ge</a>. ზოგადი მხარდაჭერისთვის გამოიყენეთ <a href="mailto:support@flexdrive.ge">support@flexdrive.ge</a>.</p>
""".strip(),
    },
)


def refresh_flexdrive_privacy_policy_content(apps, schema_editor):
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
            "footer_group": "legal",
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
        "footer_group": "legal",
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
        ("pages", "0060_trim_payment_methods_extra_copy"),
    ]

    operations = [
        migrations.RunPython(
            refresh_flexdrive_privacy_policy_content,
            migrations.RunPython.noop,
        ),
    ]
