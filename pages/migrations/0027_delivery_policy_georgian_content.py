from django.db import migrations


COMPONENT_TYPE_NAME = "Delivery"
CONTENT_NAME = "delivery_sections"
PAGE_SLUG = "delivery"
PAGE_NAME = "მიწოდება"
FOOTER_LABEL = "მიწოდება"
SECTION_TITLE = "მიწოდების პირობები"
SECTION_SUBTITLE = (
    "ამ გვერდზე აღწერილია როგორ ამუშავებს AutoMate შეკვეთებს მიწოდებისთვის, "
    "რა ვადები მოქმედებს თბილისში და რეგიონებში, რა შემთხვევაში შეიძლება "
    "შეიცვალოს ვადა და როგორ მიიღოთ მხარდაჭერა შეკვეთის სტატუსთან დაკავშირებით."
)
SEO_TITLE = "მიწოდების პირობები | AutoMate"
SEO_DESCRIPTION = (
    "გაიგე როგორ მუშაობს AutoMate-ის მიწოდება: შეკვეთის დამუშავება, "
    "თბილისში same-day მიწოდების წესი, რეგიონების ვადები და მხარდაჭერის არხები."
)
SECTION_CONTENT_TYPE = "delivery_section"

PROCESSING_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="5" y="3.5" width="14" height="17" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M9 8.25H15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 12H15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 15.75H12.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

CITY_DELIVERY_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M3.5 6.5H14.5V15.5H3.5V6.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M14.5 9H18.1L20.5 11.6V15.5H14.5V9Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <circle cx="7.5" cy="17.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>
  <circle cx="17.5" cy="17.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

REGIONAL_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 21C16.5 17.1 19 13.85 19 10.5C19 6.91 15.87 4 12 4C8.13 4 5 6.91 5 10.5C5 13.85 7.5 17.1 12 21Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <circle cx="12" cy="10.5" r="2.25" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

ADDRESS_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M4 10.5L12 4L20 10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M6.75 9.75V19.25H17.25V9.75" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M10 19.25V14.75H14V19.25" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
</svg>
""".strip()

DELAY_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.8"/>
  <path d="M12 8V12L14.75 14.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

SUPPORT_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6 9.5C6 6.46 8.69 4 12 4C15.31 4 18 6.46 18 9.5V11.5C18 12.33 17.33 13 16.5 13H15V10.5H18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M6 11.5C6 12.33 6.67 13 7.5 13H9V10.5H6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M9 17.25C9.87 17.73 10.9 18 12 18H13.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <rect x="13.75" y="16.5" width="4.25" height="2.75" rx="1.375" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "შეკვეთის დამუშავება",
        "description": (
            "მიწოდების ვადა იწყება მას შემდეგ, რაც შეკვეთა დაფიქსირდება და "
            "გადამოწმდება. 13:00-მდე მიღებული შეკვეთები სამუშაო დღეს სხვა წესით მუშავდება, "
            "ვიდრე დღის მეორე ნახევარში გაფორმებული შეკვეთები."
        ),
        "icon_svg": PROCESSING_ICON,
        "editor": """
