from django.db import migrations


COMPONENT_TYPE_NAME = "Contact"
LEGACY_COMPONENT_TYPE_NAME = "ContactForm"
CONTENT_NAME = "contact_page_content"
PAGE_SLUG = "contact"
PAGE_NAME = "კონტაქტი"
FOOTER_LABEL = "კონტაქტი"
SECTION_TITLE = "დაგვიკავშირდით"
SECTION_SUBTITLE = (
    "თუ შეკვეთის, პროდუქტის, მიწოდების ან დაბრუნების შესახებ გჭირდება დახმარება, "
    "მოგვწერე ფორმით ან გამოიყენე პირდაპირი საკონტაქტო არხები. სამუშაო საათებში "
    "მაქსიმალურად სწრაფად გიპასუხებთ."
)
SEO_TITLE = "კონტაქტი | AutoMate"
SEO_DESCRIPTION = (
    "დაუკავშირდი AutoMate-ს შეკვეთის, პროდუქტის, მიწოდების ან დაბრუნების საკითხებზე. "
    "ფორმა, პირდაპირი საკონტაქტო არხები და სასარგებლო ბმულები ერთ გვერდზე."
)

DELIVERY_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M3.75 7.5H14.25V15.75H3.75V7.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M14.25 10H17.5L20.25 12.75V15.75H14.25V10Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <circle cx="7.75" cy="16.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>
  <circle cx="17" cy="16.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

PAYMENT_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M3.5 10H20.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M7.5 14.5H12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

RETURNS_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M7 8.75H14.75C16.54 8.75 18 10.21 18 12C18 13.79 16.54 15.25 14.75 15.25H6.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 6.5L6 8.75L9 11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M11 12H14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

CATALOG_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="4" y="4" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
  <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
  <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
  <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

TOPIC_ITEMS = (
    {
        "position": 10,
        "title": "პროდუქტის შესახებ",
        "description": "დაზუსტება პროდუქტის მახასიათებლებზე, თავსებადობაზე ან არჩევაზე.",
        "slug": "product",
    },
    {
        "position": 20,
        "title": "შეკვეთის სტატუსი",
        "description": "ინფორმაცია მიმდინარე შეკვეთის ეტაპზე, დამუშავებაზე ან სტატუსზე.",
        "slug": "order-status",
    },
    {
        "position": 30,
        "title": "მიწოდება",
        "description": "ვადები, მისამართი, რეგიონები და მიწოდების პრაქტიკული კითხვები.",
        "slug": "delivery",
    },
    {
        "position": 40,
        "title": "დაბრუნება",
        "description": "დაბრუნების მოთხოვნა, დეფექტიანი ნივთი ან თანხის დაბრუნება.",
        "slug": "returns",
    },
    {
        "position": 50,
        "title": "სხვა",
        "description": "ნებისმიერი სხვა საკითხი, რომელიც ზემოთ ჩამოთვლილებში არ ჯდება.",
        "slug": "other",
    },
)

NOTICE_ITEMS = (
    {
        "position": 100,
        "slug": "form_helper",
        "title": "შეტყობინების გაგზავნა",
        "description": "ფორმით მოგვწერე თუ გჭირდება შეკვეთის, პროდუქტის ან პროცესის დაზუსტება.",
        "editor": """
<p>თუ კონკრეტულ შეკვეთას ეხები, სასურველია მიუთითო შეკვეთის ნომერიც. ეს განსაკუთრებით გვეხმარება მაშინ, როცა შეკვეთა სტუმრის რეჟიმშია გაკეთებული და მომხმარებელს პროფილში ისტორია არ აქვს.</p>
<p>რაც უფრო ზუსტად აღწერ პრობლემას ან შეკითხვას, მით უფრო სწრაფად შეგვიძლია სწორი პასუხის მოძიება და დაბრუნება.</p>
""".strip(),
    },
    {
        "position": 110,
        "slug": "support_intro",
        "title": "სად დაგვიკავშირდეთ",
        "description": "ტელეფონი, ელფოსტა და სამუშაო საათები footer settings-იდან ავტომატურად აისახება აქაც.",
        "editor": "",
    },
    {
        "position": 120,
        "slug": "response_note",
        "title": "როდის მიიღებთ პასუხს",
        "description": "სამუშაო საათებში შეტყობინებებს მაქსიმალურად სწრაფად ვამუშავებთ, არასამუშაო დროს კი მომდევნო სამუშაო დღეს გიპასუხებთ.",
        "editor": """
<ul>
  <li>თუ წერილი შეკვეთის ნომრით მოგვწერეთ, საკითხის მოძიება უფრო სწრაფად მოხდება.</li>
  <li>თუ კითხვა მიწოდებას ან დაბრუნებას ეხება, ქვემოთ მოცემულ სწრაფ ბმულებშიც დაგხვდებათ დამატებითი განმარტებები.</li>
</ul>
""".strip(),
    },
    {
        "position": 130,
        "slug": "shortcuts_intro",
        "title": "სანამ მოგვწერთ, ჯერ აქაც გადახედეთ",
        "description": "ყველაზე ხშირი პროცესები უკვე ცალკე გვერდებად გვაქვს დალაგებული, რათა საჭირო პასუხი სწრაფად იპოვოთ.",
        "editor": "",
    },
    {
        "position": 140,
        "slug": "expectations_intro",
        "title": "რას უნდა ელოდოთ პასუხისგან",
        "description": "ყოველი მოთხოვნა ჯერ ფიქსირდება, შემდეგ კონტექსტის მიხედვით მოწმდება და ბოლოს სწორ პროცესზე გადადის.",
        "editor": "",
    },
    {
        "position": 150,
        "slug": "reasons_intro",
        "title": "რით შეგვიძლია დაგეხმაროთ",
        "description": "კონტაქტის გვერდი ყველაზე სასარგებლოა მაშინ, როცა გჭირდება პროდუქტის, შეკვეთის ან პროცესის დაზუსტება.",
        "editor": "",
    },
)

