from django.db import migrations


COMPONENT_TYPE_NAME = "PrivacyPolicy"
CONTENT_NAME = "privacy_policy_sections"
PAGE_SLUG = "privacy-policy"
PAGE_NAME = "კონფიდენციალურობის პოლიტიკა"
FOOTER_LABEL = "კონფიდენციალურობა"
SECTION_TITLE = "კონფიდენციალურობის პოლიტიკა"
SECTION_SUBTITLE = (
    "ამ გვერდზე აღწერილია რა ინფორმაციას ამუშავებს AutoMate, რატომ გვჭირდება ეს მონაცემები, "
    "ვისთან შეიძლება გაზიარება და რა არჩევანი გაქვთ თქვენ."
)
SEO_TITLE = "კონფიდენციალურობის პოლიტიკა | AutoMate"
SEO_DESCRIPTION = (
    "გაიგეთ რა მონაცემებს აგროვებს AutoMate, როგორ ვიყენებთ მათ და როგორ შეგიძლიათ "
    "მოითხოვოთ თქვენი ინფორმაციის განახლება ან წაშლა."
)
SECTION_CONTENT_TYPE = "policy_section"

DATA_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="12" cy="5.5" rx="6.5" ry="2.75" stroke="currentColor" stroke-width="1.8"/>
  <path d="M5.5 5.5V12.5C5.5 14.02 8.41 15.25 12 15.25C15.59 15.25 18.5 14.02 18.5 12.5V5.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M5.5 12.5V18.5C5.5 20.02 8.41 21.25 12 21.25C15.59 21.25 18.5 20.02 18.5 18.5V12.5" stroke="currentColor" stroke-width="1.8"/>
</svg>
""".strip()

USE_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 3.5C7.86 3.5 4.5 6.86 4.5 11V19.5L8 17.25L12 19.5L16 17.25L19.5 19.5V11C19.5 6.86 16.14 3.5 12 3.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M9.25 10.75L11.2 12.7L14.9 9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

SHARE_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="6" cy="12" r="2.5" stroke="currentColor" stroke-width="1.8"/>
  <circle cx="18" cy="6" r="2.5" stroke="currentColor" stroke-width="1.8"/>
  <circle cx="18" cy="18" r="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M8.2 10.95L15.8 7.05" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M8.2 13.05L15.8 16.95" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

RETENTION_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="13" r="7.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M12 9V13L14.75 15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M8.5 3.5H15.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
""".strip()

RIGHTS_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 21C16.97 21 21 16.97 21 12V7.5L12 3L3 7.5V12C3 16.97 7.03 21 12 21Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M8.75 12.4L10.85 14.5L15.35 10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

CONTACT_ICON = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3.5" y="5.5" width="17" height="13" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
  <path d="M5.5 8L12 12.75L18.5 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M8 18.5L9.2 20.5H14.8L16 18.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""".strip()

