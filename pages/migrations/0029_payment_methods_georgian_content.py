from django.db import migrations


COMPONENT_TYPE_NAME = "PaymentMethods"
CONTENT_NAME = "payment_methods_sections"
PAGE_SLUG = "payment-methods"
PAGE_NAME = "გადახდის მეთოდები"
FOOTER_LABEL = "გადახდის მეთოდები"
SECTION_TITLE = "გადახდის მეთოდები"
SECTION_SUBTITLE = (
    "ამ გვერდზე აღწერილია რომელი გადახდის მეთოდებია ხელმისაწვდომი AutoMate-ზე, როგორ მუშაობს ნაღდი "
    "ანგარიშსწორება, რა ეტაპზე ჩაირთვება ბარათით გადახდა და რა ხდება გადახდის წარუმატებლობის ან თანხის დაბრუნების შემთხვევაში."
)
SEO_TITLE = "გადახდის მეთოდები | AutoMate"
SEO_DESCRIPTION = (
    "გაიგე როგორ მუშაობს AutoMate-ზე გადახდა: ხელმისაწვდომი მეთოდები, ნაღდი ანგარიშსწორება კურიერთან, "
    "ბარათით გადახდის სტატუსი, წარუმატებელი ტრანზაქციები და თანხის დაბრუნების პრაქტიკა."
)
SECTION_CONTENT_TYPE = "payment_method_section"

METHODS_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3.5" y="5.5" width="17" height="13" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M3.5 10H20.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M7.5 14.5H10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

CASH_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <circle cx="12" cy="12" r="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M6.5 9.25H6.51" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
  <path d="M17.5 14.75H17.51" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
</svg>
""".strip()

CARD_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M3.5 10H20.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M7.5 14.5H12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

CONFIRM_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.8"/>
  <path d="M12 8V12L14.75 13.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

FAILED_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 4.5L20 18.5H4L12 4.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M12 9.25V12.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M12 15.75H12.01" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
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
        "title": "ხელმისაწვდომი გადახდის მეთოდები",
        "description": (
            "Checkout-ზე მომხმარებელი ხედავს მხოლოდ იმ გადახდის მეთოდებს, რომლებიც რეალურად აქტიურია იმ მომენტში. "
            "ამ ეტაპზე სრულად ხელმისაწვდომია ნაღდი ანგარიშსწორება, ხოლო ბარათით გადახდა მზადდება."
        ),
        "icon_svg": METHODS_ICON,
        "editor": """
<p>AutoMate-ზე გადახდის გვერდი და checkout შექმნილია ისე, რომ მომხმარებელს აჩვენოს მხოლოდ ის მეთოდები, რომლებიც რეალურად მოქმედებს შეკვეთის გაფორმების მომენტში. ეს ნიშნავს, რომ თუ რომელიმე ახალი მეთოდი ჯერ მზადების ეტაპზეა, ის არ ჩაითვლება სრულად აქტიურ გადახდის ვარიანტად მხოლოდ იმიტომ, რომ მისი დასახელება სადმე ჩანს.</p>
<p>ამ ეტაპზე სრულად ხელმისაწვდომია ნაღდი ანგარიშსწორება. ონლაინ ბარათით გადახდის ინტეგრაცია მზადდება და აქტიურ მეთოდად ჩაითვლება მხოლოდ მას შემდეგ, რაც checkout-ზე ჩართული და ფაქტობრივად გამოსაყენებელი გახდება.</p>
<ul>
  <li>ყოველთვის იხელმძღვანელეთ იმით, რაც checkout-ზე აქტიურად ჩანს.</li>
  <li>საიტზე შეიძლება წინასწარ გამოჩნდეს მომავალი მეთოდების შესახებ ინფორმაცია.</li>
  <li>ხელმისაწვდომი მეთოდების ცვლილების შემთხვევაში ეს გვერდიც განახლდება.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "ნაღდი ანგარიშსწორება კურიერთან",
        "description": (
            "თუ აირჩევთ ნაღდი ანგარიშსწორების მეთოდს, თანხის გადახდა ხდება შეკვეთის მიღებისას, კურიერთან."
        ),
        "icon_svg": CASH_ICON,
        "editor": """
<p>ნაღდი ანგარიშსწორება განკუთვნილია იმ მომხმარებლებისთვის, ვისაც ურჩევნია თანხა გადაიხადოს შეკვეთის მიღებისას. ამ შემთხვევაში ონლაინ ტრანზაქცია წინასწარ არ სრულდება და გადახდა ხდება კურიერთან, შეკვეთის ჩაბარების მომენტში.</p>
<p>სასურველია შეკვეთის მიღებისას მზად გქონდეთ შესაბამისი თანხა ან წინასწარ დააზუსტოთ დეტალები, თუ ამის საჭიროებას ხედავთ. თუ მისამართი ან მიღების დრო შეიცვალა, დროულად დაგვიკავშირდით, რათა მიწოდებისა და გადახდის პროცესი შეფერხების გარეშე გაგრძელდეს.</p>
<ul>
  <li>გადახდა ხდება ფიზიკური მიღებისას.</li>
  <li>ონლაინ ჩამოჭრა ამ მეთოდზე წინასწარ არ სრულდება.</li>
  <li>თუ შეკვეთა არ ჩაიბარა მომხმარებელმა, გადახდაც დაუდასტურებელი რჩება.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "ონლაინ ბარათით გადახდა",
        "description": (
            "ონლაინ ბარათით გადახდის ინტეგრაცია მზადდება და მალე დაემატება. როგორც კი მეთოდი აქტიური გახდება, checkout-ზე ჩართვისთანავე გამოჩნდება მისი რეალური გამოყენების პირობები."
        ),
        "icon_svg": CARD_ICON,
        "editor": """
