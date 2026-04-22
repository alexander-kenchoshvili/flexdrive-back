from django.db import migrations


COMPONENT_TYPE_NAME = "Returns"
CONTENT_NAME = "returns_sections"
PAGE_SLUG = "returns"
PAGE_NAME = "დაბრუნება"
FOOTER_LABEL = "დაბრუნება"
SECTION_TITLE = "დაბრუნება და თანხის დაბრუნება"
SECTION_SUBTITLE = (
    "ამ გვერდზე აღწერილია როგორ უნდა მოითხოვოთ პროდუქტის დაბრუნება AutoMate-ზე, რა ვადები მოქმედებს "
    "ჩვეულებრივი და დეფექტიანი დაბრუნების შემთხვევაში, ვინ ფარავს დაბრუნების ხარჯს და როგორ მუშავდება თანხის დაბრუნება."
)
SEO_TITLE = "დაბრუნება და თანხის დაბრუნება | AutoMate"
SEO_DESCRIPTION = (
    "გაიგე როგორ მუშაობს AutoMate-ზე დაბრუნება: მოთხოვნის გაგზავნა, 14-დღიანი დაბრუნება, დეფექტიანი ან არასწორი "
    "პროდუქტის პროცესი და თანხის დაბრუნების ვადები."
)
SECTION_CONTENT_TYPE = "returns_section"

REQUEST_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M4 7.75C4 6.78 4.78 6 5.75 6H18.25C19.22 6 20 6.78 20 7.75V16.25C20 17.22 19.22 18 18.25 18H5.75C4.78 18 4 17.22 4 16.25V7.75Z" stroke="currentColor" stroke-width="1.8"/>
  <path d="M5 8L11.1 12.27C11.64 12.65 12.36 12.65 12.9 12.27L19 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

CALENDAR_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="4" y="5" width="16" height="15" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M8 3.75V6.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M16 3.75V6.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M4 9H20" stroke="currentColor" stroke-width="1.8"/>
  <path d="M8.5 12.5H12.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

DEFECT_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 4L19 7.5V12.5C19 16.6 16.33 19.88 12 21C7.67 19.88 5 16.6 5 12.5V7.5L12 4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M9.25 12L11.1 13.85L14.75 10.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

PACKAGE_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 3.75L18.75 7.5V16.5L12 20.25L5.25 16.5V7.5L12 3.75Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M12 12L18.75 7.5" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M12 12L5.25 7.5" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M12 12V20.25" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
</svg>
""".strip()

REFUND_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M7 8.75H14.75C16.54 8.75 18 10.21 18 12C18 13.79 16.54 15.25 14.75 15.25H6.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 6.5L6 8.75L9 11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M11 12H14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
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
        "title": "როგორ დავიწყოთ დაბრუნება",
        "description": (
            "დაბრუნების მოთხოვნა იწყება ელფოსტაზე წერილით. მოგვწერეთ შეკვეთის ნომერი, თქვენი სახელი, საკონტაქტო ნომერი, "
            "დასაბრუნებელი ნივთი და დაბრუნების მიზეზი."
        ),
        "icon_svg": REQUEST_ICON,
        "editor": """