<p>როდესაც მომხმარებელი აგზავნის შეკვეთას, AutoMate ჯერ ამოწმებს შეკვეთის დეტალებს, საკონტაქტო ინფორმაციას და მარაგის ხელმისაწვდომობას. მიწოდების ვადის დათვლა იწყება შეკვეთის მიღებისა და დამუშავების პროცესის შემდეგ.</p>
<p>თუ შეკვეთა სამუშაო დღეს 13:00-მდე დაფიქსირდა და მისამართი/საკონტაქტო ინფორმაცია სწორად არის მითითებული, ის გადადის იმავე დღის პრიორიტეტულ დამუშავებაში. 13:00-ის შემდეგ მიღებული შეკვეთები ჩვეულებრივ გადაიტანება მომდევნო სამუშაო დღის დამუშავებაზე.</p>
<ul>
  <li>შეკვეთის გაგზავნა არ ნიშნავს ავტომატურ დასრულებულ მიწოდებას; საჭიროების შემთხვევაში შეიძლება დაგიკავშირდეთ დეტალების დასაზუსტებლად.</li>
  <li>თუ შეკვეთის რომელიმე მონაცემი დასაზუსტებელია, მიწოდების ვადის ათვლა იწყება დაზუსტებული ინფორმაციის მიღების შემდეგ.</li>
  <li>სამუშაო დღის ჭრილი 13:00-მდე წესისთვის გამოიყენება მხოლოდ იმ შეკვეთებზე, რომლებიც რეალურად მიღებულია და მზად არის დამუშავებისთვის.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "მიწოდება თბილისში",
        "description": (
            "თბილისის მასშტაბით 13:00-მდე გაფორმებული შეკვეთები, როგორც წესი, "
            "იგივე დღეს იგზავნება. 13:00-ის შემდეგ გაფორმებული შეკვეთები გადადის "
            "მომდევნო სამუშაო დღეზე."
        ),
        "icon_svg": CITY_DELIVERY_ICON,
        "editor": """
<p>თბილისში მიწოდება იგეგმება მაქსიმალურად სწრაფად. თუ შეკვეთა სამუშაო დღეს 13:00-მდე დაფიქსირდა, AutoMate მიზნად ისახავს მის იმავე დღეს მიწოდებას. თუ შეკვეთა 13:00-ის შემდეგ მივიღეთ, მიწოდება ჩვეულებრივ ხორციელდება მომდევნო სამუშაო დღეს.</p>
<p>ეს ვადა მოქმედებს თბილისის სტანდარტულ მისამართებზე და იმ შემთხვევებზე, როდესაც კურიერს შეუძლია მომხმარებელთან დაკავშირება და მისამართის დადასტურება დამატებითი შეფერხების გარეშე.</p>
<ul>
  <li>13:00-მდე: მიწოდება იმავე დღეს.</li>
  <li>13:00-ის შემდეგ: მიწოდება მომდევნო სამუშაო დღეს.</li>
  <li>თუ შეკვეთაში საჭიროა დამატებითი დაზუსტება, ვადა შეიძლება გადაიწიოს შესაბამისი კომუნიკაციის დასრულებამდე.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "მიწოდება რეგიონებში",
        "description": (
            "რეგიონებში შეკვეთების მიწოდების სტანდარტული ჩარჩო არის 1-5 სამუშაო დღე. "
            "ზუსტი დრო დამოკიდებულია მიმართულებაზე, კურიერის მარშრუტსა და მიმდინარე დატვირთვაზე."
        ),
        "icon_svg": REGIONAL_ICON,
        "editor": """