SECTION_DEFINITIONS = (
    {
        "position": 1,
        "title": "რა ინფორმაციას ვაგროვებთ",
        "description": (
            "ანგარიშის, შეკვეთის, მიწოდების და ტექნიკური გამოყენების მონაცემებს იმდენად, "
            "რამდენადაც პლატფორმის მუშაობისთვის გვჭირდება."
        ),
        "icon_svg": DATA_ICON,
        "editor": """
<p>AutoMate ამუშავებს მხოლოდ იმ მონაცემებს, რომლებიც საჭიროა ანგარიშის, შეკვეთის და სერვისის უსაფრთხო მუშაობისთვის. როცა ანგარიშს ქმნით, ავტორიზაციას გადიხართ ან პაროლის აღდგენას იყენებთ, შეიძლება შევაგროვოთ თქვენი სახელი, ელფოსტა, ტელეფონის ნომერი და ავტორიზაციის პროცესთან დაკავშირებული ტექნიკური ინფორმაცია.</p>
<p>შეკვეთის გაკეთებისას შეიძლება დამუშავდეს მიწოდების მისამართი, მიმღების დეტალები, შეკვეთის შემადგენლობა, ფასები, შეკვეთის სტატუსი და თქვენ მიერ მოწოდებული დამატებითი კომენტარები. თუ პროფილს იყენებთ, შეიძლება შევინახოთ სურვილების სია, შეკვეთების ისტორია და ანგარიშთან დაკავშირებული აქტივობა.</p>
<ul>
  <li>ანგარიშისა და ავტორიზაციის მონაცემები: ელფოსტა, პაროლის აღდგენის ან აქტივაციის პროცესთან დაკავშირებული ჩანაწერები.</li>
  <li>შეკვეთის მონაცემები: პროდუქტები, რაოდენობა, მიწოდების ინფორმაცია, შეკვეთის სტატუსი და კომუნიკაციის შენიშვნები.</li>
  <li>ტექნიკური მონაცემები: IP მისამართი, ბრაუზერის ტიპი, სესიის ინფორმაცია, უსაფრთხოების ლოგები და აუცილებელი cookies.</li>
  <li>უსაფრთხოების ინსტრუმენტები: reCAPTCHA-სთან დაკავშირებული სიგნალები, რომლებიც საჭიროა ბოროტად გამოყენების თავიდან ასაცილებლად.</li>
</ul>
""".strip(),
    },
    {
        "position": 2,
        "title": "როგორ ვიყენებთ ინფორმაციას",
        "description": (
            "მონაცემებს ვიყენებთ ანგარიშის მართვისთვის, შეკვეთების დასამუშავებლად, "
            "უსაფრთხოებისთვის და მომხმარებლის მხარდაჭერისთვის."
        ),
        "icon_svg": USE_ICON,
        "editor": """
<p>ჩვენ ვიყენებთ მონაცემებს იმისთვის, რომ საიტმა იმუშაოს პრაქტიკულად და სტაბილურად: შევძლოთ ავტორიზაცია, შეკვეთის მიღება, სტატუსის შეცვლა, მიწოდების კოორდინაცია და მხარდაჭერის გაწევა. უსაფრთხოების ნაწილი ასევე მნიშვნელოვანია, რადგან ავტორიზაციის, პაროლის აღდგენის და ფორმების ბოროტად გამოყენებისგან დაცვა გვჭირდება.</p>
<ul>
  <li>ანგარიშის შექმნა, შესვლა, აქტივაცია და პაროლის აღდგენა.</li>
  <li>შეკვეთის მიღება, დადასტურება, დამუშავება და მიწოდების პროცესის კოორდინაცია.</li>
  <li>მომხმარებლის კითხვებზე პასუხი და პრობლემური შემთხვევების გამოკვლევა.</li>
  <li>უსაფრთხოების მონიტორინგი, თაღლითური ან სპამური აქტივობის შემცირება და სისტემის სტაბილურობის შენარჩუნება.</li>
</ul>
<p>ამ ეტაპზე AutoMate არ იყენებს Google Analytics-ს, სარეკლამო პიქსელებს ან მარკეტინგულ ტრეკინგს. თუ მომავალში დავამატებთ ანალიტიკას, რემარკეტინგს ან სხვა არასავალდებულო tracking ინსტრუმენტებს, ამ პოლიტიკას წინასწარ განვაახლებთ.</p>
""".strip(),
    },
    {
        "position": 3,
        "title": "ვის ვუზიარებთ ინფორმაციას",
        "description": (
            "მონაცემებს ვუზიარებთ მხოლოდ იმ პარტნიორებსა და სერვისებს, რომლებიც აუცილებელია "
            "პლატფორმის მუშაობისთვის."
        ),
        "icon_svg": SHARE_ICON,
        "editor": """
<p>ჩვენ არ ვყიდით თქვენს პერსონალურ მონაცემებს. ინფორმაცია შეიძლება გაეზიაროს მხოლოდ იმ მხარეებს, რომლებიც რეალურად მონაწილეობენ AutoMate-ის მუშაობაში და მხოლოდ იმ მოცულობით, რაც აუცილებელია შესაბამისი ამოცანის შესასრულებლად.</p>
<ul>
  <li>ჰოსტინგისა და ინფრასტრუქტურის მომწოდებლებს, რათა პლატფორმა და API სტაბილურად იმუშაოს.</li>
  <li>reCAPTCHA-ს მომწოდებელს, ფორმებისა და ავტორიზაციის უსაფრთხოების უზრუნველსაყოფად.</li>
  <li>მიწოდების ან შეკვეთის დამუშავებაში ჩართულ ოპერატორებსა და პარტნიორებს, რათა შეკვეთა სწორად ჩაბარდეს.</li>
  <li>კანონით მოთხოვნილ შემთხვევებში შესაბამის უფლებამოსილ ორგანოებს.</li>
</ul>
<p>ონლაინ გადახდის ინტეგრაცია ამ ეტაპზე ჯერ არ არის ჩართული. თუ მომავალში დაემატება გადახდის გეითვეი, პოლიტიკაში ცალკე ავხსნით რომელი გადახდის მონაცემები მუშავდება ჩვენთან და რომელი უშუალოდ საგადახდო პროვაიდერთან.</p>
""".strip(),
    },
    {
        "position": 4,
        "title": "რამდენ ხანს ვინახავთ მონაცემებს",
        "description": (
            "მონაცემებს ვინახავთ იმდენ ხანს, რამდენიც საჭიროა ანგარიშის, შეკვეთების ისტორიისა "
            "და უსაფრთხოების მოთხოვნებისთვის."
        ),
        "icon_svg": RETENTION_ICON,
        "editor": """
<p>შენახვის ვადა დამოკიდებულია მონაცემის ტიპზე და იმაზე, თუ რა მიზანს ემსახურება. სადაც შესაძლებელია, მონაცემებს ვშლით ან ვანონიმურებთ მაშინ, როცა მათი შენახვა აღარ არის საჭირო.</p>
<table>
  <thead>
    <tr>
      <th>მონაცემის ტიპი</th>
      <th>ჩვეულებრივი ვადა</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>ანგარიშის ძირითადი ინფორმაცია</td>
      <td>სანამ ანგარიში აქტიურია ან მის წაშლას არ მოითხოვთ</td>
    </tr>
    <tr>
      <td>შეკვეთები და ოპერაციული ჩანაწერები</td>
      <td>იმდენ ხანს, რამდენიც საჭიროა შეკვეთის მომსახურებისთვის, ისტორიისთვის და იურიდიული/ბუღალტრული მოთხოვნებისთვის</td>
    </tr>
    <tr>
      <td>უსაფრთხოების და ავტორიზაციის ლოგები</td>
      <td>შეზღუდული ვადით, უსაფრთხოების ან პრობლემების დიაგნოსტიკის მიზნებისთვის</td>
    </tr>
    <tr>
      <td>support-თან მიმოწერა</td>
      <td>სანამ საკითხი აქტუალურია და გონივრული შემდგომი მხარდაჭერა შეიძლება დაგვჭირდეს</td>
    </tr>
  </tbody>
</table>
<p>თუ კონკრეტული მონაცემის წაშლას მოითხოვთ, ვეცდებით მოვახდინოთ წაშლა ან ანონიმიზაცია იქ, სადაც ამის გაკეთება შეგვიძლია და სხვა სამართლებრივი ვალდებულება არ გვაკავებს.</p>
""".strip(),
    },
    {
        "position": 5,
        "title": "თქვენი უფლებები და არჩევანი",
        "description": (
            "შეგიძლიათ მოითხოვოთ თქვენი მონაცემების ნახვა, განახლება, წაშლა ან გარკვეული "
            "გამოყენების შეზღუდვა."
        ),
        "icon_svg": RIGHTS_ICON,
        "editor": """
<p>ჩვენ გვსურს, რომ თქვენი მონაცემები იყოს ზუსტი და თქვენზე კონტროლი დაგრჩეთ. ამიტომ შეგიძლიათ მოგვმართოთ, თუ გსურთ იცოდეთ რა ინფორმაცია გვაქვს თქვენზე ან გინდათ მისი კორექტირება.</p>
<ul>
  <li>მოითხოვოთ თქვენს შესახებ შენახული მონაცემების ასლი ან განმარტება.</li>
  <li>გამოასწოროთ არაზუსტი ან მოძველებული ინფორმაცია.</li>
  <li>მოითხოვოთ ანგარიშისა და დაკავშირებული მონაცემების წაშლა იქ, სადაც ეს ტექნიკურად და სამართლებრივად შესაძლებელია.</li>
  <li>გააპროტესტოთ კონკრეტული დამუშავება ან მოითხოვოთ მისი შეზღუდვა.</li>
</ul>
<p>ყველაზე სწრაფი გზა ხშირად თქვენი პროფილის მონაცემების განახლებაა უშუალოდ ანგარიშიდან. თუ ამისთვის საკმარისი შესაძლებლობა არ გაქვთ, შეგიძლიათ მოგვწეროთ და მოთხოვნას ხელით გადავამოწმებთ.</p>
""".strip(),
    },
    {
        "position": 6,
        "title": "კონტაქტი და პოლიტიკის განახლებები",
        "description": (
            "თუ კითხვები გაქვთ, მოგვწერეთ placeholder მისამართებზე; ცვლილებების შემთხვევაში "
            "ამ გვერდს განვაახლებთ."
        ),
        "icon_svg": CONTACT_ICON,
        "editor": """
<p>თუ ამ პოლიტიკასთან, თქვენს მონაცემებთან ან კონკრეტულ შეკვეთასთან დაკავშირებული კითხვა გაქვთ, დაგვიკავშირდით შემდეგ მისამართებზე. ქვემოთ მითითებული ინფორმაცია დროებითი placeholder-ია და საჭიროების შემთხვევაში შეგიძლიათ მოგვიანებით შეცვალოთ ადმინისტრაციიდან.</p>
<ul>
  <li>ელფოსტა: <a href="mailto:privacy@automate.ge">privacy@automate.ge</a></li>
  <li>მხარდაჭერა: <a href="mailto:support@automate.ge">support@automate.ge</a></li>
  <li>ტელეფონი: <a href="tel:+995555010203">+995 555 01 02 03</a></li>
  <li>ქალაქი: თბილისი, საქართველო</li>
</ul>
<blockquote>
  <p>როცა AutoMate-ს დაემატება ახალი ფუნქციები, მაგალითად ანალიტიკა, ონლაინ გადახდა ან დამატებითი მარკეტინგული ინსტრუმენტები, ამ პოლიტიკასაც შესაბამისად განვაახლებთ.</p>
</blockquote>
<p>გვირჩევნია ეს გვერდი იყოს ცხადი და პრაქტიკული, ამიტომ ცვლილებებს სწორედ აქ გამოვაქვეყნებთ და განახლების თარიღიც ზემოთ გამოჩნდება.</p>
""".strip(),
    },
)


def seed_privacy_policy_georgian_content(apps, schema_editor):
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
    if page.footer_group != "legal":
        page.footer_group = "legal"
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
        ("pages", "0024_seed_privacy_policy_component"),
    ]

    operations = [
        migrations.RunPython(
            seed_privacy_policy_georgian_content,
            migrations.RunPython.noop,
        ),
    ]