<p>ამ ეტაპზე AutoMate-ზე თვითმომსახურების დაბრუნების ღილაკი ჯერ არ არის დამატებული, ამიტომ დაბრუნების მოთხოვნა იწყება ელფოსტაზე წერილით. მოგვწერეთ მისამართზე <a href="mailto:support@automate.ge">support@automate.ge</a> და სათაურში ან ტექსტში მიუთითეთ შეკვეთის ნომერი.</p>
<p>წერილში დაგვიტოვეთ მომხმარებლის სახელი, საკონტაქტო ნომერი, რომელი პროდუქტის დაბრუნება გსურთ და რა მიზეზით. თუ ნივთი დაზიანებულია, დეფექტიანია ან არასწორი პროდუქტი მიიღეთ, დაგვიმატეთ ფოტო ან მოკლე ვიდეოც, რომ გადამოწმება სწრაფად მოხდეს.</p>
<ul>
  <li>შეკვეთის ნომერი აჩქარებს მოთხოვნის მოძიებას.</li>
  <li>სტუმრის რეჟიმში გაფორმებული შეკვეთის შემთხვევაში განსაკუთრებით მნიშვნელოვანია სწორი ტელეფონისა და ელფოსტის მითითება.</li>
  <li>თუ პრობლემა მიწოდებისას დაფიქსირდა, მოგვწერეთ რაც შეიძლება მალე.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "ჩვეულებრივი დაბრუნება 14 დღეში",
        "description": (
            "თუ უბრალოდ გადაიფიქრეთ შეძენა, დაბრუნების მოთხოვნა შეგიძლიათ გამოგვიგზავნოთ პროდუქტის მიღებიდან 14 კალენდარული დღის განმავლობაში."
        ),
        "icon_svg": CALENDAR_ICON,
        "editor": """
<p>თუ მომხმარებელმა უბრალოდ გადაიფიქრა შეძენა და პროდუქტი დეფექტიანი არ არის, დაბრუნების მოთხოვნა შეიძლება გამოგვიგზავნოთ ნივთის მიღებიდან 14 კალენდარული დღის განმავლობაში. მოთხოვნა უნდა მივიღოთ ამ ვადაში, თუნდაც თავად ფიზიკური დაბრუნება მოგვიანებით განხორციელდეს შეთანხმებული პროცესით.</p>
<p>ასეთი დაბრუნების დროს მნიშვნელოვანია, რომ ნივთი იყოს კარგ მდგომარეობაში და გამოყენებული არ იყოს იმაზე მეტად, ვიდრე ეს მის შესამოწმებლად არის საჭირო. თუ კომპლექტაციაში შედიოდა დამატებითი აქსესუარები, სამაგრები, კაბელები, ინსტრუქცია ან ყუთი, სასურველია დაბრუნდეს მათთან ერთად.</p>
<ul>
  <li>14-დღიანი ვადა ითვლება პროდუქტის მიღებიდან.</li>
  <li>დაბრუნების მოთხოვნა უნდა გაიგზავნოს ელფოსტაზე.</li>
  <li>ჩვეულებრივი დაბრუნების შემთხვევაში პროდუქტის პირდაპირი დაბრუნების ხარჯი, როგორც წესი, მომხმარებელზეა.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "დეფექტიანი ან არასწორი პროდუქტი",
        "description": (
            "თუ მიიღეთ დაზიანებული, დეფექტიანი ან შეკვეთასთან შეუსაბამო პროდუქტი, დაგვიკავშირდით და შევთავაზებთ შეცვლას ან თანხის დაბრუნებას."
        ),
        "icon_svg": DEFECT_ICON,
        "editor": """