SHORTCUT_ITEMS = (
    {
        "position": 200,
        "slug": "delivery",
        "title": "მიწოდება",
        "description": "ვადები, თბილისი/რეგიონები და მისამართის დეტალები.",
        "icon_svg": DELIVERY_ICON,
    },
    {
        "position": 210,
        "slug": "payment-methods",
        "title": "გადახდის მეთოდები",
        "description": "ხელმისაწვდომი გადახდის გზები და წარუმატებელი ტრანზაქციის სცენარები.",
        "icon_svg": PAYMENT_ICON,
    },
    {
        "position": 220,
        "slug": "returns",
        "title": "დაბრუნება",
        "description": "14-დღიანი დაბრუნება, დეფექტიანი ნივთი და refund-ის ლოგიკა.",
        "icon_svg": RETURNS_ICON,
    },
    {
        "position": 230,
        "slug": "catalog",
        "title": "კატალოგი",
        "description": "გადადი ყველა პროდუქტზე და გადაამოწმე აქტუალური შეთავაზებები.",
        "icon_svg": CATALOG_ICON,
    },
)

EXPECTATION_ITEMS = (
    {
        "position": 300,
        "title": "მოთხოვნის დაფიქსირება",
        "description": "შეტყობინება ინახება სისტემაში და არ იკარგება მაშინაც, როცა პასუხი სამუშაო საათებს სცდება.",
    },
    {
        "position": 310,
        "title": "კონტექსტის გადამოწმება",
        "description": "თუ შეტყობინება შეკვეთას ეხება, ვამოწმებთ შეკვეთის ნომერს, სტატუსს და შესაბამის დეტალებს.",
    },
    {
        "position": 320,
        "title": "სწორი არხით დახმარება",
        "description": "გიპასუხებთ იმ პროცესით, რომელიც რეალურად საჭიროა: პროდუქტის დაზუსტება, შეკვეთის სტატუსი, მიწოდება თუ დაბრუნება.",
    },
)

REASON_ITEMS = (
    {
        "position": 400,
        "title": "პროდუქტის დაზუსტება",
        "description": "თუ არჩევანს ადარებ ან თავსებადობა გაინტერესებს, ფორმით მოგვწერე კონკრეტული კითხვა.",
    },
    {
        "position": 410,
        "title": "შეკვეთის სტატუსი",
        "description": "რეგისტრირებული მომხმარებელი სტატუსს პროფილიდანაც ხედავს, მაგრამ საჭიროების შემთხვევაში ჩვენც მოგიძიებთ ინფორმაციას.",
    },
    {
        "position": 420,
        "title": "მიწოდება, დაბრუნება და გადახდა",
        "description": "თუ გჭირდება კონკრეტული წესის ან გამონაკლისის დაზუსტება, კონტაქტის გვერდი პირდაპირი გასასვლელია ჩვენი გუნდისკენ.",
    },
)