<p>ბარათით ონლაინ გადახდა AutoMate-ზე მზადების პროცესშია. სანამ ეს ფუნქცია სრულად არ ჩაირთვება, ბარათით გადახდა არ უნდა ჩაითვალოს დასრულებულ ან ყოველდღიურად ხელმისაწვდომ მეთოდად.</p>
<p>როდესაც ონლაინ გადახდა ჩაირთვება, შესაბამისი წესები განახლდება ამავე გვერდზე. აქ აღიწერება რომელი ბარათებია მხარდაჭერილი, როდის დადასტურდება ტრანზაქცია, როგორ იმუშავებს გაუქმებული ან წარუმატებელი ოპერაცია და რა გზით დამუშავდება თანხის დაბრუნება.</p>
<ul>
  <li>ბარათით გადახდა აქტიურია მხოლოდ მაშინ, როცა checkout-ზე რეალურად შეგიძლიათ მისი არჩევა და დასრულება.</li>
  <li>თუ გვერდზე ან checkout-ში წერია, რომ მეთოდი მალე დაემატება, ეს ნიშნავს, რომ ის ჯერ მზადების ეტაპზეა.</li>
  <li>გადახდის პროვაიდერის დამატების შემდეგ გვერდი განახლდება ტექნიკური და პრაქტიკული დეტალებით.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "როდის ითვლება გადახდა დასრულებულად",
        "description": (
            "გადახდის დასრულების მომენტი დამოკიდებულია არჩეულ მეთოდზე: ნაღდი ანგარიშსწორება სრულდება კურიერთან, ხოლო ბარათით გადახდა დადასტურდება ონლაინ ტრანზაქციის წარმატებით."
        ),
        "icon_svg": CONFIRM_ICON,
        "editor": """
<p>გადახდა დასრულებულად სხვადასხვანაირად ითვლება იმის მიხედვით, რომელი მეთოდია არჩეული. ნაღდი ანგარიშსწორებისას საბოლოო გადახდა ხდება კურიერთან, პროდუქტის ჩაბარებისას. ბარათით გადახდის ჩართვის შემდეგ კი ონლაინ მეთოდის დასრულება დამოკიდებული იქნება საგადახდო ტრანზაქციის წარმატებულ დადასტურებაზე.</p>
<p>შეკვეთის გაგზავნა თავისთავად არ ნიშნავს, რომ კონკრეტული გადახდა უკვე შესრულებულია. სწორედ ამიტომ checkout-ზე მითითებული სტატუსი და შემდგომი დადასტურება ყოველთვის მნიშვნელოვანია როგორც მომხმარებლისთვის, ისე შეკვეთის დამუშავებისთვის.</p>
<ul>
  <li>ნაღდი ანგარიშსწორება სრულდება შეკვეთის ფიზიკური მიღებისას.</li>
  <li>ბარათით გადახდის შემთხვევაში დასრულება დამოკიდებული იქნება ონლაინ ტრანზაქციის წარმატებით დადასტურებაზე.</li>
  <li>შეკვეთის გაგზავნა და გადახდის დასრულება ერთი და იგივე ეტაპი არ არის.</li>
</ul>
""".strip(),
    },
    {
        "position": 5,
        "title": "წარუმატებელი ან გაუქმებული გადახდა",
        "description": (
            "თუ ონლაინ გადახდა არ დასრულდა ან ტრანზაქცია შეწყდა, შეკვეთა შეიძლება დარჩეს დაუმუშავებელ მდგომარეობაში, ვიდრე მომხმარებელი ხელახლა არ დაადასტურებს ან არ აირჩევს სხვა ხელმისაწვდომ მეთოდს."
        ),
        "icon_svg": FAILED_ICON,
        "editor": """
<p>ონლაინ გადახდის ამოქმედების შემდეგ შესაძლოა გაჩნდეს შემთხვევები, როცა ტრანზაქცია არ დასრულდება ტექნიკური შეფერხების, კავშირის გაწყვეტის, ავტორიზაციის უარყოფის ან სხვა მიზეზის გამო. ასეთ დროს შეკვეთის საბოლოო დამუშავება შეიძლება შეჩერდეს იქამდე, სანამ გადახდის სტატუსი არ დაზუსტდება.</p>
<p>თუ ეჭვი გეპარებათ, დასრულდა თუ არა გადახდა, ჯერ გადაამოწმეთ თქვენი საბანკო შეტყობინებები ან სტატუსი checkout-ის გვერდზე. თუ ინფორმაცია არ არის მკაფიო, დაგვიკავშირდით და არ სცადოთ რამდენიმე იდენტური შეკვეთის დაუფიქრებლად გაგზავნა, რათა ზედმეტი დუბლირება არ შეიქმნას.</p>
<ul>
  <li>თუ ონლაინ ტრანზაქცია ვერ დასრულდა, შეკვეთა შეიძლება დარჩეს დაუდასტურებელ მდგომარეობაში.</li>
  <li>ნაღდი ანგარიშსწორების მეთოდზე ეს რისკი წინასწარ ჩამოჭრის თვალსაზრისით არ არსებობს.</li>
  <li>გაურკვეველი სტატუსის შემთხვევაში დაგვიკავშირდით შეკვეთის ნომრით ან საკონტაქტო მონაცემებით.</li>
</ul>
""".strip(),
    },
    {
        "position": 6,
        "title": "უსაფრთხოება, თანხის დაბრუნება და დახმარება",
        "description": (
            "გადახდასთან დაკავშირებული დახმარება შეგიძლიათ მიიღოთ ელფოსტით ან ტელეფონით, ხოლო თანხის დაბრუნების პრაქტიკა მიჰყვება დაბრუნების წესებს და არჩეული გადახდის მეთოდის სპეციფიკას."
        ),
        "icon_svg": SUPPORT_ICON,
        "editor": """
<p>გადახდასთან დაკავშირებული ნებისმიერი საკითხის შემთხვევაში შეგიძლიათ დაგვიკავშირდეთ ელფოსტით ან ტელეფონით. თუ მომავალში ონლაინ ბარათით გადახდა ჩაირთვება, შესაბამისი ტექნიკური ოპერაციები დამუშავდება საგადახდო პროვაიდერის არხებით, ხოლო ჩვენ ამ გვერდზე და სხვა შესაბამის პოლიტიკებში ავსახავთ საჭირო განმარტებებს.</p>
<p>თანხის დაბრუნება დამოკიდებულია იმაზე, როგორ იყო გადახდილი შეკვეთა და რა საფუძვლით ხდება დაბრუნება. ნაღდი ანგარიშსწორებით გაფორმებული შეკვეთების შემთხვევაში შეიძლება საჭირო გახდეს საბანკო რეკვიზიტების დამატებით მოწოდება, ხოლო ონლაინ გადახდის შემთხვევაში თანხა, როგორც წესი, დაბრუნდება იმავე გადახდის არხზე. დაბრუნების დეტალური წესები იხილეთ დაბრუნების გვერდზე.</p>
<ul>
  <li>ელფოსტა: <a href="mailto:support@automate.ge">support@automate.ge</a></li>
  <li>ტელეფონი: <a href="tel:+995555010203">+995 555 01 02 03</a></li>
  <li>დაბრუნებისა და refund-ის დეტალები აღწერილია Returns გვერდზე.</li>
</ul>
""".strip(),
    },
)


def seed_payment_methods_georgian_content(apps, schema_editor):
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
            "footer_order": 20,
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
    if page.footer_order != 20:
        page.footer_order = 20
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
        ("pages", "0028_returns_policy_georgian_content"),
    ]

    operations = [
        migrations.RunPython(
            seed_payment_methods_georgian_content,
            migrations.RunPython.noop,
        ),
    ]
