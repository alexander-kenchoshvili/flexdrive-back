from django.db import migrations


COMPONENT_TYPE_NAME = "Terms"
CONTENT_NAME = "terms_sections"
PAGE_SLUG = "terms"
PAGE_NAME = "წესები და პირობები"
FOOTER_LABEL = "წესები და პირობები"
SECTION_TITLE = "წესები და პირობები"
SECTION_SUBTITLE = (
    "ამ გვერდზე აღწერილია AutoMate-ის ვებსაიტის გამოყენების, ანგარიშების, შეკვეთების, "
    "გადახდისა და შეკვეთის ძირითადი პირობები როგორც სტუმარი, ისე რეგისტრირებული მომხმარებლისთვის."
)
SEO_TITLE = "წესები და პირობები | AutoMate"
SEO_DESCRIPTION = (
    "გაიგე რა წესები ვრცელდება AutoMate-ის საიტის გამოყენებაზე, შეკვეთებზე, გადახდაზე, "
    "მიწოდების მოკლე პირობებსა და თანხის დაბრუნების ძირითად ჩარჩოზე."
)
SECTION_CONTENT_TYPE = "terms_section"

ACCOUNT_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 12C14.4853 12 16.5 9.98528 16.5 7.5C16.5 5.01472 14.4853 3 12 3C9.51472 3 7.5 5.01472 7.5 7.5C7.5 9.98528 9.51472 12 12 12Z" stroke="currentColor" stroke-width="1.8"/>
  <path d="M4 20.25C4.8 16.98 7.93 14.75 12 14.75C16.07 14.75 19.2 16.98 20 20.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

PRICING_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M4.75 8.25L10.25 2.75H18.5C19.6 2.75 20.5 3.65 20.5 4.75V13L15 18.5L4.75 8.25Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <circle cx="16.25" cy="7" r="1.25" fill="currentColor"/>
</svg>
""".strip()

ORDER_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="5" y="3.5" width="14" height="17" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M9 8.25H15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 12H15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 15.75H12.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

PAYMENT_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M3.5 10H20.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M7.5 14.25H10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

DELIVERY_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M3.5 6.5H14.5V15.5H3.5V6.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M14.5 9H18.1L20.5 11.6V15.5H14.5V9Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <circle cx="7.5" cy="17.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>
  <circle cx="17.5" cy="17.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

RETURNS_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 7H18V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M18 7L15.25 4.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M18 7L20.75 4.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M16 17H6V7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M6 17L3.25 19.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M6 17L8.75 19.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

LEGAL_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 3L19 6V11.4C19 15.72 16.09 19.74 12 21C7.91 19.74 5 15.72 5 11.4V6L12 3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M9 10.5H15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M9 13.75H13.25" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "საიტის გამოყენება და ანგარიშის ტიპები",
        "description": (
            "AutoMate-ზე შეკვეთა შესაძლებელია როგორც სტუმრის რეჟიმში, ისე რეგისტრაციის შემდეგ. "
            "ანგარიშის ქონა დამატებით გაძლევს შეკვეთების ისტორიისა და სტატუსის ნახვის შესაძლებლობას."
        ),
        "icon_svg": ACCOUNT_ICON,
        "editor": """