def seed_contact_page_content(apps, schema_editor):
    Component = apps.get_model("pages", "Component")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Page = apps.get_model("pages", "Page")

    page, _ = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            "name": PAGE_NAME,
            "show_in_menu": False,
            "show_in_footer": True,
            "footer_group": "navigation",
            "footer_order": 50,
            "footer_label": FOOTER_LABEL,
            "seo_title": SEO_TITLE,
            "seo_description": SEO_DESCRIPTION,
            "seo_noindex": True,
        },
    )

    page_update_fields = []
    if page.name != PAGE_NAME:
        page.name = PAGE_NAME
        page_update_fields.append("name")
    if page.show_in_menu:
        page.show_in_menu = False
        page_update_fields.append("show_in_menu")
    if not page.show_in_footer:
        page.show_in_footer = True
        page_update_fields.append("show_in_footer")
    if page.footer_group != "navigation":
        page.footer_group = "navigation"
        page_update_fields.append("footer_group")
    if page.footer_order != 50:
        page.footer_order = 50
        page_update_fields.append("footer_order")
    if page.footer_label != FOOTER_LABEL:
        page.footer_label = FOOTER_LABEL
        page_update_fields.append("footer_label")
    if page.seo_title != SEO_TITLE:
        page.seo_title = SEO_TITLE
        page_update_fields.append("seo_title")
    if page.seo_description != SEO_DESCRIPTION:
        page.seo_description = SEO_DESCRIPTION
        page_update_fields.append("seo_description")
    if not page.seo_noindex:
        page.seo_noindex = True
        page_update_fields.append("seo_noindex")
    if page_update_fields:
        page.save(update_fields=page_update_fields)

    component_type, _ = ComponentType.objects.get_or_create(name=COMPONENT_TYPE_NAME)
    legacy_component_type = ComponentType.objects.filter(
        name=LEGACY_COMPONENT_TYPE_NAME
    ).first()
    content, _ = Content.objects.get_or_create(name=CONTENT_NAME)

    component = (
        Component.objects.filter(page=page, component_type=component_type)
        .order_by("position", "id")
        .first()
    )

    if component is None and legacy_component_type is not None:
        component = (
            Component.objects.filter(page=page, component_type=legacy_component_type)
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
        component_update_fields = []
        if component.component_type_id != component_type.id:
            component.component_type = component_type
            component_update_fields.append("component_type")
        if component.content_id != content.id:
            component.content = content
            component_update_fields.append("content")
        if component.position != 10:
            component.position = 10
            component_update_fields.append("position")
        if component.title != SECTION_TITLE:
            component.title = SECTION_TITLE
            component_update_fields.append("title")
        if component.subtitle != SECTION_SUBTITLE:
            component.subtitle = SECTION_SUBTITLE
            component_update_fields.append("subtitle")
        if component.button_text is not None:
            component.button_text = None
            component_update_fields.append("button_text")
        if not component.enabled:
            component.enabled = True
            component_update_fields.append("enabled")
        if component_update_fields:
            component.save(update_fields=component_update_fields)

    Component.objects.filter(page=page).exclude(pk=component.pk).update(enabled=False)

    valid_positions = []

    for item in TOPIC_ITEMS:
        valid_positions.append(item["position"])
        ContentItem.objects.update_or_create(
            content=content,
            position=item["position"],
            defaults={
                "title": item["title"],
                "description": item["description"],
                "content_type": "contact_topic",
                "icon_svg": None,
                "editor": None,
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": item["slug"],
            },
        )

    for item in NOTICE_ITEMS:
        valid_positions.append(item["position"])
        ContentItem.objects.update_or_create(
            content=content,
            position=item["position"],
            defaults={
                "title": item["title"],
                "description": item["description"],
                "content_type": "contact_notice",
                "icon_svg": None,
                "editor": item["editor"] or None,
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": item["slug"],
            },
        )

    for item in SHORTCUT_ITEMS:
        valid_positions.append(item["position"])
        target_page = Page.objects.filter(slug=item["slug"]).order_by("id").first()
        ContentItem.objects.update_or_create(
            content=content,
            position=item["position"],
            defaults={
                "title": item["title"],
                "description": item["description"],
                "content_type": "contact_shortcut",
                "icon_svg": item["icon_svg"],
                "editor": None,
                "catalog_category_id": None,
                "singlePageRoute_id": target_page.id if target_page else None,
                "slug": item["slug"],
            },
        )

    for item in EXPECTATION_ITEMS:
        valid_positions.append(item["position"])
        ContentItem.objects.update_or_create(
            content=content,
            position=item["position"],
            defaults={
                "title": item["title"],
                "description": item["description"],
                "content_type": "contact_expectation",
                "icon_svg": None,
                "editor": None,
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": None,
            },
        )

    for item in REASON_ITEMS:
        valid_positions.append(item["position"])
        ContentItem.objects.update_or_create(
            content=content,
            position=item["position"],
            defaults={
                "title": item["title"],
                "description": item["description"],
                "content_type": "contact_reason",
                "icon_svg": None,
                "editor": None,
                "catalog_category_id": None,
                "singlePageRoute_id": None,
                "slug": None,
            },
        )

    ContentItem.objects.filter(content=content).exclude(position__in=valid_positions).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0031_contact_inquiry"),
    ]

    operations = [
        migrations.RunPython(
            seed_contact_page_content,
            migrations.RunPython.noop,
        ),
    ]
