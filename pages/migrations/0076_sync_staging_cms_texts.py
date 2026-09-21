from django.db import migrations


PAGES = [{'url': None,
  'name': 'ჩვენ შესახებ',
  'slug': 'about-us',
  'order': 39,
  'seo_title': 'ჩვენ შესახებ | FlexDrive',
  'seo_noindex': False,
  'footer_group': 'navigation',
  'footer_label': 'ჩვენ შესახებ',
  'footer_order': 45,
  'show_in_menu': True,
  'show_in_footer': True,
  'seo_description': 'FlexDrive ქმნის ავტონაწილების ყიდვის უფრო მარტივ გზას მკაფიო კატალოგით, გასაგები checkout-ით და '
                     'შეკვეთის სტატუსის გადამოწმებით.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'კონტაქტი',
  'slug': 'contact',
  'order': 45,
  'seo_title': 'კონტაქტი | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'navigation',
  'footer_label': 'კონტაქტი',
  'footer_order': 50,
  'show_in_menu': True,
  'show_in_footer': True,
  'seo_description': 'დაუკავშირდი FlexDrive-ს შეკვეთის, ავტონაწილის, მიწოდების ან დაბრუნების საკითხებზე. საკონტაქტო '
                     'ფორმა, არხები და სასარგებლო ბმულები ერთ გვერდზე.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'მიწოდება',
  'slug': 'delivery',
  'order': 0,
  'seo_title': 'მიწოდების პირობები | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'help',
  'footer_label': 'მიწოდება',
  'footer_order': 10,
  'show_in_menu': False,
  'show_in_footer': True,
  'seo_description': 'FlexDrive-ის მიწოდების პირობები: შეკვეთის დადასტურება, მიწოდების ვადები თბილისსა და რეგიონებში, '
                     'მისამართის სიზუსტე და მხარდაჭერა.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'შეკვეთის სტატუსი',
  'slug': 'order-status',
  'order': 30,
  'seo_title': 'შეკვეთის სტატუსის შემოწმება | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'help',
  'footer_label': 'შეკვეთის სტატუსი',
  'footer_order': 40,
  'show_in_menu': True,
  'show_in_footer': True,
  'seo_description': 'FlexDrive-ზე სტუმრის შეკვეთის სტატუსის შემოწმება შეკვეთის ნომრით და ტელეფონის ნომრით.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'გადახდის მეთოდები',
  'slug': 'payment-methods',
  'order': 0,
  'seo_title': 'გადახდის მეთოდები | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'help',
  'footer_label': 'გადახდის მეთოდები',
  'footer_order': 20,
  'show_in_menu': False,
  'show_in_footer': True,
  'seo_description': 'FlexDrive-ის გადახდის მეთოდები: ბარათით ონლაინ გადახდის წესი, გადახდის დადასტურება და თანხის '
                     'დაბრუნება.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'კონფიდენციალურობის პოლიტიკა',
  'slug': 'privacy-policy',
  'order': 0,
  'seo_title': 'კონფიდენციალურობის პოლიტიკა | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'legal',
  'footer_label': 'კონფიდენციალურობა',
  'footer_order': 10,
  'show_in_menu': False,
  'show_in_footer': True,
  'seo_description': 'FlexDrive-ის კონფიდენციალურობის პოლიტიკა: პერსონალური მონაცემები, ქუქები, ანალიტიკა, მარკეტინგი, '
                     'გადახდის პროვაიდერები და მომხმარებლის უფლებები.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'დაბრუნება',
  'slug': 'returns',
  'order': 0,
  'seo_title': 'პროდუქტისა და თანხის დაბრუნება | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'help',
  'footer_label': 'დაბრუნება',
  'footer_order': 30,
  'show_in_menu': False,
  'show_in_footer': True,
  'seo_description': 'FlexDrive-ის დაბრუნების პირობები: დაბრუნების მოთხოვნა, პროდუქტის მდგომარეობა, დეფექტიანი ან '
                     'არასწორი პროდუქტი, დაბრუნების ხარჯი და თანხის დაბრუნება.',
  'seo_canonical_url': None},
 {'url': None,
  'name': 'წესები და პირობები',
  'slug': 'terms',
  'order': 0,
  'seo_title': 'წესები და პირობები | FlexDrive',
  'seo_noindex': True,
  'footer_group': 'legal',
  'footer_label': 'წესები და პირობები',
  'footer_order': 20,
  'show_in_menu': False,
  'show_in_footer': True,
  'seo_description': 'FlexDrive-ის წესები და პირობები: ავტონაწილების ონლაინ შეკვეთა, ტაივანური ნაწილების თავსებადობა, '
                     'გადახდა, მიწოდება, დაბრუნება და B2B შეკვეთები.',
  'seo_canonical_url': None}]

COMPONENTS = [{'title': 'Flex[[Drive]]-ის შესახებ',
  'enabled': True,
  'position': 10,
  'subtitle': 'Flex[[Drive]] ვქმნით ავტონაწილების ყიდვის მარტივ გზას: მკაფიო კატალოგი, გასაგები Checkout და შეკვეთის '
              'სტატუსი ერთ სივრცეში. ჩვენი მიზანია, მომხმარებელს შევთავაზოთ სრულიად ახალი გამოცდილება ხარისხსა და '
              'მომსახურებაში.',
  'page_slug': 'about-us',
  'button_text': None,
  'content_name': 'about_us_page_content',
  'component_type': 'AboutUs'},
 {'title': None,
  'enabled': True,
  'position': 10,
  'subtitle': None,
  'page_slug': 'contact',
  'button_text': None,
  'content_name': 'contact_page_content',
  'component_type': 'Contact'},
 {'title': 'მიწოდების პირობები',
  'enabled': True,
  'position': 10,
  'subtitle': 'თბილისში მიწოდება ხორციელდება ორშაბათიდან შაბათის ჩათვლით, შეკვეთის გაფორმების დროის მიხედვით. '
              'რეგიონებში მიწოდების ვადაა 4-5 სამუშაო დღე შეკვეთის დადასტურებიდან.',
  'page_slug': 'delivery',
  'button_text': None,
  'content_name': 'delivery_sections',
  'component_type': 'Delivery'},
 {'title': 'შეკვეთის სტატუსი',
  'enabled': True,
  'position': 10,
  'subtitle': 'შეიყვანეთ შეკვეთის ნომერი და ტელეფონის ნომერი, რომ ნახოთ შეკვეთის მიმდინარე მდგომარეობა.',
  'page_slug': 'order-status',
  'button_text': None,
  'content_name': 'order_status_content',
  'component_type': 'OrderStatus'},
 {'title': 'გადახდის მეთოდები',
  'enabled': True,
  'position': 10,
  'subtitle': 'FlexDrive-ზე შეკვეთის გადახდა შესაძლებელია მხოლოდ საბანკო ბარათით, ონლაინ.',
  'page_slug': 'payment-methods',
  'button_text': None,
  'content_name': 'payment_methods_sections',
  'component_type': 'PaymentMethods'},
 {'title': 'კონფიდენციალურობის პოლიტიკა',
  'enabled': True,
  'position': 10,
  'subtitle': 'ამ გვერდზე მოკლედ არის აღწერილი რა მონაცემებს ამუშავებს FlexDrive, რისთვის ვიყენებთ მათ, ვის შეიძლება '
              'გადაეცეს ინფორმაცია და როგორ შეგიძლიათ თქვენი უფლებებით სარგებლობა.',
  'page_slug': 'privacy-policy',
  'button_text': None,
  'content_name': 'privacy_policy_sections',
  'component_type': 'PrivacyPolicy'},
 {'title': 'პროდუქტისა და თანხის დაბრუნება',
  'enabled': True,
  'position': 10,
  'subtitle': 'ამ გვერდზე აღწერილია FlexDrive-ზე შეძენილი ავტონაწილების დაბრუნების მოთხოვნის ძირითადი წესი, ვადები, '
              'ნივთის მდგომარეობის მოთხოვნები და თანხის დაბრუნების პროცესი.',
  'page_slug': 'returns',
  'button_text': None,
  'content_name': 'returns_sections',
  'component_type': 'Returns'},
 {'title': 'წესები და პირობები',
  'enabled': True,
  'position': 10,
  'subtitle': 'ეს გვერდი აღწერს FlexDrive-ზე საიტის გამოყენების, ანგარიშის, ავტონაწილების შერჩევის, შეკვეთის, '
              'გადახდის, მიწოდებისა და დაბრუნების ძირითად პირობებს. დეტალური ინსტრუქციები შესაბამის გვერდებზეა '
              'მოცემული.',
  'page_slug': 'terms',
  'button_text': None,
  'content_name': 'terms_sections',
  'component_type': 'Terms'}]