<p>AutoMate-ის გამოყენებით ეთანხმებით, რომ საიტს გამოიყენებთ კეთილსინდისიერად, ზუსტი ინფორმაციის მითითებით და მოქმედი კანონმდებლობის დაცვით. შეკვეთის გაფორმება შესაძლებელია როგორც რეგისტრირებული პროფილით, ისე მის გარეშე.</p>
<p>რეგისტრირებულ მომხმარებელს პროფილში შეუძლია საკუთარი შეკვეთების ისტორიის ნახვა, შეკვეთების სტატუსზე თვალყურის დევნება და მომავალი შეკვეთების უფრო სწრაფად გაფორმება. სტუმრის რეჟიმში შეკვეთის გაკეთება შესაძლებელია, თუმცა შეკვეთების ისტორია და სტატუსების არქივი ანგარიშში არ შეინახება.</p>
<ul>
  <li>ანგარიშის შექმნისას უნდა მიუთითოთ სწორი და აქტუალური ინფორმაცია.</li>
  <li>თუ გაქვთ პროფილი, პასუხისმგებელი ხართ თქვენი ავტორიზაციის მონაცემების დაცვაზე.</li>
  <li>აკრძალულია საიტის გამოყენება თაღლითური შეკვეთებისთვის, ყალბი მონაცემების მიწოდებისთვის ან პლატფორმის მუშაობის შეფერხების მიზნით.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "პროდუქტები, ფასები და ხელმისაწვდომობა",
        "description": (
            "საიტზე ნაჩვენები პროდუქტის ინფორმაცია, ფასები და მარაგი შეიძლება პერიოდულად განახლდეს. "
            "Terms-ში კონკრეტული პროდუქტების სია არ იწერება; აქ აღწერილია მხოლოდ ზოგადი წესი."
        ),
        "icon_svg": PRICING_ICON,
        "editor": """
<p>საიტზე წარმოდგენილი პროდუქტის აღწერები, სურათები, ფასები და ხელმისაწვდომობა განთავსებულია ინფორმაციის მისაწოდებლად და შეიძლება დროთა განმავლობაში განახლდეს. კონკრეტული პროდუქტის აქტუალური ფასი და სტატუსი ყოველთვის მის შესაბამის კატალოგის ან პროდუქტის გვერდზე უნდა გადაამოწმოთ.</p>
<p>მარაგი შეიძლება შეიცვალოს შეკვეთებს შორის პერიოდში. აგრეთვე შეიძლება საჭირო გახდეს პროდუქტის აღწერის, ფოტოს, მახასიათებლების ან ფასის დაზუსტება, თუ დაფიქსირდა ტექნიკური ან ოპერატიული შეცდომა.</p>
<ul>
  <li>ფასები და ხელმისაწვდომობა შეიძლება შეიცვალოს წინასწარი შეტყობინების გარეშე.</li>
  <li>აშკარა ტექნიკური შეცდომის შემთხვევაში შეკვეთის დადასტურებამდე შეიძლება დაგიკავშირდეთ ინფორმაციის დასაზუსტებლად.</li>
  <li>Terms გვერდზე კონკრეტული პროდუქტების ინდივიდუალური პირობები სათითაოდ არ იწერება.</li>
</ul>
""".strip(),
    },
    {
        "position": 3,
        "title": "შეკვეთის გაფორმება და დადასტურება",
        "description": (
            "შეკვეთის გაგზავნა ნიშნავს order request-ის დაფიქსირებას. "
            "საბოლოო დადასტურება ხდება მას შემდეგ, რაც შეკვეთა გადამოწმდება და დამუშავდება."
        ),
        "icon_svg": ORDER_ICON,
        "editor": """
<p>როდესაც მომხმარებელი საიტზე ავსებს საჭირო ველებს და აგზავნის შეკვეთას, ეს ნიშნავს შეკვეთის მოთხოვნის დაფიქსირებას. შეკვეთის გაგზავნა თავისთავად არ ნიშნავს, რომ შეკვეთა ავტომატურად საბოლოოდ მიღებულია.</p>
<p>AutoMate უფლებას იტოვებს შეკვეთის დამუშავებამდე გადაამოწმოს მარაგი, მიწოდების შესაძლებლობა, საკონტაქტო დეტალები და აშკარა ტექნიკური შეუსაბამობები. საჭიროების შემთხვევაში მომხმარებელს დამატებით დაუკავშირდება შეკვეთის დასადასტურებლად ან დასაზუსტებლად.</p>
<ul>
  <li>მომხმარებელი ვალდებულია სწორად შეავსოს სახელი, ტელეფონი, მისამართი და სხვა შეკვეთისთვის საჭირო ინფორმაცია.</li>
  <li>თუ შეკვეთის შესრულება შეუძლებელია, მომხმარებელს ეცნობება გონივრულ ვადაში.</li>
  <li>შეკვეთის სტატუსზე თვალყურის დევნება პროფილიდან ხელმისაწვდომია მხოლოდ რეგისტრირებული ანგარიშისთვის.</li>
</ul>
""".strip(),
    },
    {
        "position": 4,
        "title": "გადახდის პირობები",
        "description": (
            "ამ ეტაპზე აქტიურია ნაღდი ანგარიშსწორება. ონლაინ ბარათით გადახდა დაემატება მოგვიანებით "
            "და ამის შემდეგ შესაბამის პირობებსაც ცალკე განვაახლებთ."
        ),
        "icon_svg": PAYMENT_ICON,
        "editor": """
<p>ამ ეტაპზე AutoMate-ზე აქტიურია ნაღდი ანგარიშსწორება შეკვეთის მიღების დროს. მომხმარებელი თანხას იხდის კურიერთან ან შეკვეთის ჩაბარების მომენტში, შეთანხმებული წესის შესაბამისად.</p>
<p>ონლაინ ბარათით გადახდის ფუნქცია დაგეგმილია და დაემატება მოგვიანებით. როდესაც ეს მეთოდი ხელმისაწვდომი გახდება, შესაბამისი წესები, ტექნიკური დეტალები და თანხის დაბრუნების პრაქტიკა Terms-ში და სხვა შესაბამის გვერდებზე განახლდება.</p>
<ul>
  <li>მომხმარებელი ვალდებულია შეკვეთის გაფორმებისას აირჩიოს ხელმისაწვდომი და რეალურად მოქმედი გადახდის მეთოდი.</li>
  <li>თუ მომავალში ჩაირთვება ბარათით გადახდა, სისტემა შეკვეთის გაფორმებამდე მკაფიოდ აჩვენებს ამ მეთოდის ხელმისაწვდომობას.</li>
  <li>საიტზე შეიძლება ნაჩვენები იყოს მომავალი გადახდის მეთოდები, თუმცა აქტიურ მეთოდად ჩაითვლება მხოლოდ ის, რაც checkout-ზე რეალურად არის ჩასართველი.</li>
</ul>
""".strip(),
    },
    {
        "position": 5,
        "title": "მიწოდების მოკლე პირობები",
        "description": (
            "თბილისში შეკვეთების ნაწილი შეიძლება იმავე დღესვე მიეწოდოს, ხოლო რეგიონებში "
            "სტანდარტული მიწოდება დაგეგმილია 1-5 სამუშაო დღეში."
        ),
        "icon_svg": DELIVERY_ICON,
        "editor": """
<p>AutoMate ცდილობს შეკვეთები ჩააბაროს გონივრულ და წინასწარ გამოცხადებულ ვადებში. ამ ეტაპზე მოქმედი ძირითადი ჩარჩო ასეთია:</p>
<ul>
  <li>თბილისში: თუ შეკვეთა გაფორმდა 13:00-მდე, მიწოდება იგეგმება იმავე დღეს.</li>
  <li>თბილისში: თუ შეკვეთა გაფორმდა 13:00-ის შემდეგ, მიწოდება იგეგმება მომდევნო სამუშაო დღეს.</li>
  <li>რეგიონებში: სტანდარტული მიწოდების ვადა არის 1-5 სამუშაო დღე.</li>
</ul>
<p>მიწოდების ვადაზე შეიძლება გავლენა იქონიოს მისამართის დაზუსტებამ, პროდუქტის მარაგმა, მაღალი დატვირთვის პერიოდმა, ამინდის ან ლოჯისტიკურმა შეფერხებებმა. ასეთ შემთხვევაში მომხმარებელს შეძლებისდაგვარად წინასწარ ან დაუყოვნებლივ ეცნობება ცვლილების შესახებ.</p>
<p>მიწოდების უფრო დეტალური წესები, ზონები, შეზღუდვები და გამონაკლისები ეტაპობრივად აისახება შესაბამის Delivery გვერდზეც.</p>
""".strip(),
    },
    {
        "position": 6,
        "title": "დაბრუნება და თანხის დაბრუნება",
        "description": (
            "დაბრუნების მოთხოვნა ამ ეტაპზე მიიღება ელფოსტით. "
            "Ordinary return-ის ჩარჩო არის 14 კალენდარული დღე, ხოლო არასწორი ან დეფექტიანი ნივთისთვის მოქმედებს ცალკე პროცესი."
        ),
        "icon_svg": RETURNS_ICON,
        "editor": """
<p>თუ მომხმარებელს სურს პროდუქტის დაბრუნება, ამ ეტაპზე მოთხოვნა უნდა გამოგზავნოს ელფოსტაზე. წერილში უნდა იყოს მითითებული შეკვეთის ნომერი, სახელი, საკონტაქტო ნომერი, დასაბრუნებელი პროდუქტი და დაბრუნების მიზეზი. თუ ნივთი დაზიანებულია ან არასწორი პროდუქტი მოვიდა, რეკომენდებულია ფოტოს ან ვიდეოს დართვაც.</p>
<p>თუ მომხმარებელი უბრალოდ უარს ამბობს შეკვეთაზე და პროდუქტი შეესაბამება აღწერას, დაბრუნების ძირითადი ჩარჩო არის 14 კალენდარული დღე პროდუქტის მიღებიდან, კანონით გათვალისწინებული გამონაკლისების გარდა. ასეთ შემთხვევაში დაბრუნების პირდაპირი ხარჯი, როგორც წესი, მომხმარებელს ეკისრება, თუ სხვა რამ არ იქნება წინასწარ შეთანხმებული.</p>
<p>თუ პროდუქტი დეფექტიანია, დაზიანებულია ან მიწოდებულია არასწორი ნივთი, AutoMate განიხილავს შეცვლას, შეკეთებას ან თანხის დაბრუნებას შემთხვევის ხასიათის მიხედვით. ასეთ სიტუაციაში დაბრუნების ტრანსპორტირების ხარჯი, როგორც წესი, მაღაზიის მხარეს არის.</p>
<ul>
  <li>დაბრუნების მოთხოვნა: <a href="mailto:returns@automate.ge">returns@automate.ge</a></li>
  <li>Refund-ის ძირითადი ვადა: მოთხოვნის მიღებიდან ან დაბრუნებული ნივთის დადასტურებიდან არაუგვიანეს 14 კალენდარული დღისა.</li>
  <li>თუ მომავალში ჩაირთვება ბარათით გადახდა, თანხა ბარათით გადახდილი შეკვეთებისთვის დაბრუნდება იმავე გადახდის მეთოდით, გარდა იმ შემთხვევისა, როცა სხვა წესი კანონით ან შეთანხმებით განისაზღვრება.</li>
</ul>
<p>დაბრუნებისა და Refund-ის უფრო დეტალური წესები, მათ შორის გამონაკლისები, ეტაპობრივად აისახება ცალკე Returns გვერდზეც.</p>
""".strip(),
    },
    {
        "position": 7,
        "title": "ინტელექტუალური საკუთრება, პასუხისმგებლობა და ცვლილებები",
        "description": (
            "საიტის კონტენტი და ვიზუალური მასალა ეკუთვნის AutoMate-ს ან გამოიყენება კანონიერ საფუძველზე. "
            "Terms შესაძლოა პერიოდულად განახლდეს და აქტუალური ვერსია ყოველთვის აქ გამოქვეყნდება."
        ),
        "icon_svg": LEGAL_ICON,
        "editor": """
<p>თუ სხვაგვარად არ არის აღნიშნული, საიტზე განთავსებული დიზაინი, ლოგო, ტექსტები, ფოტოები, სტრუქტურა და სხვა მასალები ეკუთვნის AutoMate-ს ან გამოიყენება შესაბამისი უფლების საფუძველზე. მათი უნებართვოდ კოპირება, გავრცელება ან კომერციული გამოყენება დაუშვებელია.</p>
<p>AutoMate ცდილობს საიტზე არსებული ინფორმაცია იყოს ზუსტი და მომსახურება იყოს სტაბილური, თუმცა არ არის გამორიცხული ტექნიკური შეფერხება, დროებითი მიუწვდომლობა ან მონაცემების განახლების საჭიროება. ეს Terms არ ზღუდავს მომხმარებლის იმ უფლებებს, რომლებიც მას მოქმედი კანონმდებლობით ენიჭება.</p>
<p>წესები და პირობები შეიძლება პერიოდულად განახლდეს ბიზნეს-პროცესების, გადახდის მეთოდების, მიწოდების პოლიტიკის ან კანონმდებლობის ცვლილების შესაბამისად. განახლებული ვერსია გამოქვეყნდება ამავე გვერდზე და გვერდის თავში გამოჩნდება განახლების თარიღი.</p>
<ul>
  <li>საკონტაქტო მისამართი: <a href="mailto:support@automate.ge">support@automate.ge</a></li>
  <li>დამატებითი შეკითხვებისთვის: <a href="mailto:legal@automate.ge">legal@automate.ge</a></li>
  <li>ტელეფონი: <a href="tel:+995555010203">+995 555 01 02 03</a></li>
</ul>
""".strip(),
    },
)


def seed_terms_georgian_content(apps, schema_editor):
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
            "footer_group": "legal",
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
    if page.footer_group != "legal":
        page.footer_group = "legal"
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
        Component.objects
        .filter(page=page, component_type=component_type)
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

    ContentItem.objects.filter(content=content).exclude(position__in=valid_positions).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0025_privacy_policy_georgian_content"),
    ]

    operations = [
        migrations.RunPython(
            seed_terms_georgian_content,
            migrations.RunPython.noop,
        ),
    ]