<p>თბილისის ფარგლებს გარეთ მიწოდება ხორციელდება რეგიონული მარშრუტების მიხედვით. შეკვეთის მიღებიდან რეგიონებში მიწოდების საორიენტაციო ვადა არის 1-5 სამუშაო დღე.</p>
<p>ზუსტი დრო შეიძლება შეიცვალოს დასახლებული პუნქტის, ტრანსპორტირების მიმართულებისა და პარტნიორი საკურიერო ქსელის სამუშაო რეჟიმის მიხედვით. AutoMate შეეცდება მიწოდება შესრულდეს რაც შეიძლება სწრაფად, მაგრამ რეგიონული შეკვეთები ყოველთვის ერთსა და იმავე დღეში ვერ დაექვემდებარება.</p>
<ul>
  <li>რეგიონების შეკვეთები იგეგმება 1-5 სამუშაო დღის ჩარჩოში.</li>
  <li>შორეულ ან ნაკლებად დატვირთულ მიმართულებებზე მიწოდება შეიძლება უახლოვდებოდეს მაქსიმალურ ვადას.</li>
  <li>თუ დაგვჭირდება დამატებითი დადასტურება ან კურიერის მხრიდან იქნება სპეციფიკური შეზღუდვა, მოგაწვდით განახლებულ ინფორმაციას.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "მისამართი და მიღება",
        "description": (
            "მიწოდების სისწრაფე მნიშვნელოვნად არის დამოკიდებული სწორ მისამართსა და "
            "აქტიურ საკონტაქტო ნომერზე. არაზუსტი მონაცემები ყველაზე ხშირი შეფერხების მიზეზია."
        ),
        "icon_svg": ADDRESS_ICON,
        "editor": """
<p>მომხმარებელმა შეკვეთის გაფორმებისას უნდა მიუთითოს სრული და ზუსტი მისამართი, აქტიური სატელეფონო ნომერი და, საჭიროების შემთხვევაში, დამატებითი მითითებები, რომლებიც კურიერს დაეხმარება შეკვეთის სწრაფად ჩაბარებაში.</p>
<p>თუ მითითებული მისამართი არასრულია, შენობაში შესასვლელი ან სადარბაზო დეტალები აკლია, ან საკონტაქტო ნომერზე დაკავშირება ვერ ხერხდება, მიწოდება შეიძლება გადაიდოს ან ხელახლა დაიგეგმოს.</p>
<ul>
  <li>შეამოწმეთ მისამართი შეკვეთის გაგზავნამდე.</li>
  <li>შეინარჩუნეთ აქტიური ტელეფონი, რომ კურიერმა საჭიროების შემთხვევაში დაგიკავშირდეთ.</li>
  <li>თუ მისამართი შეიცვალა შეკვეთის გაფორმების შემდეგ, დაგვიკავშირდით რაც შეიძლება სწრაფად.</li>
</ul>
""".strip(),
    },
    {
        "position": 5,
        "title": "შესაძლო შეფერხებები",
        "description": (
            "ზოგიერთ შემთხვევაში მიწოდების ვადა შეიძლება შეიცვალოს. ამის მიზეზი "
            "შეიძლება იყოს მაღალი დატვირთვა, ამინდი, დასვენების დღეები ან საკონტაქტო პრობლემები."
        ),
        "icon_svg": DELAY_ICON,
        "editor": """
<p>AutoMate ცდილობს დაიცვას მითითებული საორიენტაციო ვადები, თუმცა გარკვეულ შემთხვევებში მიწოდება შეიძლება გადაიწიოს. ასეთ შემთხვევებს მიეკუთვნება არასტაბილური ამინდი, მაღალი საოპერაციო დატვირთვა, დასვენების დღეები, სატრანსპორტო შეზღუდვები ან შეკვეთის მონაცემების დაზუსტების საჭიროება.</p>
<p>თუ ველით, რომ შეკვეთის მიწოდება დაგეგმილ ვადას გადააჭარბებს, ჩვენი გუნდი შეეცდება მომხმარებელს დროულად მიაწოდოს განახლებული ინფორმაცია ხელმისაწვდომი კომუნიკაციის არხით.</p>
<ul>
  <li>აღნიშნული ვადები საორიენტაციოა და ემყარება ნორმალურ საოპერაციო პირობებს.</li>
  <li>შეფერხების შემთხვევაში მომხმარებელს მიეწოდება დაზუსტებული ინფორმაცია, როცა ეს შესაძლებელი იქნება.</li>
  <li>არაზუსტი მისამართი ან უკონტაქტობა ხშირად იწვევს ხელახალ დაგეგმვას.</li>
</ul>
""".strip(),
    },
    {
        "position": 6,
        "title": "შეკვეთის სტატუსი და დახმარება",
        "description": (
            "რეგისტრირებულ მომხმარებელს შეუძლია პროფილიდან ნახოს შეკვეთის ისტორია და სტატუსი. "
            "სტუმრის რეჟიმში გაფორმებული შეკვეთებისთვის მხარდაჭერა ხელმისაწვდომია ელფოსტით ან ტელეფონით."
        ),
        "icon_svg": SUPPORT_ICON,
        "editor": """
<p>თუ მომხმარებელი შეკვეთას რეგისტრირებული პროფილით აფორმებს, მას შეუძლია საკუთარ ანგარიშში ნახოს შეკვეთების ისტორია და სტატუსის ცვლილებები. ეს არის ყველაზე მარტივი გზა მიწოდების პროგრესის დასაკვირვებლად.</p>
<p>თუ შეკვეთა გაფორმებულია სტუმრის რეჟიმში, პროფილის შიგნით სტატუსის არქივი ხელმისაწვდომი არ არის. ასეთ შემთხვევაში დახმარებისთვის დაგვიკავშირდით შეკვეთის ნომრით და საკონტაქტო მონაცემებით, რათა სწრაფად მოვძებნოთ შეკვეთის სტატუსი.</p>
<ul>
  <li>ელფოსტა: <a href="mailto:support@automate.ge">support@automate.ge</a></li>
  <li>ტელეფონი: <a href="tel:+995555010203">+995 555 01 02 03</a></li>
  <li>სტუმრის შეკვეთის შემთხვევაში მოგვწერეთ შეკვეთის ნომერი, სახელი და საკონტაქტო ნომერი.</li>
</ul>
""".strip(),
    },
)


def seed_delivery_georgian_content(apps, schema_editor):
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
            "footer_group": "help",
            "footer_order": 10,
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
    if page.footer_group != "help":
        page.footer_group = "help"
        page_update_fields.append("footer_group")
    if page.footer_order != 10:
        page.footer_order = 10
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
    content, _ = Content.objects.get_or_create(name=CONTENT_NAME)

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
        component_update_fields = []
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
                "icon_svg": section["icon_svg"],
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
        ("pages", "0026_terms_georgian_content"),
    ]

    operations = [
        migrations.RunPython(
            seed_delivery_georgian_content,
            migrations.RunPython.noop,
        ),
    ]