<p>თუ მიღებული პროდუქტი დაზიანებულია, აქვს დეფექტი ან მიღებულია სხვა მოდელი/ვერსია, ვიდრე შეკვეთაში იყო მითითებული, დაბრუნების პროცესი მუშავდება პრიორიტეტულად. ასეთ შემთხვევაში ელფოსტაზე წერილთან ერთად სასურველია მოგვაწოდოთ ფოტო ან ვიდეო, სადაც პრობლემა კარგად ჩანს.</p>
<p>გადამოწმების შემდეგ AutoMate მომხმარებელს შესთავაზებს გამოსავალს კონკრეტული შემთხვევის მიხედვით: პროდუქტის შეცვლას, ალტერნატიულ ერთეულს ან თანხის სრულ დაბრუნებას. თუ მიზეზი ჩვენი შეცდომაა, დაბრუნების და ხელახლა გაგზავნის საჭირო ხარჯს მაღაზია იღებს საკუთარ თავზე.</p>
<ul>
  <li>დეფექტიანი ან არასწორი პროდუქტის შემთხვევაში დაგვიმატეთ ვიზუალური მასალა.</li>
  <li>ასეთ შემთხვევებში დაბრუნების ტრანსპორტირების ხარჯი მომხმარებელზე არ გადადის.</li>
  <li>საბოლოო გადაწყვეტა მიიღება გადამოწმების დასრულების შემდეგ, მაგრამ პროცესი მაქსიმალურად დაჩქარდება.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "ნივთის მდგომარეობა და კომპლექტაცია",
        "description": (
            "ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა დაბრუნდეს მაქსიმალურად სრულ კომპლექტაციაში და ისეთ მდგომარეობაში, რომ მისი გადამოწმება შესაძლებელი იყოს."
        ),
        "icon_svg": PACKAGE_ICON,
        "editor": """
<p>ჩვეულებრივი დაბრუნების შემთხვევაში პროდუქტი უნდა დაგვიბრუნდეს ისეთ მდგომარეობაში, რომ შესაძლებელი იყოს მისი შემოწმება. ეს ნიშნავს, რომ ნივთი არ უნდა იყოს დაზიანებული მომხმარებლის მხრიდან და სასურველია ახლდეს ის დეტალებიც, რაც შეკვეთისას მიიღო მომხმარებელმა.</p>
<p>თუ პროდუქტს მოჰყვებოდა ორიგინალი შეფუთვა, დამატებითი ელემენტები, სამაგრები, ინსტრუქცია ან სხვა კომპონენტები, დაბრუნებისას მათი ერთად გამოგზავნა მნიშვნელოვნად ამარტივებს პროცესს. დეფექტიანი ან არასწორი პროდუქტის შემთხვევაში შეფასება მოხდება კონკრეტული პრობლემის ხასიათის მიხედვით.</p>
<ul>
  <li>შეინახეთ აქსესუარები და პატარა ნაწილები, სანამ გადაწყვეტთ დატოვებთ თუ დააბრუნებთ ნივთს.</li>
  <li>თუ შეფუთვა ან კომპლექტაცია არასრულია, მოგვწერეთ წინასწარ და შევაფასებთ კონკრეტულ შემთხვევას.</li>
  <li>დაბრუნების დამტკიცება შეიძლება დამოკიდებული იყოს ნივთის რეალურ მდგომარეობაზე.</li>
</ul>
""".strip(),
    },
    {
        "position": 5,
        "title": "თანხის დაბრუნების ვადა და მეთოდი",
        "description": (
            "დადასტურებული დაბრუნების შემდეგ თანხის დაბრუნება, როგორც წესი, მუშავდება არაუგვიანეს 14 კალენდარული დღის განმავლობაში."
        ),
        "icon_svg": REFUND_ICON,
        "editor": """
<p>თუ დაბრუნება დადასტურდა, AutoMate თანხის დაბრუნებას ამუშავებს არაუგვიანეს 14 კალენდარული დღის განმავლობაში. ჩვეულებრივ, თანხის დაბრუნება შეიძლება დაკავშირდეს იმასთან, რომ პროდუქტი უკვე მიღებული და გადამოწმებულია, ან მიღებულია მისი გამოგზავნის დამადასტურებელი ინფორმაცია.</p>
<p>თუ შეკვეთა ონლაინ იყო გადახდილი, თანხის დაბრუნება, სადაც ეს ტექნიკურად შესაძლებელია, იმავე გადახდის მეთოდით დამუშავდება. თუ შეკვეთა ნაღდი ანგარიშსწორებით იყო მიღებული, შეიძლება დაგვჭირდეს საბანკო რეკვიზიტების დამატებით მოწოდება, რათა თანხა სწორად გადაირიცხოს.</p>
<ul>
  <li>დაბრუნების ვადა ითვლება მოთხოვნის დადასტურებისა და დაბრუნების პროცესის დაწყებიდან.</li>
  <li>ონლაინ გადახდის შემთხვევაში თანხა, როგორც წესი, ბრუნდება იმავე გადახდის არხზე.</li>
  <li>ნაღდი ანგარიშსწორების შეკვეთებზე შეიძლება საჭირო გახდეს საბანკო ანგარიშის დეტალები.</li>
</ul>
""".strip(),
    },
    {
        "position": 6,
        "title": "დაბრუნების ხარჯი და დახმარება",
        "description": (
            "ჩვეულებრივი დაბრუნებისას პირდაპირი ხარჯი მომხმარებელზეა, ხოლო დეფექტიანი ან არასწორი პროდუქტის შემთხვევაში ამ ხარჯს AutoMate ფარავს."
        ),
        "icon_svg": SUPPORT_ICON,
        "editor": """
<p>თუ დაბრუნება ხდება მხოლოდ იმ მიზეზით, რომ მომხმარებელმა გადაიფიქრა შეძენა, პროდუქტის უკან გაგზავნის პირდაპირი ხარჯი ჩვეულებრივ მომხმარებელზეა. თუ პრობლემა გამოწვეულია ჩვენი მხრიდან, მაგალითად მიღებულია არასწორი ან დეფექტიანი პროდუქტი, შესაბამის ხარჯს AutoMate იღებს საკუთარ თავზე.</p>
<p>თუ შეკვეთა ანგარიშით გაფორმდა, შეკვეთების ისტორია და სტატუსი პროფილიდანაც შეგიძლიათ გადაამოწმოთ. სტუმრის რეჟიმში გაფორმებული შეკვეთების შემთხვევაში დახმარებისთვის მოგვწერეთ ან დაგვირეკეთ და მიუთითეთ შეკვეთის ნომერი.</p>
<ul>
  <li>ელფოსტა: <a href="mailto:support@automate.ge">support@automate.ge</a></li>
  <li>ტელეფონი: <a href="tel:+995555010203">+995 555 01 02 03</a></li>
  <li>სტუმრის შეკვეთის შემთხვევაში მოგვწერეთ შეკვეთის ნომერი, სახელი და საკონტაქტო ნომერი.</li>
</ul>
""".strip(),
    },
)


def seed_returns_georgian_content(apps, schema_editor):
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
            "footer_order": 30,
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
    if page.footer_order != 30:
        page.footer_order = 30
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
        ("pages", "0027_delivery_policy_georgian_content"),
    ]

    operations = [
        migrations.RunPython(
            seed_returns_georgian_content,
            migrations.RunPython.noop,
        ),
    ]