CONTENT_ITEMS = [{'slug': 'eyebrow',
  'title': 'ავტონაწილების ონლაინ მაღაზია',
  'editor': None,
  'icon_svg': None,
  'position': 5,
  'description': None,
  'content_name': 'about_us_page_content',
  'content_type': 'about_eyebrow',
  'single_page_slug': None},
 {'slug': 'summary',
  'title': 'რას იღებს მომხმარებელი',
  'editor': None,
  'icon_svg': None,
  'position': 100,
  'description': 'Flex[[Drive]] არის პრაქტიკული სივრცე ნაწილის მოძებნისა და შეკვეთისთვის.',
  'content_name': 'about_us_page_content',
  'content_type': 'about_panel',
  'single_page_slug': None},
 {'slug': 'catalog',
  'title': 'კატალოგი',
  'editor': None,
  'icon_svg': None,
  'position': 200,
  'description': 'კატეგორიები, ბრენდები და სწრაფი ძიება.',
  'content_name': 'about_us_page_content',
  'content_type': 'about_feature',
  'single_page_slug': None},
 {'slug': 'payment',
  'title': 'გადახდა',
  'editor': None,
  'icon_svg': None,
  'position': 210,
  'description': 'სწრაფი და უსაფრთხო ონლაინ ტრანზაქცია.',
  'content_name': 'about_us_page_content',
  'content_type': 'about_feature',
  'single_page_slug': None},
 {'slug': 'status',
  'title': 'სტატუსი',
  'editor': None,
  'icon_svg': None,
  'position': 220,
  'description': 'შეკვეთის მიმდინარეობის მარტივი გადამოწმება.',
  'content_name': 'about_us_page_content',
  'content_type': 'about_feature',
  'single_page_slug': None},
 {'slug': 'catalog',
  'title': 'კატალოგის ნახვა',
  'editor': None,
  'icon_svg': None,
  'position': 300,
  'description': None,
  'content_name': 'about_us_page_content',
  'content_type': 'about_action',
  'single_page_slug': None},
 {'slug': 'order-status',
  'title': 'შეკვეთის სტატუსი',
  'editor': None,
  'icon_svg': None,
  'position': 310,
  'description': None,
  'content_name': 'about_us_page_content',
  'content_type': 'about_action',
  'single_page_slug': None},
 {'slug': 'product',
  'title': 'პროდუქტის შესახებ',
  'editor': None,
  'icon_svg': None,
  'position': 10,
  'description': 'დაზუსტება პროდუქტის მახასიათებლებზე, თავსებადობაზე ან არჩევაზე.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_topic',
  'single_page_slug': None},
 {'slug': 'order-status',
  'title': 'შეკვეთის სტატუსი',
  'editor': None,
  'icon_svg': None,
  'position': 20,
  'description': 'ინფორმაცია მიმდინარე შეკვეთის ეტაპზე, დამუშავებაზე ან სტატუსზე.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_topic',
  'single_page_slug': None},
 {'slug': 'delivery',
  'title': 'მიწოდება',
  'editor': None,
  'icon_svg': None,
  'position': 30,
  'description': 'ვადები, მისამართი, რეგიონები და მიწოდების პრაქტიკული კითხვები.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_topic',
  'single_page_slug': None},
 {'slug': 'returns',
  'title': 'დაბრუნება',
  'editor': None,
  'icon_svg': None,
  'position': 40,
  'description': 'დაბრუნების მოთხოვნა, დეფექტიანი ნივთი ან თანხის დაბრუნება.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_topic',
  'single_page_slug': None},
 {'slug': 'other',
  'title': 'სხვა',
  'editor': None,
  'icon_svg': None,
  'position': 50,
  'description': 'ნებისმიერი სხვა საკითხი, რომელიც ზემოთ ჩამოთვლილებში არ ჯდება.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_topic',
  'single_page_slug': None},
 {'slug': 'support_intro',
  'title': 'სად დაგვიკავშირდეთ',
  'editor': '',
  'icon_svg': None,
  'position': 110,
  'description': '',
  'content_name': 'contact_page_content',
  'content_type': 'contact_notice',
  'single_page_slug': None},
 {'slug': 'response_note',
  'title': 'როდის მიიღებთ პასუხს',
  'editor': '<ul>\n'
            '  <li>თუ წერილი შეკვეთის ნომრით მოგვწერეთ, საკითხის მოძიება უფრო სწრაფად მოხდება.</li>\n'
            '  <li>თუ კითხვა მიწოდებას ან დაბრუნებას ეხება, ქვემოთ მოცემულ სწრაფ ბმულებშიც დაგხვდებათ დამატებითი '
            'განმარტებები.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 120,
  'description': 'სამუშაო საათებში შეტყობინებებს მაქსიმალურად სწრაფად ვამუშავებთ, არასამუშაო დროს კი მომდევნო სამუშაო '
                 'დღეს გიპასუხებთ.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_notice',
  'single_page_slug': None},
 {'slug': 'shortcuts_intro',
  'title': 'სანამ მოგვწერთ, ჯერ აქაც გადახედეთ',
  'editor': None,
  'icon_svg': None,
  'position': 130,
  'description': 'ყველაზე ხშირი პროცესები უკვე ცალკე გვერდებად გვაქვს დალაგებული, რათა საჭირო პასუხი სწრაფად იპოვოთ.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_notice',
  'single_page_slug': None},
 {'slug': 'expectations_intro',
  'title': 'რას უნდა ელოდოთ პასუხისგან',
  'editor': None,
  'icon_svg': None,
  'position': 140,
  'description': 'ყოველი მოთხოვნა ჯერ ფიქსირდება, შემდეგ კონტექსტის მიხედვით მოწმდება და ბოლოს სწორ პროცესზე გადადის.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_notice',
  'single_page_slug': None},
 {'slug': 'reasons_intro',
  'title': 'რით შეგვიძლია დაგეხმაროთ',
  'editor': None,
  'icon_svg': None,
  'position': 150,
  'description': 'კონტაქტის გვერდი ყველაზე სასარგებლოა მაშინ, როცა გჭირდება პროდუქტის, შეკვეთის ან პროცესის დაზუსტება.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_notice',
  'single_page_slug': None},
 {'slug': 'delivery',
  'title': 'მიწოდება',
  'editor': None,
  'icon_svg': '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
              '  <path d="M3.75 7.5H14.25V15.75H3.75V7.5Z" stroke="currentColor" stroke-width="1.8" '
              'stroke-linejoin="round"/>\n'
              '  <path d="M14.25 10H17.5L20.25 12.75V15.75H14.25V10Z" stroke="currentColor" stroke-width="1.8" '
              'stroke-linejoin="round"/>\n'
              '  <circle cx="7.75" cy="16.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>\n'
              '  <circle cx="17" cy="16.5" r="1.75" stroke="currentColor" stroke-width="1.8"/>\n'
              '</svg>',
  'position': 200,
  'description': 'ვადები, თბილისი/რეგიონები და მისამართის დეტალები.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_shortcut',
  'single_page_slug': 'delivery'},
 {'slug': 'payment-methods',
  'title': 'გადახდის მეთოდები',
  'editor': None,
  'icon_svg': '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
              '  <rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>\n'
              '  <path d="M3.5 10H20.5" stroke="currentColor" stroke-width="1.8"/>\n'
              '  <path d="M7.5 14.5H12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>\n'
              '</svg>',
  'position': 210,
  'description': 'ხელმისაწვდომი გადახდის გზები და წარუმატებელი ტრანზაქციის სცენარები.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_shortcut',
  'single_page_slug': 'payment-methods'},
 {'slug': 'returns',
  'title': 'დაბრუნება',
  'editor': None,
  'icon_svg': '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
              '  <path d="M7 8.75H14.75C16.54 8.75 18 10.21 18 12C18 13.79 16.54 15.25 14.75 15.25H6.75" '
              'stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>\n'
              '  <path d="M9 6.5L6 8.75L9 11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
              'stroke-linejoin="round"/>\n'
              '  <path d="M11 12H14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>\n'
              '</svg>',
  'position': 220,
  'description': '14-დღიანი დაბრუნება, დეფექტიანი ნივთი და refund-ის ლოგიკა.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_shortcut',
  'single_page_slug': 'returns'},
 {'slug': 'catalog',
  'title': 'კატალოგი',
  'editor': None,
  'icon_svg': '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
              '  <rect x="4" y="4" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>\n'
              '  <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>\n'
              '  <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>\n'
              '  <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.8"/>\n'
              '</svg>',
  'position': 230,
  'description': 'გადადი ყველა პროდუქტზე და გადაამოწმე აქტუალური შეთავაზებები.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_shortcut',
  'single_page_slug': 'catalog'},
 {'slug': None,
  'title': 'მოთხოვნის დაფიქსირება',
  'editor': None,
  'icon_svg': None,
  'position': 300,
  'description': 'შეტყობინება ინახება სისტემაში და არ იკარგება მაშინაც, როცა პასუხი სამუშაო საათებს სცდება.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_expectation',
  'single_page_slug': None},
 {'slug': None,
  'title': 'კონტექსტის გადამოწმება',
  'editor': None,
  'icon_svg': None,
  'position': 310,
  'description': 'თუ შეტყობინება შეკვეთას ეხება, ვამოწმებთ შეკვეთის ნომერს, სტატუსს და შესაბამის დეტალებს.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_expectation',
  'single_page_slug': None},
 {'slug': None,
  'title': 'სწორი არხით დახმარება',
  'editor': None,
  'icon_svg': None,
  'position': 320,
  'description': 'გიპასუხებთ იმ პროცესით, რომელიც რეალურად საჭიროა: პროდუქტის დაზუსტება, შეკვეთის სტატუსი, მიწოდება თუ '
                 'დაბრუნება.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_expectation',
  'single_page_slug': None},
 {'slug': None,
  'title': 'პროდუქტის დაზუსტება',
  'editor': None,
  'icon_svg': None,
  'position': 400,
  'description': 'თუ არჩევანს ადარებ ან თავსებადობა გაინტერესებს, ფორმით მოგვწერე კონკრეტული კითხვა.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_reason',
  'single_page_slug': None},
 {'slug': None,
  'title': 'შეკვეთის სტატუსი',
  'editor': None,
  'icon_svg': None,
  'position': 410,
  'description': 'რეგისტრირებული მომხმარებელი სტატუსს პროფილიდანაც ხედავს, მაგრამ საჭიროების შემთხვევაში ჩვენც '
                 'მოგიძიებთ ინფორმაციას.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_reason',
  'single_page_slug': None},
 {'slug': None,
  'title': 'მიწოდება, დაბრუნება და გადახდა',
  'editor': None,
  'icon_svg': None,
  'position': 420,
  'description': 'თუ გჭირდება კონკრეტული წესის ან გამონაკლისის დაზუსტება, კონტაქტის გვერდი პირდაპირი გასასვლელია ჩვენი '
                 'გუნდისკენ.',
  'content_name': 'contact_page_content',
  'content_type': 'contact_reason',
  'single_page_slug': None},
 {'slug': None,
  'title': 'როდის იწყება მიწოდების ვადა',
  'editor': '<p>თბილისში მიწოდების დღე განისაზღვრება შეკვეთის გაფორმების დროის მიხედვით, ქვემოთ მოცემული გრაფიკის '
            'შესაბამისად. რეგიონებში მიწოდების ვადის ათვლა იწყება შეკვეთის დადასტურებიდან.</p>\n'
            '<p>შეკვეთის გაფორმების შემდეგ FlexDrive ამოწმებს შეკვეთის მონაცემებს, პროდუქტის ხელმისაწვდომობას, '
            'საკონტაქტო ნომერს და მიწოდების მისამართს. თუ საჭიროა მისამართის, ტელეფონის, პროდუქტის ან გადახდის დეტალის '
            'დაზუსტება, მიწოდება შეიძლება შეფერხდეს. ასეთ შემთხვევაში მომხმარებელს დავუკავშირდებით და მიწოდების დროს '
            'შევათანხმებთ.</p>\n'
            '<ul>\n'
            '  <li>ონლაინ გადახდისას შეკვეთის დამუშავება დამოკიდებულია გადახდის წარმატებულ დადასტურებაზეც.</li>\n'
            '  <li>მიწოდების შესაძლო ხარჯი, თუ ასეთი არსებობს, checkout-ში გამოჩნდება შეკვეთის დადასტურებამდე.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 1,
  'description': 'თბილისში მიწოდების დღე განისაზღვრება შეკვეთის გაფორმების დროის მიხედვით, ხოლო რეგიონებში მიწოდების '
                 'ვადა ითვლება შეკვეთის დადასტურებიდან.',
  'content_name': 'delivery_sections',
  'content_type': 'delivery_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'მიწოდების ვადები',
  'editor': '<p><strong>თბილისში მიწოდება</strong></p>\n'
            '<p>ორშაბათიდან შაბათის ჩათვლით, 14:00 საათამდე გაფორმებულ შეკვეთას იმავე დღეს მოგაწვდით, ხოლო 14:00 '
            'საათიდან გაფორმებულ შეკვეთას — მომდევნო დღეს. კვირას მიწოდება არ ხორციელდება — შაბათს 14:00 საათიდან და '
            'კვირას გაფორმებულ შეკვეთებს ორშაბათს მოგაწვდით.</p>\n'
            '<p><strong>რეგიონებში მიწოდება</strong></p>\n'
            '<p>რეგიონებში მიწოდების სტანდარტული ვადაა 4-5 სამუშაო დღე შეკვეთის დადასტურებიდან.</p>\n'
            '<p>თუ კონკრეტულ შეკვეთაზე მიწოდების დროის შეცვლა გახდება საჭირო, მომხმარებელს დამატებით '
            'დავუკავშირდებით.</p>',
  'icon_svg': None,
  'position': 2,
  'description': 'თბილისში 14:00 საათამდე გაფორმებული შეკვეთა იმავე დღეს მოგეწოდებათ, ხოლო 14:00 საათიდან — მომდევნო '
                 'დღეს, კვირის გარდა. შაბათს 14:00 საათიდან და კვირას გაფორმებული შეკვეთები ორშაბათს მოგეწოდებათ. '
                 'რეგიონებში მიწოდების ვადაა 4-5 სამუშაო დღე შეკვეთის დადასტურებიდან.',
  'content_name': 'delivery_sections',
  'content_type': 'delivery_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'მისამართი და ჩაბარება',
  'editor': '<p>შეკვეთის გაფორმებისას მიუთითეთ სრული მისამართი, აქტიური ტელეფონის ნომერი და საჭიროების შემთხვევაში '
            'დამატებითი მითითება კურიერისთვის. არაზუსტი ან არასრული მონაცემები მიწოდებას აფერხებს.</p>\n'
            '<p>შეკვეთის ჩაბარებისას მომხმარებელმა უნდა გადაამოწმოს ამანათის ვიზუალური მდგომარეობა. თუ შეფუთვა ან '
            'პროდუქტი დაზიანებული ჩანს, გადაიღეთ ფოტო და რაც შეიძლება მალე დაგვიკავშირდით.</p>\n'
            '<ul>\n'
            '  <li>მისამართის ცვლილებისას მოგვწერეთ შეკვეთის გაგზავნამდე ან რაც შეიძლება სწრაფად.</li>\n'
            '  <li>თუ ჩაბარება მითითებული მონაცემებით ვერ ხერხდება, FlexDrive მომხმარებელს დაუკავშირდება და მიწოდების '
            'გაგრძელების პირობებს შეათანხმებს.</li>\n'
            '  <li>სტუმრის შეკვეთაზე სტატუსის დასაზუსტებლად საჭიროა შეკვეთის ნომერი და საკონტაქტო ტელეფონი.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 3,
  'description': 'სწორი მისამართი და აქტიური ტელეფონის ნომერი აუცილებელია შეკვეთის დროულად ჩასაბარებლად.',
  'content_name': 'delivery_sections',
  'content_type': 'delivery_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'შეფერხებები და დახმარება',
  'editor': '<p>FlexDrive ცდილობს დაიცვას მითითებული ვადები, თუმცა მიწოდება შეიძლება გადაიწიოს ამინდის, მაღალი '
            'დატვირთვის, სატრანსპორტო შეზღუდვის, კურიერის სამუშაო გრაფიკის ან შეკვეთის მონაცემების დაზუსტების '
            'საჭიროების გამო.</p>\n'
            '<p>შეკვეთის სტატუსის გადამოწმება შეგიძლიათ საიტზე, „შეკვეთის სტატუსის“ გვერდზე, რეგისტრაციის გარეშეც. '
            'რეგისტრირებულ მომხმარებელს შეკვეთების ისტორიისა და სტატუსის ნახვა საკუთარ პროფილშიც შეუძლია.</p>\n'
            '<ul>\n'
            '  <li>ელფოსტა: <a href="mailto:support@flexdrive.ge">support@flexdrive.ge</a></li>\n'
            '  <li>ტელეფონი: <a href="tel:+995557106104">+995 557 10 61 04</a></li>\n'
            '  <li>შეკვეთის ნომერი დაგვეხმარება სტატუსის სწრაფად მოძებნაში.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 4,
  'description': 'მიწოდება შეიძლება გადაიწიოს ამინდის, მაღალი დატვირთვის, კურიერის შეზღუდვის ან მონაცემების დაზუსტების '
                 'საჭიროების გამო.',
  'content_name': 'delivery_sections',
  'content_type': 'delivery_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'ბარათით გადახდა',
  'editor': '<p>გადახდის დასასრულებლად მიჰყევით შეკვეთის გაფორმებისას ნაჩვენებ ინსტრუქციებს. შეკვეთა გადახდილად '
            'ჩაითვლება გადახდის წარმატებით დადასტურების შემდეგ.</p>',
  'icon_svg': None,
  'position': 1,
  'description': 'გადახდის დასასრულებლად მიჰყევით შეკვეთის გაფორმებისას ნაჩვენებ ინსტრუქციებს. შეკვეთა გადახდილად '
                 'ჩაითვლება გადახდის წარმატებით დადასტურების შემდეგ.',
  'content_name': 'payment_methods_sections',
  'content_type': 'payment_method_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'გადახდის სტატუსი',
  'editor': '<p>თუ გადახდა ვერ დასრულდა ან მისი სტატუსი გაურკვეველია, გადაამოწმეთ საბანკო ოპერაცია და შეკვეთის '
            'სტატუსი. თუ თანხა ჩამოგეჭრათ, მაგრამ შეკვეთაზე გადახდა არ დასტურდება, დაგვიკავშირდით და მიუთითეთ შეკვეთის '
            'ნომერი.</p>',
  'icon_svg': None,
  'position': 2,
  'description': 'თუ გადახდა ვერ დასრულდა ან მისი სტატუსი გაურკვეველია, გადაამოწმეთ საბანკო ოპერაცია და შეკვეთის '
                 'სტატუსი. თუ თანხა ჩამოგეჭრათ, მაგრამ შეკვეთაზე გადახდა არ დასტურდება, დაგვიკავშირდით და მიუთითეთ '
                 'შეკვეთის ნომერი.',
  'content_name': 'payment_methods_sections',
  'content_type': 'payment_method_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'გაუქმება და თანხის დაბრუნება',
  'editor': '<p>დადასტურებული დაბრუნების შემთხვევაში თანხა ბრუნდება იმავე გადახდის არხით, რომლითაც შეკვეთა გადაიხადეთ. '
            'თანხის ანგარიშზე ასახვის დრო დამოკიდებულია ბანკზე ან საგადახდო პროვაიდერზე. დეტალური პირობები აღწერილია '
            '<a href="/returns">„პროდუქტისა და თანხის დაბრუნების“</a> გვერდზე.</p>',
  'icon_svg': None,
  'position': 3,
  'description': 'დადასტურებული დაბრუნების შემთხვევაში თანხა ბრუნდება იმავე გადახდის არხით, რომლითაც შეკვეთა '
                 'გადაიხადეთ. თანხის ანგარიშზე ასახვის დრო დამოკიდებულია ბანკზე ან საგადახდო პროვაიდერზე. დეტალური '
                 'პირობები აღწერილია „პროდუქტისა და თანხის დაბრუნების“ გვერდზე.',
  'content_name': 'payment_methods_sections',
  'content_type': 'payment_method_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'რა მონაცემებს ვამუშავებთ',
  'editor': '<p>FlexDrive-ის ვებგვერდზე პერსონალური მონაცემების დამუშავებაზე პასუხისმგებელია შპს FlexDrive, '
            'საიდენტიფიკაციო კოდი: 406559040. ეს მონაცემები განახლებულია FlexDrive-ის მოქმედი საკონტაქტო '
            'ინფორმაციით.</p>\n'
            '<p>მონაცემები მუშავდება მაშინ, როცა მომხმარებელი ქმნის ანგარიშს, შედის პროფილში, ამატებს პროდუქტს '
            'კალათაში ან სურვილების სიაში, აგზავნის შეკვეთას, იყენებს საკონტაქტო ფორმას ან გვიკავშირდება '
            'მხარდაჭერისთვის.</p>\n'
            '<ul>\n'
            '  <li>ანგარიში და პროფილი: სახელი, გვარი, ელფოსტა, ტელეფონი, ქალაქი, მისამართი, პაროლი დაშიფრული '
            'ფორმით.</li>\n'
            '  <li>შეკვეთა: პროდუქტი, რაოდენობა, ფასი, გადახდის მეთოდი, მიწოდების ინფორმაცია, შეკვეთის სტატუსი და '
            'კომენტარი.</li>\n'
            '  <li>საკონტაქტო ფორმა: სახელი, ტელეფონი, ელფოსტა, თემა, შეკვეთის ნომერი და შეტყობინების ტექსტი.</li>\n'
            '  <li>ტექნიკური მონაცემები: IP მისამართი, ბრაუზერი, მოწყობილობა, სესიის მონაცემები, უსაფრთხოების '
            'ჩანაწერები და ქუქები.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 1,
  'description': 'ვაგროვებთ იმ ინფორმაციას, რომელიც საჭიროა ანგარიშის, კალათის, შეკვეთის, მიწოდების, მხარდაჭერისა და '
                 'უსაფრთხოებისთვის.',
  'content_name': 'privacy_policy_sections',
  'content_type': 'policy_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'რისთვის ვიყენებთ მონაცემებს',
  'editor': '<p>მონაცემებს ვიყენებთ იმ მიზნით, რომ საიტზე არსებული ძირითადი ecommerce ფუნქციები სწორად მუშაობდეს: '
            'ანგარიში, კალათა, სურვილების სია, checkout, შეკვეთების ისტორია, მიწოდება, გადახდა, დაბრუნება და '
            'მომხმარებლის მხარდაჭერა.</p>\n'
            '<p>ასევე ვიყენებთ ტექნიკურ და ანალიტიკურ მონაცემებს საიტის სტაბილურობის, უსაფრთხოების, შეცდომების პოვნისა '
            'და პროდუქტის გამოცდილების გასაუმჯობესებლად. პირდაპირი მარკეტინგი, სარეკლამო აუდიტორიები ან remarketing '
            'გამოიყენება მხოლოდ შესაბამისი სამართლებრივი საფუძვლით, მათ შორის თანხმობით, როცა ასეთი თანხმობა '
            'საჭიროა.</p>\n'
            '<ul>\n'
            '  <li>ანგარიშის შექმნა, ავტორიზაცია, აქტივაცია და პაროლის აღდგენა.</li>\n'
            '  <li>შეკვეთის მიღება, დადასტურება, მიწოდება, გაუქმება, დაბრუნება და refund.</li>\n'
            '  <li>გადახდის სტატუსის გადამოწმება ბანკთან ან საგადახდო პროვაიდერთან.</li>\n'
            '  <li>თაღლითობის, სპამის, ბოტების და არაავტორიზებული წვდომის შემცირება.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 2,
  'description': 'მონაცემები გვჭირდება შეკვეთის დასამუშავებლად, მომხმარებელთან დასაკავშირებლად, გადახდისა და '
                 'დაბრუნების პროცესისთვის, უსაფრთხოებისთვის და სერვისის გასაუმჯობესებლად.',
  'content_name': 'privacy_policy_sections',
  'content_type': 'policy_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'ქუქები, ანალიტიკა და მარკეტინგი',
  'editor': '<p>აუცილებელი ქუქები და მსგავსი ტექნოლოგიები საჭიროა საიტის ფუნქციონირებისთვის: ავტორიზაციის სესია, CSRF '
            'დაცვა, კალათა, სურვილების სია, სწრაფი ყიდვის სესია და არჩეული ვიზუალური თემა. ასეთი ქუქების გარეშე საიტის '
            'ძირითადი ფუნქციები სრულად ვერ იმუშავებს.</p>\n'
            '<p>ანალიტიკისა და მარკეტინგის მიზნით შეიძლება გამოყენებული იყოს Google Analytics, Google Tag Manager, '
            'Google Ads, Meta Pixel ან მსგავსი ხელსაწყოები. მათი მიზანია ვიზიტების გაზომვა, რეკლამის ეფექტიანობის '
            'შეფასება, აუდიტორიების შექმნა და საიტის გაუმჯობესება.</p>\n'
            '<ul>\n'
            '  <li>აუცილებელი ქუქები გამოიყენება უსაფრთხოების, სესიისა და ecommerce ფუნქციებისთვის.</li>\n'
            '  <li>ანალიტიკური ქუქები გვეხმარება გავიგოთ როგორ გამოიყენება საიტი და სად არის გასაუმჯობესებელი '
            'ნაწილი.</li>\n'
            '  <li>მარკეტინგული ქუქები შეიძლება გამოყენებულ იქნეს რეკლამისა და remarketing კამპანიებისთვის.</li>\n'
            '  <li>არასავალდებულო ქუქების მართვა შესაძლებელია cookie banner-ით ან ბრაუზერის პარამეტრებიდან.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 3,
  'description': 'საიტი იყენებს აუცილებელ ქუქებს მუშაობისთვის, ხოლო ანალიტიკისა და მარკეტინგის ხელსაწყოები გამოიყენება '
                 'საიტის გაუმჯობესებისა და რეკლამის გასაზომად.',
  'content_name': 'privacy_policy_sections',
  'content_type': 'policy_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'ვის შეიძლება გადაეცეს ინფორმაცია',
  'editor': '<p>FlexDrive არ ყიდის მომხმარებლის პერსონალურ მონაცემებს. მონაცემები შეიძლება გადაეცეს მხოლოდ იმ '
            'მომსახურების მომწოდებლებსა და პარტნიორებს, რომლებიც საჭიროა კონკრეტული პროცესის შესასრულებლად.</p>\n'
            '<ul>\n'
            '  <li>ჰოსტინგის, ინფრასტრუქტურის, მონაცემთა ბაზისა და ელფოსტის/SMS სერვისის მომწოდებლებს.</li>\n'
            '  <li>Google reCAPTCHA-ს და სხვა უსაფრთხოების ხელსაწყოებს, ბოტებისა და სპამის შესამცირებლად.</li>\n'
            '  <li>Google-ის, Meta-ს ან სხვა ანალიტიკისა და რეკლამის პლატფორმებს, თუ შესაბამისი ხელსაწყო '
            'აქტიურია.</li>\n'
            '  <li>ბანკებს, საგადახდო პროვაიდერებს და განვადების/ნაწილ-ნაწილ გადახდის პარტნიორებს.</li>\n'
            '  <li>კურიერს ან მიწოდებაში ჩართულ პარტნიორს, მხოლოდ შეკვეთის ჩასაბარებლად საჭირო მოცულობით.</li>\n'
            '  <li>უფლებამოსილ სახელმწიფო ორგანოს, თუ მონაცემის გადაცემა კანონით არის მოთხოვნილი.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 4,
  'description': 'მონაცემები შეიძლება გადაეცეს მხოლოდ იმ პარტნიორებს, რომლებიც საჭიროა საიტის, შეკვეთის, გადახდის, '
                 'მიწოდების, ანალიტიკის ან უსაფრთხოების პროცესისთვის.',
  'content_name': 'privacy_policy_sections',
  'content_type': 'policy_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'შენახვა, უსაფრთხოება და უფლებები',
  'editor': '<p>მონაცემებს ვინახავთ იმდენ ხანს, რამდენიც საჭიროა ანგარიშის, შეკვეთის, მიწოდების, გადახდის, დაბრუნების, '
            'მხარდაჭერის, უსაფრთხოების ან კანონით გათვალისწინებული მოთხოვნების შესასრულებლად. როცა მონაცემი აღარ არის '
            'საჭირო, ის იშლება, ანონიმიზდება ან ინახება მხოლოდ იმ მოცულობით, რაც კანონით ან ლეგიტიმური ინტერესით არის '
            'გამართლებული.</p>\n'
            '<p>მონაცემების დასაცავად ვიყენებთ დაშიფრულ კავშირებს, უსაფრთხო ქუქებს, წვდომის შეზღუდვას, reCAPTCHA-ს, '
            'ადმინისტრაციულ კონტროლს და სხვა გონივრულ ტექნიკურ/ორგანიზაციულ ზომებს.</p>\n'
            '<ul>\n'
            '  <li>შეგიძლიათ მოითხოვოთ თქვენს შესახებ არსებული მონაცემების ნახვა ან ასლი.</li>\n'
            '  <li>შეგიძლიათ მოითხოვოთ არაზუსტი მონაცემის გასწორება ან განახლება.</li>\n'
            '  <li>შეგიძლიათ მოითხოვოთ მონაცემების წაშლა ან დამუშავების შეზღუდვა, თუ ამის სამართლებრივი საფუძველი '
            'არსებობს.</li>\n'
            '</ul>\n'
            '<p>კონფიდენციალურობასთან დაკავშირებულ საკითხებზე მოგვწერეთ: <a '
            'href="mailto:info@flexdrive.ge">info@flexdrive.ge</a>. ზოგადი მხარდაჭერისთვის გამოიყენეთ <a '
            'href="mailto:support@flexdrive.ge">support@flexdrive.ge</a>.</p>',
  'icon_svg': None,
  'position': 5,
  'description': 'მონაცემებს ვინახავთ საჭირო ვადით და ვიყენებთ გონივრულ უსაფრთხოების ზომებს. მომხმარებელს შეუძლია '
                 'მოითხოვოს მონაცემების ნახვა, შეცვლა ან წაშლა.',
  'content_name': 'privacy_policy_sections',
  'content_type': 'policy_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'დაბრუნების მოთხოვნის გაგზავნა',
  'editor': '<p>დაბრუნების მოთხოვნა უნდა გამოიგზავნოს ელფოსტაზე <a '
            'href="mailto:return@flexdrive.ge">return@flexdrive.ge</a>. წერილში მიუთითეთ შეკვეთის ნომერი, სახელი, '
            'საკონტაქტო ტელეფონი, დასაბრუნებელი პროდუქტი და მოკლე მიზეზი, რის გამოც ითხოვთ დაბრუნებას.</p>\n'
            '<p>მოთხოვნის მიღება ავტომატურად არ ნიშნავს დაბრუნების დადასტურებას. FlexDrive ამოწმებს შეკვეთის '
            'მონაცემებს, ვადებს, პროდუქტის მდგომარეობას და იმას, შეესაბამება თუ არა მოთხოვნა დაბრუნების პირობებს.</p>\n'
            '<ul>\n'
            '  <li>შეკვეთის ნომერი და სწორი საკონტაქტო მონაცემები ამცირებს განხილვის დროს.</li>\n'
            '  <li>თუ მოთხოვნა ეხება დაზიანებას, დეფექტს ან არასწორ პროდუქტს, წერილს დაურთეთ ფოტო ან ვიდეო.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 1,
  'description': 'დაბრუნების პროცესი იწყება წერილობითი მოთხოვნით. მოთხოვნა განიხილება შეკვეთის, პროდუქტის '
                 'მდგომარეობისა და დაბრუნების საფუძვლის გადამოწმების შემდეგ.',
  'content_name': 'returns_sections',
  'content_type': 'returns_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'ჩვეულებრივი დაბრუნების ვადა',
  'editor': '<p>ონლაინ შეძენილ პროდუქტზე მომხმარებელს შეუძლია დაბრუნების მოთხოვნის გამოგზავნა პროდუქტის ჩაბარებიდან 14 '
            'კალენდარული დღის განმავლობაში, თუ დაბრუნება არ ექვემდებარება კანონით ან ამ გვერდზე აღწერილ '
            'გამონაკლისს.</p>\n'
            '<p>ვადის დაცვას ამოწმებს FlexDrive შეკვეთისა და მიწოდების მონაცემების მიხედვით. თუ მოთხოვნა ვადის გასვლის '
            'შემდეგ გაიგზავნა, ჩვეულებრივი დაბრუნება შეიძლება არ დადასტურდეს.</p>\n'
            '<ul>\n'
            '  <li>14-დღიანი ვადა ითვლება მომხმარებლის ან მის მიერ განსაზღვრული მიმღების მიერ ნივთის '
            'ჩაბარებიდან.</li>\n'
            '  <li>დაბრუნების შესახებ შეტყობინება ამ ვადის ამოწურვამდე უნდა გამოგვიგზავნოთ.</li>\n'
            '  <li>თუ მიღებული ნივთი დაზიანებულია ან შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა, შემთხვევა ცალკე '
            'განიხილება და ჩვეულებრივი დაბრუნების წესებით არ შემოიფარგლება.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 2,
  'description': 'დისტანციურ შეკვეთაზე დაბრუნების მოთხოვნა მიიღება პროდუქტის ჩაბარებიდან 14 კალენდარული დღის '
                 'განმავლობაში, კანონით გათვალისწინებული პირობებისა და გამონაკლისების დაცვით.',
  'content_name': 'returns_sections',
  'content_type': 'returns_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'პროდუქტის მდგომარეობა',
  'editor': '<p>ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა დაბრუნდეს ისეთ მდგომარეობაში, რომ შესაძლებელი იყოს მისი '
            'შემოწმება და დაბრუნების საფუძვლის შეფასება. ნივთი არ უნდა იყოს დაზიანებული მომხმარებლის მხრიდან და '
            'აუცილებლად უნდა ახლდეს ყველა ის ნაწილი, შეფუთვა, სამაგრი, აქსესუარი ან დოკუმენტი, რაც შეკვეთისას მიიღო '
            'მომხმარებელმა.</p>\n'
            '<p>თუ ავტონაწილი დამონტაჟდა, გამოყენებულია, აქვს ექსპლუატაციის კვალი, დაზიანება ან აკლია კომპლექტაცია, '
            'დაბრუნების მოთხოვნა ინდივიდუალურად შეფასდება. ასეთ შემთხვევაში FlexDrive მომხმარებელს აცნობებს, '
            'შესაძლებელია თუ არა ჩვეულებრივი დაბრუნება და რა პირობებით.</p>\n'
            '<ul>\n'
            '  <li>პროდუქტის შემოწმება არ უნდა გასცდეს იმ ფარგლებს, რაც საჭიროა მისი მდგომარეობისა და თავსებადობის '
            'დასადგენად.</li>\n'
            '  <li>მცირე ნაწილები, სამაგრები და შეფუთვა შეინახეთ, სანამ საბოლოოდ გადაწყვეტთ პროდუქტის დატოვებას.</li>\n'
            '  <li>თუ პროდუქტი უკვე დამონტაჟდა მანქანაზე, დაბრუნების მოთხოვნაში ეს ინფორმაცია უნდა მიუთითოთ.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 3,
  'description': 'ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა იყოს შემოწმებადი, დაუზიანებელი და სრულ კომპლექტაციაში. '
                 'დამონტაჟებული ან გამოყენებული ავტონაწილი ინდივიდუალურად ფასდება.',
  'content_name': 'returns_sections',
  'content_type': 'returns_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'დაზიანებული ან შეკვეთასთან შეუსაბამო პროდუქტი',
  'editor': '<p>თუ მიიღეთ დაზიანებული, დეფექტიანი ან შეკვეთასთან შეუსაბამო პროდუქტი, დაგვიკავშირდით რაც შეიძლება მალე. '
            'ასეთ შემთხვევაში წერილში მიუთითეთ შეკვეთის ნომერი, აღწერეთ პრობლემა და დაურთეთ ფოტო ან ვიდეო, სადაც '
            'საკითხი მკაფიოდ ჩანს.</p>\n'
            '<p>გადამოწმების შემდეგ FlexDrive მომხმარებელს შესთავაზებს შესაბამის გადაწყვეტილებას კონკრეტული შემთხვევის '
            'მიხედვით: პროდუქტის შეცვლას ან ალტერნატიული პროდუქტის მიწოდებას. თუ პრობლემა გამოწვეულია ჩვენი შეცდომით, '
            'შეცვლასთან დაკავშირებულ საჭირო პირდაპირ ხარჯს FlexDrive ფარავს.</p>\n'
            '<ul>\n'
            '  <li>თუ პროდუქტი არასწორი ან დეფექტიანია, დაგვიკავშირდით მის დამონტაჟებამდე ან შეკეთებამდე.</li>\n'
            '  <li>თუ დაზიანება მიწოდებისას ჩანს, გადაიღეთ ფოტო და რაც შეიძლება მალე მოგვწერეთ.</li>\n'
            '  <li>ფოტო/ვიდეო და მოკლე აღწერა დაგვეხმარება მდგომარეობის შეფასებაში და იმის დადგენაში, შესაძლებელია თუ '
            'არა პროდუქტის შეცვლა.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 4,
  'description': 'თუ პროდუქტი დაზიანებულია, დეფექტიანია ან შეკვეთას არ შეესაბამება, მოთხოვნა განიხილება პრიორიტეტულად '
                 'და საჭიროებს პრობლემის აღწერას ან ვიზუალურ მასალას.',
  'content_name': 'returns_sections',
  'content_type': 'returns_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'დაბრუნების ხარჯი',
  'editor': '<p>თუ დაბრუნება ხდება ჩვეულებრივი წესით და პროდუქტი არ არის დეფექტიანი ან არასწორად მიწოდებული, პროდუქტის '
            'უკან გამოგზავნის პირდაპირი ხარჯი ეკისრება მომხმარებელს. დაბრუნების არხი და მისამართი წინასწარ უნდა '
            'შეთანხმდეს FlexDrive-თან.</p>\n'
            '<p>თუ დადასტურდა, რომ მომხმარებელმა მიიღო არასწორი, დაზიანებული ან შეკვეთასთან შეუსაბამო პროდუქტი და '
            'მიზეზი FlexDrive-ის მხარესაა, შესაბამის დაბრუნების ხარჯს FlexDrive ფარავს ან მომხმარებელს აძლევს ცალკე '
            'ინსტრუქციას, როგორ მოხდეს პროდუქტის დაბრუნება.</p>\n'
            '<ul>\n'
            '  <li>დაბრუნების ხარჯი ანაზღაურდება მხოლოდ მაშინ, თუ ეს წინასწარ დადასტურდა და მიზეზი FlexDrive-ის '
            'მხარესაა.</li>\n'
            '  <li>გაგზავნამდე მომხმარებელმა უნდა მიიღოს დასაბრუნებელი მისამართი და ინსტრუქცია.</li>\n'
            '  <li>დაბრუნებისას პროდუქტი უნდა შეფუთოთ ისე, რომ ტრანსპორტირებისას დამატებით არ დაზიანდეს.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 5,
  'description': 'ჩვეულებრივი დაბრუნებისას პროდუქტის უკან გამოგზავნის პირდაპირი ხარჯი მომხმარებელზეა, ხოლო ჩვენი '
                 'შეცდომის ან დეფექტის დადასტურებისას ხარჯს FlexDrive ფარავს.',
  'content_name': 'returns_sections',
  'content_type': 'returns_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'თანხის დაბრუნება',
  'editor': '<p>თანხის დაბრუნება მუშავდება მას შემდეგ, რაც დაბრუნების მოთხოვნა დადასტურდება და FlexDrive მიიღებს '
            'დაბრუნებულ პროდუქტს ან მომხმარებლისგან მიიღებს პროდუქტის გამოგზავნის დამადასტურებელ ინფორმაციას, თუ '
            'კონკრეტულ შემთხვევაში სხვა რამ არ არის შეთანხმებული.</p>\n'
            '<p>დადასტურებული დაბრუნების შემთხვევაში თანხა ბრუნდება იმავე გადახდის არხით, რომლითაც შეკვეთა გადაიხადა '
            'მომხმარებელმა, თუ სხვა მეთოდი წინასწარ არ შეთანხმდა და მომხმარებელს დამატებითი ხარჯი არ წარმოეშობა. '
            'ონლაინ გადახდისას თანხის ანგარიშზე ასახვის დრო შეიძლება დამოკიდებული იყოს ბანკზე ან საგადახდო '
            'პროვაიდერზე.</p>\n'
            '<ul>\n'
            '<li>დაბრუნებასთან დაკავშირებული შეკითხვებისთვის გამოიყენეთ <a '
            'href="mailto:return@flexdrive.ge">return@flexdrive.ge</a>.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 6,
  'description': 'თანხის დაბრუნება მუშავდება დაბრუნების დადასტურების, პროდუქტის მიღების ან გაგზავნის დამადასტურებელი '
                 'ინფორმაციის გადამოწმების შემდეგ.',
  'content_name': 'returns_sections',
  'content_type': 'returns_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'მოვაჭრის მონაცემები და პირობების მოქმედება',
  'editor': '<p>FlexDrive არის ავტონაწილების ონლაინ მაღაზია, სადაც მომხმარებელს შეუძლია შეარჩიოს, შეუკვეთოს და '
            'შეიძინოს ტაივანური წარმოების ავტონაწილები. საიტის გამოყენებით, ანგარიშის შექმნით ან შეკვეთის გაგზავნით '
            'მომხმარებელი ადასტურებს, რომ გაეცნო ამ წესებსა და პირობებს და ეთანხმება მათ იმ ნაწილში, რომელიც კონკრეტულ '
            'მოქმედებას ეხება.</p>\n'
            '<p>მოვაჭრის ძირითადი იურიდიული და საკონტაქტო მონაცემები მოცემულია ქვემოთ.</p>\n'
            '<ul>\n'
            '  <li>მოვაჭრე: შპს FlexDrive</li>\n'
            '  <li>საიდენტიფიკაციო კოდი: 406559040</li>\n'
            '  <li>იურიდიული მისამართი: თბილისი, საქართველო</li>\n'
            '  <li>მხარდაჭერა: <a href="mailto:support@flexdrive.ge">support@flexdrive.ge</a></li>\n'
            '  <li>დაბრუნების მოთხოვნები: <a href="mailto:return@flexdrive.ge">return@flexdrive.ge</a></li>\n'
            '  <li>ტელეფონი: <a href="tel:+995557106104">+995 557 10 61 04</a></li>\n'
            '</ul>\n'
            '<p>თუ კონკრეტულ შეკვეთაზე, ინვოისზე ან წერილობით შეთანხმებაზე სხვა სპეციალური პირობაა მითითებული, ასეთი '
            'პირობა მოქმედებს მხოლოდ შესაბამისი შეკვეთის ფარგლებში და არ აუქმებს მომხმარებლის კანონით მინიჭებულ '
            'უფლებებს.</p>',
  'icon_svg': None,
  'position': 1,
  'description': 'ეს პირობები ვრცელდება FlexDrive-ის ვებსაიტის გამოყენებაზე, ონლაინ შეკვეთებზე და იმ მომსახურებებზე, '
                 'რომლებიც მომხმარებელს საიტის საშუალებით მიეწოდება.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'საიტის გამოყენება, ანგარიში და სტუმრის შეკვეთა',
  'editor': '<p>FlexDrive-ზე პროდუქტის დათვალიერება და შეკვეთის გაგზავნა შესაძლებელია რეგისტრაციის გარეშეც. '
            'რეგისტრირებული ანგარიში მომხმარებელს აძლევს დამატებით კომფორტს: შეკვეთების ისტორიის ნახვას, მიმდინარე '
            'სტატუსებზე თვალყურის დევნებას, სურვილების სიის მართვას და მომავალ შეკვეთებში მონაცემების უფრო სწრაფად '
            'შევსებას.</p>\n'
            '<p>მომხმარებელი ვალდებულია ანგარიშის შექმნისას და შეკვეთის გაფორმებისას მიუთითოს სწორი, სრული და '
            'აქტუალური ინფორმაცია. არასწორმა ტელეფონმა, ელფოსტამ, მისამართმა ან მანქანის მონაცემებმა შეიძლება '
            'გამოიწვიოს შეკვეთის დამუშავების, მიწოდების ან თავსებადობის დადასტურების შეფერხება.</p>\n'
            '<ul>\n'
            '  <li>მომხმარებელმა არ უნდა გადასცეს თავისი ანგარიშის მონაცემები მესამე პირს; FlexDrive კი იყენებს '
            'გონივრულ ტექნიკურ და ორგანიზაციულ ზომებს ანგარიშებისა და მონაცემების დასაცავად.</li>\n'
            '  <li>აკრძალულია ყალბი მონაცემებით შეკვეთა, სხვა პირის ანგარიშის გამოყენება ან საიტის მუშაობის '
            'ხელშეშლა.</li>\n'
            '  <li>სტუმრის რეჟიმში გაფორმებულ შეკვეთაზე მხარდაჭერის მისაღებად შეიძლება საჭირო გახდეს შეკვეთის ნომრის, '
            'ტელეფონის ან ელფოსტის მითითება.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 2,
  'description': 'შეკვეთა შესაძლებელია როგორც სტუმრის რეჟიმში, ისე რეგისტრირებული ანგარიშით. ანგარიში ამარტივებს '
                 'შეკვეთების ისტორიის, სტატუსებისა და შენახული პროდუქტების მართვას.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'პროდუქტის ინფორმაცია და თავსებადობა',
  'editor': '<p>FlexDrive-ზე წარმოდგენილი პროდუქტები არის ტაივანური წარმოების ავტონაწილები. პროდუქტის გვერდზე შეიძლება '
            'მითითებული იყოს კატეგორია, ბრენდი, SKU, მწარმოებლის კოდი, ფასი, მარაგი, მხარე, განთავსება, ფოტოები, მოკლე '
            'აღწერა, ტექნიკური მახასიათებლები და მანქანასთან თავსებადობის მონაცემები.</p>\n'
            '<p>თავსებადობის ინფორმაცია, მათ შორის მარკა, მოდელი, წელი, ძრავი, OEM/ნაწილის კოდი ან სხვა ტექნიკური '
            'მინიშნება, მომხმარებელს ეხმარება სწორი ნაწილის შერჩევაში. ავტონაწილების შემთხვევაში ერთი და იგივე მოდელის '
            'სხვადასხვა წელი, ძრავი, კომპლექტაცია ან ბაზრის ვერსია შეიძლება განსხვავებულ ნაწილს მოითხოვდეს, ამიტომ '
            'შეკვეთამდე მომხმარებელმა უნდა გადაამოწმოს პროდუქტის შესაბამისობა თავისი ავტომობილის რეალურ '
            'მონაცემებთან.</p>\n'
            '<ul>\n'
            '  <li>თუ მომხმარებელს თავსებადობაში ეჭვი აქვს, შეკვეთამდე შეუძლია მოგვწეროს და მოგვაწოდოს მანქანის '
            'მონაცემები ან არსებული ნაწილის კოდი.</li>\n'
            '  <li>თუ მომხმარებელმა არასწორი ან არასრული მონაცემები მოგვაწოდა, შესაბამისობის შეცდომაზე პასუხისმგებლობა '
            'შეიძლება მომხმარებლის მხარეს გადავიდეს.</li>\n'
            '  <li>თუ პროდუქტი არ შეესაბამება ჩვენს მიერ დადასტურებულ ინფორმაციას, საკითხი განიხილება არასწორი ან '
            'შეუსაბამო პროდუქტის წესით.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 3,
  'description': 'FlexDrive ყიდის ტაივანურ ავტონაწილებს. პროდუქტის თავსებადობის მონაცემები ეხმარება არჩევაში, თუმცა '
                 'საბოლოო შესაბამისობა უნდა გადამოწმდეს მანქანის რეალური მონაცემებით.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'ფასი, მარაგი და ტექნიკური შეცდომები',
  'editor': '<p>საიტზე ფასები მითითებულია ლარში, თუ კონკრეტულ გვერდზე სხვა რამ არ არის აღნიშნული. პროდუქტის საბოლოო '
            'ღირებულება, ხელმისაწვდომი გადახდის მეთოდი და შესაძლო მიწოდების ხარჯი მომხმარებელს უნდა გამოუჩნდეს '
            'შეკვეთის გაფორმებამდე, checkout-ის პროცესში.</p>\n'
            '<p>მარაგი, ფასი, ფასდაკლება და პროდუქტის მონაცემები შეიძლება განახლდეს. თუ დაფიქსირდა აშკარა ტექნიკური '
            'შეცდომა, მაგალითად არარეალურად დაბალი ფასი, არასწორი მარაგი ან პროდუქტის აღწერის არსებითი უზუსტობა, '
            'FlexDrive უფლებას იტოვებს შეკვეთის საბოლოო დადასტურებამდე დაუკავშირდეს მომხმარებელს ინფორმაციის '
            'დასაზუსტებლად.</p>\n'
            '<ul>\n'
            '  <li>შეკვეთაზე მოქმედებს ის ფასი და პირობები, რომლებიც მომხმარებელმა შეკვეთის გაგზავნამდე checkout-ში '
            'ნახა, გარდა აშკარა ტექნიკური შეცდომისა.</li>\n'
            '  <li>თუ შეკვეთის შესრულება მარაგის ან ტექნიკური მიზეზით შეუძლებელია, მომხმარებელს გონივრულ ვადაში '
            'ეცნობება.</li>\n'
            '  <li>ფასდაკლება ან აქცია მოქმედებს მხოლოდ იმ ვადით და პირობებით, რომლებიც შესაბამის პროდუქტზე ან '
            'შეთავაზებაზეა მითითებული.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 4,
  'description': 'პროდუქტის მოქმედი ფასი და ხელმისაწვდომობა ჩანს პროდუქტის გვერდზე და checkout-ში. აშკარა ტექნიკური '
                 'შეცდომის შემთხვევაში შეკვეთა შეიძლება დადასტურებამდე დაზუსტდეს.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'შეკვეთის განთავსება და დადასტურება',
  'editor': '<p>შეკვეთის გაგზავნამდე მომხმარებელს აქვს შესაძლებლობა გადაამოწმოს კალათაში დამატებული პროდუქტები, '
            'რაოდენობა, ფასი, საკონტაქტო ინფორმაცია, მიწოდების მისამართი, შენიშვნა და არჩეული გადახდის მეთოდი. '
            'შეკვეთის გაგზავნის შემდეგ სისტემა აფიქსირებს შეკვეთის მოთხოვნას და მომხმარებელს უჩვენებს ან უგზავნის '
            'დადასტურების ინფორმაციას.</p>\n'
            '<p>შეკვეთის მოთხოვნის მიღება არ ნიშნავს, რომ შეკვეთა ყველა შემთხვევაში უკვე საბოლოოდ შესრულებადია. '
            'შეკვეთა შეიძლება გადამოწმდეს მარაგის, გადახდის მეთოდის, მიწოდების შესაძლებლობის, საკონტაქტო ინფორმაციისა '
            'და პროდუქტის თავსებადობის კუთხით, თუ ასეთი გადამოწმება საჭიროა.</p>\n'
            '<ul>\n'
            '  <li>შეკვეთის სტატუსი შეიძლება იყოს: მიღებული, დადასტურებული, მუშავდება, გაგზავნილია, ჩაბარებულია ან '
            'გაუქმებულია.</li>\n'
            '  <li>რეგისტრირებული მომხმარებელი შეკვეთების ისტორიასა და სტატუსებს ხედავს საკუთარ პროფილში.</li>\n'
            '  <li>თუ შეკვეთის მნიშვნელოვანი დეტალი შესაცვლელია, მომხმარებელი უნდა დაგვიკავშირდეს რაც შეიძლება '
            'სწრაფად, სანამ შეკვეთა დამუშავების ან გაგზავნის ეტაპზე გადავა.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 5,
  'description': 'შეკვეთის გაგზავნამდე მომხმარებელს შეუძლია შეამოწმოს და შეცვალოს კალათა, რაოდენობა, საკონტაქტო '
                 'მონაცემები, მისამართი და გადახდის მეთოდი.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'გადახდის პირობები',
  'editor': '<p>FlexDrive-ზე შეკვეთის გადახდა შესაძლებელია მხოლოდ საბანკო ბარათით, ონლაინ.</p>\n'
            '<p>გადახდის დასასრულებლად მიჰყევით შეკვეთის გაფორმებისას ნაჩვენებ ინსტრუქციებს. თუ გადახდა ვერ '
            'დადასტურდა, გადაამოწმეთ მისი სტატუსი ან დაგვიკავშირდით.</p>\n'
            '<p>თანხის დაბრუნების პირობები აღწერილია <a href="/returns">„პროდუქტისა და თანხის დაბრუნების“</a> '
            'გვერდზე.</p>',
  'icon_svg': None,
  'position': 6,
  'description': 'FlexDrive-ზე შეკვეთის გადახდა შესაძლებელია მხოლოდ საბანკო ბარათით, ონლაინ.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'მიწოდების მოკლე პირობები',
  'editor': '<p>FlexDrive შეკვეთებს აწვდის მომხმარებლის მიერ მითითებულ მისამართზე ან იმ სხვა წესით, რომელიც შეკვეთის '
            'პროცესში იქნება შეთავაზებული. თბილისში მიწოდების დღე განისაზღვრება შეკვეთის გაფორმების დროის მიხედვით, '
            'ხოლო რეგიონებში მიწოდების ვადა ითვლება შეკვეთის დადასტურებიდან.</p>\n'
            '<ul>\n'
            '  <li>თბილისში: ორშაბათიდან შაბათის ჩათვლით, 14:00 საათამდე გაფორმებულ შეკვეთას იმავე დღეს მოგაწვდით, '
            'ხოლო 14:00 საათიდან გაფორმებულ შეკვეთას — მომდევნო დღეს. კვირას მიწოდება არ ხორციელდება — შაბათს 14:00 '
            'საათიდან და კვირას გაფორმებულ შეკვეთებს ორშაბათს მოგაწვდით.</li>\n'
            '  <li>რეგიონებში მიწოდების საორიენტაციო ვადაა 4-5 სამუშაო დღე შეკვეთის დადასტურებიდან.</li>\n'
            '  <li>მიწოდების ღირებულება, თუ ასეთი მოქმედებს, მომხმარებელს უნდა გამოუჩნდეს შეკვეთის დადასტურებამდე ან '
            'განისაზღვროს შესაბამისი მიწოდების გვერდის პირობებით.</li>\n'
            '</ul>\n'
            '<p>ვადაზე შეიძლება გავლენა იქონიოს მისამართის დაზუსტებამ, მარაგის მდგომარეობამ, კურიერის დატვირთვამ, '
            'ამინდმა ან სხვა ლოჯისტიკურმა გარემოებამ. დეტალური ინფორმაცია განთავსებულია <a href="/delivery">მიწოდების '
            'პირობების გვერდზე</a>.</p>',
  'icon_svg': None,
  'position': 7,
  'description': 'თბილისში 14:00 საათამდე გაფორმებული შეკვეთა იმავე დღეს მოგეწოდებათ, ხოლო 14:00 საათიდან — მომდევნო '
                 'დღეს, კვირის გარდა. შაბათს 14:00 საათიდან და კვირას გაფორმებული შეკვეთები ორშაბათს მოგეწოდებათ. '
                 'რეგიონებში — 4-5 სამუშაო დღე შეკვეთის დადასტურებიდან. დეტალური პირობები იხილეთ მიწოდების გვერდზე.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'გაუქმება, დაბრუნება და დამონტაჟებული ნაწილი',
  'editor': '<p>მომხმარებელს შეუძლია დისტანციურ შეკვეთაზე ხელშეკრულებაზე უარის თქმა და დაბრუნების მოთხოვნის გაგზავნა '
            'პროდუქტის მიღებიდან 14 კალენდარული დღის განმავლობაში, კანონით გათვალისწინებული გამონაკლისებისა და '
            'პირობების დაცვით. დაბრუნების პროცესი იწყება ელფოსტაზე მოთხოვნის გაგზავნით.</p>\n'
            '<p>ჩვეულებრივი დაბრუნებისას პროდუქტი უნდა იყოს ისეთ მდგომარეობაში, რომ შესაძლებელი იყოს მისი შემოწმება და '
            'დაბრუნების საფუძვლის შეფასება. თუ ავტონაწილი დამონტაჟდა ან გამოყენებულია იმაზე მეტად, ვიდრე მისი '
            'მდგომარეობისა და თავსებადობის შესამოწმებლად იყო საჭირო, დაბრუნების მოთხოვნა ინდივიდუალურად შეფასდება. თუ '
            'ნივთს აქვს მომხმარებლის მხრიდან დაზიანება, გამოყენების აშკარა კვალი ან აკლია კომპლექტაცია, FlexDrive '
            'მომხმარებელს აცნობებს, შესაძლებელია თუ არა ჩვეულებრივი დაბრუნება და რა პირობებით.</p>\n'
            '<p>დამონტაჟების ან გამოყენების ფაქტი არ აუქმებს მომხმარებლის უფლებებს, თუ მიღებული ნივთი დაზიანებულია, '
            'შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა ან არ შეესაბამება იმ არსებით ინფორმაციას, რომელიც '
            'შეკვეთამდე იყო დადასტურებული. ასეთ შემთხვევაში FlexDrive განიხილავს შეცვლას, შეკეთებას, ფასის შემცირებას '
            'ან თანხის დაბრუნებას კონკრეტული შემთხვევის მიხედვით.</p>\n'
            '<ul>\n'
            '  <li>დაბრუნების მოთხოვნა იგზავნება: <a href="mailto:return@flexdrive.ge">return@flexdrive.ge</a></li>\n'
            '  <li>წერილში სასურველია მიეთითოს შეკვეთის ნომერი, სახელი, ტელეფონი, დასაბრუნებელი პროდუქტი და '
            'მიზეზი.</li>\n'
            '  <li>თუ მიღებული ნივთი დაზიანებულია ან შეკვეთაში მითითებულ პროდუქტს/კოდს არ ემთხვევა, რეკომენდებულია '
            'ფოტოს ან ვიდეოს დართვა.</li>\n'
            '</ul>\n'
            '<p>დეტალური პროცესი, ხარჯები, ვადები და გამონაკლისები აღწერილია <a href="/returns">დაბრუნების '
            'გვერდზე</a>.</p>',
  'icon_svg': None,
  'position': 8,
  'description': 'დისტანციურ შეკვეთაზე მომხმარებელს აქვს კანონით გათვალისწინებული დაბრუნების უფლება. დამონტაჟებული ან '
                 'გამოყენებული ნაწილის შემთხვევა ფასდება ცალკე.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'იურიდიული პირები და B2B შეკვეთები',
  'editor': '<p>FlexDrive-ის მომსახურება გათვლილია როგორც ფიზიკურ პირებზე, ისე იურიდიულ პირებსა და სხვა კომერციულ '
            'მომხმარებლებზე. იურიდიული პირის სახელით შეკვეთის გაფორმებისას შეიძლება საჭირო გახდეს კომპანიის '
            'საიდენტიფიკაციო კოდის, დასახელების, საკონტაქტო პირის, მისამართისა და ანგარიშსწორებისთვის საჭირო სხვა '
            'მონაცემების მითითება.</p>\n'
            '<p>B2B შეკვეთებზე შეიძლება მოქმედებდეს ცალკე შეთავაზება, ინვოისი, გადახდის ვადა, მიწოდების პირობა ან '
            'წერილობითი შეთანხმება. ასეთ შემთხვევაში კონკრეტული შეკვეთისთვის უპირატესად მოქმედებს შესაბამისი '
            'კომერციული შეთანხმება, თუ ის არ ეწინააღმდეგება სავალდებულო კანონმდებლობას.</p>\n'
            '<ul>\n'
            '  <li>ფიზიკური პირის, როგორც მომხმარებლის, კანონით დაცული უფლებები არ იზღუდება ამ გვერდით.</li>\n'
            '  <li>B2B შეკვეთის დეტალები შეიძლება დაზუსტდეს შეკვეთის მიღების შემდეგ, თუ კომპანიასთან დაკავშირებული '
            'მონაცემები არასრულია.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 9,
  'description': 'FlexDrive მომავალში მოემსახურება როგორც ფიზიკურ პირებს, ისე კომპანიებს. B2B შეკვეთებზე შეიძლება '
                 'იმოქმედოს ცალკე შეთავაზებამ, ინვოისმა ან შეთანხმებამ.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None},
 {'slug': None,
  'title': 'კონფიდენციალურობა, უსაფრთხოება და ცვლილებები',
  'editor': '<p>FlexDrive მომხმარებლის პერსონალურ მონაცემებს ამუშავებს იმ მიზნით, რომ იმუშაოს ანგარიში, კალათა, '
            'შეკვეთა, მიწოდება, მხარდაჭერა, უსაფრთხოება და კანონით მოთხოვნილი პროცესები. მონაცემების დამუშავების '
            'დეტალური წესი მოცემულია <a href="/privacy-policy">კონფიდენციალურობის პოლიტიკაში</a>.</p>\n'
            '<p>საიტზე განთავსებული ტექსტები, დიზაინი, ლოგო, სტრუქტურა, ფოტოები და სხვა მასალა ეკუთვნის FlexDrive-ს ან '
            'გამოიყენება შესაბამისი უფლების საფუძველზე. მათი უნებართვოდ კომერციული გამოყენება, კოპირება ან გავრცელება '
            'დაუშვებელია, გარდა კანონით დაშვებული შემთხვევებისა.</p>\n'
            '<p>FlexDrive უფლებას იტოვებს განაახლოს წესები და პირობები ბიზნეს პროცესების, გადახდის მეთოდების, '
            'მიწოდების პრაქტიკის, დაბრუნების წესის, ტექნიკური ფუნქციების ან კანონმდებლობის ცვლილების შესაბამისად. '
            'მოქმედი ვერსია ყოველთვის გამოქვეყნდება ამ გვერდზე.</p>\n'
            '<ul>\n'
            '  <li>ზოგადი მხარდაჭერა: <a href="mailto:support@flexdrive.ge">support@flexdrive.ge</a></li>\n'
            '  <li>იურიდიული საკითხები: <a href="mailto:info@flexdrive.ge">info@flexdrive.ge</a></li>\n'
            '  <li>თუ მომხმარებელს აქვს შეკითხვა კონკრეტულ შეკვეთაზე, სასურველია მიუთითოს შეკვეთის ნომერი.</li>\n'
            '</ul>',
  'icon_svg': None,
  'position': 10,
  'description': 'პერსონალური მონაცემების დამუშავება აღწერილია კონფიდენციალურობის პოლიტიკაში. წესები შეიძლება '
                 'განახლდეს ბიზნეს პროცესების ან კანონმდებლობის ცვლილებისას.',
  'content_name': 'terms_sections',
  'content_type': 'terms_section',
  'single_page_slug': None}]


def sync_staging_cms_texts(apps, schema_editor):
    Page = apps.get_model("pages", "Page")
    ComponentType = apps.get_model("pages", "ComponentType")
    Content = apps.get_model("pages", "Content")
    ContentItem = apps.get_model("pages", "ContentItem")
    Component = apps.get_model("pages", "Component")

    # 1) Page text, SEO text, and navigation/footer structure.
    page_by_slug = {}
    for row in PAGES:
        slug = row["slug"]
        defaults = {
            "name": row.get("name"),
            "seo_title": row.get("seo_title"),
            "seo_description": row.get("seo_description"),
            "seo_noindex": row.get("seo_noindex", False),
            "seo_canonical_url": row.get("seo_canonical_url"),
            "show_in_menu": row.get("show_in_menu", True),
            "show_in_footer": row.get("show_in_footer", False),
            "footer_group": row.get("footer_group"),
            "footer_order": row.get("footer_order", 0),
            "footer_label": row.get("footer_label"),
            "order": row.get("order", 0),
            "url": row.get("url"),
        }
        page, _ = Page.objects.update_or_create(slug=slug, defaults=defaults)
        page_by_slug[slug] = page

    # 2) Components: sync only text/configuration fields.
    # Image fields are intentionally untouched.
    for row in COMPONENTS:
        page = page_by_slug[row["page_slug"]]
        component_type, _ = ComponentType.objects.get_or_create(name=row["component_type"])

        content = None
        if row.get("content_name"):
            content, _ = Content.objects.get_or_create(name=row["content_name"])

        component = (
            Component.objects
            .filter(page=page, component_type=component_type)
            .order_by("id")
            .first()
        )

        if component is None:
            component = Component(page=page, component_type=component_type)

        component.content = content
        component.position = row.get("position", 0)
        component.title = row.get("title")
        component.subtitle = row.get("subtitle")
        component.button_text = row.get("button_text")
        component.enabled = row.get("enabled", True)
        component.save()

    # 3) Content items: preserve media/image fields and icon_svg.
    # Match each item by (content, position), which is unique in this snapshot.
    for row in CONTENT_ITEMS:
        content, _ = Content.objects.get_or_create(name=row["content_name"])

        item = (
            ContentItem.objects
            .filter(content=content, position=row["position"])
            .order_by("id")
            .first()
        )
        if item is None:
            item = ContentItem(content=content, position=row["position"])

        item.title = row.get("title")
        item.description = row.get("description")
        item.editor = row.get("editor")
        item.slug = row.get("slug")
        item.content_type = row.get("content_type")

        single_page_slug = row.get("single_page_slug")
        item.singlePageRoute = page_by_slug.get(single_page_slug) if single_page_slug else None

        item.save()

    # 4) Staging has exactly 3 payment-method sections.
    # Remove only obsolete extra payment-method rows; do not touch other contents.
    payment_content = Content.objects.filter(name="payment_methods_sections").first()
    if payment_content:
        desired_positions = [
            row["position"]
            for row in CONTENT_ITEMS
            if row["content_name"] == "payment_methods_sections"
        ]
        ContentItem.objects.filter(content=payment_content).exclude(
            position__in=desired_positions
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0075_seed_about_us_page"),
    ]

    operations = [
        migrations.RunPython(sync_staging_cms_texts, migrations.RunPython.noop),
    ]
