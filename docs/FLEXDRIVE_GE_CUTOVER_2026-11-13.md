# flexdrive.ge — გადასვლის მიმდინარე გეგმა

განახლებულია 2026-11-14. ისტორიული სრული აუდიტი: `outputs/production-cutover-audit-20261102/FlexDrive_Production_Cutover_TODO_2026-11-02.md` (D01–D21).

## დადასტურებული მიმდინარე მდგომარეობა

- Namespace-ის აქტიური nameserver-ებია `ns1.namespace.life` და `ns2.namespace.life`.
- ვებგადართვა შესრულებულია. `flexdrive.ge`-ის A ჩანაწერებია `162.159.140.98` და `172.66.0.96`, TTL 300. `www.flexdrive.ge` CNAME მიუთითებს `flexdrive-prod-front-pdzcv.ondigitalocean.app`-ზე, TTL 300. ორივე ავტორიტეტული NS-ის ზუსტი შედარება შენახულია.
- MX არის `mail.flexdrive.ge`, priority 0. `mail.flexdrive.ge` A არის `136.243.25.146`, TTL 14400. SPF გახდა `v=spf1 +mx +ip4:136.243.25.146 ~all`. ოთხი CalDAV/CardDAV SRV სამიზნე გადავიდა იმავე პროვაიდერის `cp4.de.namespace.life`-ზე, მისამართი და TLS 2080 შემოწმებულია. DKIM/DMARC/Brevo/MX/mail და დანარჩენი 21 query ჯგუფი შენარჩუნებულია. მომხმარებელმა ვებგადართვამდე წერილების მიღება დაადასტურა, გადართვისშემდგომი საფოსტო ტესტი ჯერ დასადასტურებელია.
- Namespace-ის cPanel-ში ფოსტა არის `Local Mail Exchanger`-ზე. ელფოსტის SSL/TLS კლიენტის პარამეტრებში შემომავალი IMAP 993 და გამავალი SMTP 465 სერვერად მითითებულია `cp4.de.namespace.life`; მისი მიმდინარე A-ც `136.243.25.146`-ია. ეს **არ ადასტურებს**, რომ ის MX-ის რეკომენდებული მუდმივი სამიზნეა.
- Namespace-ის დროებით ჩართული სრული Zone Editor-ით ცვლილებები შენახულია. ორივე NS-ის before/after ასლები და ზუსტი შედარება ignored `tmp/measurements-20261015/domain-cutover-20261113/`-შია. წვდომის ისევ შეზღუდვის შეტყობინება მომხმარებელმა სატესტო შესვლისა და გადართვისშემდგომი ფოსტის შემოწმების შემდეგ უნდა გაგზავნოს.
- `flexdrive.ge` და `www.flexdrive.ge` მიბმულია DigitalOcean-ზე და ორივე IP-ზე მოქმედი HTTPS გადამოწმებულია. `www` GET პასუხი 308-ით ინარჩუნებს გზას და გადადის root-ზე. root და `/__preview` არის 200 private/no-store/noindex, პირდაპირი API კოდის გარეშე 403-ია. `public_open=False`. 2026-11-14 მომხმარებელმა დაადასტურა კოდის შექმნა და სრული საიტის წარმატებული სატესტო შესვლა. შედეგი `production-domain-live.json`-შია.
- frontend კომპონენტზე `NUXT_PUBLIC_SITE_URL=https://flexdrive.ge` შენახულია, მხოლოდ ერთი ველი შეიცვალა. backend app-level `FRONTEND_BASE_URL` გადავიდა root-ზე, `CORS_ALLOWED_ORIGINS` და `CSRF_TRUSTED_ORIGINS` შეიცავს ძველ starter-სა და ახალ root/www origins-ს. 37 app-level ცვლადიდან მხოლოდ ეს სამი შეიცვალა. ახალ origins-ზე CORS live პასუხი დადასტურებულია. ბანკის, OAuth-ისა და კურიერის საბოლოო runtime/account პარამეტრების სრული შემოწმება შემდგომი სამუშაოა.

## Backend API subdomain — 2026-11-14

მომხმარებელმა აირჩია და დაავალა ცალკე backend hostname. DigitalOcean backend app-ზე `api.flexdrive.ge` დამატებულია external DNS რეჟიმით და Active-ია. Namespace-ის ზონაში დაემატა მხოლოდ `api.flexdrive.ge CNAME flexdrive-prod-back-2eit9.ondigitalocean.app`, TTL 300. ორივე ავტორიტეტულ NS-ზე 29 არსებული query ჯგუფი უცვლელია SOA serial-ის გარდა; root/www/mail ჩანაწერები შენარჩუნებულია.

- ადმინისტრაცია: `https://api.flexdrive.ge/manager-fd/`. გამოიყენება იგივე მომხმარებელი/პაროლი; ახალ hostname-ზე ხელახალი შესვლაა საჭირო. Launch control: `https://api.flexdrive.ge/manager-fd/pages/launchcontrol/`.
- backend app-level `DJANGO_ALLOWED_HOSTS` და `CSRF_TRUSTED_ORIGINS` შეიცავს ახალ API hostname-საც, ძველი hostname/origins შენარჩუნებულია. `WINGO_WEBHOOK_PUBLIC_URL=https://api.flexdrive.ge/api/commerce/wingo/webhook/`.
- backend component-ის მხოლოდ `BOG_CALLBACK_PUBLIC_URL` შეიცვალა: `https://api.flexdrive.ge/api/commerce/payments/bog/callback/`. ბანკთან/კურიერთან მოთხოვნა არ გაგზავნილა; მათი სრული operational შემოწმება კვლავ დარჩენილია. ძველი backend hostname მოქმედებს უკვე შექმნილი callback-ებისთვისაც.
- frontend component-ის მხოლოდ `NUXT_INTERNAL_API_URL` შეიცვალა: `https://api.flexdrive.ge/api`. მომხმარებლის ბრაუზერი კვლავ storefront-ის same-origin `/api` გზას იყენებს.
- app-level 148, backend component 188 და frontend component 36 ფორმის ველი შედარდა შენახვამდე; მხოლოდ ზემოთ აღწერილი მნიშვნელობები შეიცვალა, scope/encryption შენარჩუნებულია. Source code/DB/migration ცვლილება არ არის, push საჭირო არ არის.
- API status 200/guard enabled/public closed, root 403 JSON, admin login/static 200 და ცარიელი login ფორმის რეალური CSRF POST 200 დადასტურებულია. API სერტიფიკატი ორივე ingress IP-ზე CA/hostname შემოწმებას გადის. Bare `api.flexdrive.ge` მაღაზიის გვერდი არ არის.
- ორივე runtime config deployment დასრულდა. frontend `a4d121ce-2f43-40ef-96cb-922775b9bfe5` არის Success/Live; backend `b96be326-851a-4708-845d-58beb6852a9c` healthy. ახალი frontend deployment-ის შემდეგ მომხმარებლის არსებული preview cookie-ით მთავარი გვერდი და რეალური პროდუქტების კატალოგი Computer Use-ით წარმატებით გაიხსნა. დახურული რეჟიმი შენარჩუნებულია.
- ასლები/ზუსტი ცვლილებები/live მტკიცებულება ignored `tmp/measurements-20261015/api-domain-20261114/`-შია. საჯარო გახსნა არ შესრულებულა.

## ბანკის env მისამართები — 2026-11-14

მომხმარებლის მითითებით მხოლოდ ბანკის env შემოწმდა და დომენთან დაკავშირებული ორი დარჩენილი ბმული გასწორდა: `BOG_FRONTEND_SUCCESS_URL=https://flexdrive.ge/checkout/payment/success` და `BOG_FRONTEND_FAIL_URL=https://flexdrive.ge/checkout/payment/fail`. `BOG_CALLBACK_PUBLIC_URL` უკვე სწორ API hostname-ზე იყო. App-level ბანკის ერთადერთი პარამეტრი reconciliation alert email-ია, `support@flexdrive.ge`; ცვლილება არ დასჭირდა. სხვა BOG მნიშვნელობები დომენზე დამოკიდებული არ არის და შენარჩუნებულია. 188 კომპონენტის ფორმის ველის ზუსტმა შედარებამ დაადასტურა მხოლოდ ეს ორი ცვლილება. ორივე frontend route კოდში არსებობს.

Deployment `9123394c-ce5a-4669-8c2f-841a424f907b` დასრულდა Success/Live, app Healthy. Source/DB/credential ცვლილება და ბანკის მოთხოვნა/გადახდა არ შესრულებულა; დამატებითი push/deploy საჭირო არ არის. მომხმარებელმა რეალური გადახდა შემდეგი დღისთვის გადადო და ამ ეტაპის შემდეგ გაჩერება მოითხოვა. ეს ადასტურებს env-ის განახლებას; რეალურ გადახდას/callback-სა და ბანკის merchant შეზღუდვებს არ ამოწმებს. მტკიცებულება ignored `tmp/measurements-20261015/api-domain-20261114/bank-env-urls.json`-შია.

## თავდაპირველი გეგმის მდგომარეობა — 2026-11-14

### Google-ისთვის საჯარო საინფორმაციო გვერდები — deployment და დომენის მფლობელობა დადასტურებულია

მომხმარებელმა დაავალა Google brand verification-ის მომზადება ისე, რომ მაღაზია დახურული დარჩეს. მომზადებულია ორი პროექტის source ცვლილება: მოლოდინის გვერდს დაემატა FlexDrive-ის აღწერა, საკონტაქტო ელფოსტა და legal ბმულები; `/privacy-policy` და `/terms` მხოლოდ GET/HEAD-ზე აჩვენებს არსებულ CMS ტექსტს კოდის გარეშე. Backend-ის ახალი `/api/launch/information/<slug>/` აბრუნებს მხოლოდ ამ ორი გვერდის ჩართული შესაბამისი კომპონენტებისა და legal ტიპის პუნქტების ტექსტს, არსებული HTML sanitization-ით. ზოგადი CMS/catalog/accounts API-ები კვლავ დახურულია. იურიდიული ტექსტი/ბაზა/env/public_open არ შეცვლილა. SEO noindex და private/no-store რჩება.

24 backend და 18 frontend რეგრესია, lint/typecheck/production build და აწყობილი Nitro-ს იზოლირებული HTTP smoke წარმატებულია. მომხმარებელმა ორივე deployment დაადასტურა; მიგრაცია არ სჭირდება. ანონიმურად live მთავარი გვერდი/Privacy Policy/Terms არის 200 და ორივე დოკუმენტი სრულ ტექსტს შეიცავს. კატალოგი ისევ მოლოდინის გვერდია, catalog API 403, `public_open=False`. private/no-store/noindex შენარჩუნებულია.

Google-ის ავტომატური Branding შემოწმება დაიწყო; ერთადერთი ნაჩვენები მიზეზია homepage-ის დაუდასტურებელი მფლობელობა. პანელი პირდაპირ მოითხოვს მფლობელობის დადასტურების შემდეგ 24 საათის ლოდინს და ხელახალ შემოწმებას. Search Console-ში შეიქმნა `flexdrive.ge` Domain property იმავე Google ანგარიშით; დადასტურდა Google-ის CNAME მეთოდით: `saz7zcmidlok.flexdrive.ge CNAME gv-op4ax32ama2c5k.dv.googlehosted.com`, TTL 14400. Search Console-მა აჩვენა **Ownership verified**. ეს ჩანაწერი არ წაიშალოს. TXT-ის შენახვა cPanel-ში ვერ დასრულდა და Google TXT DNS-ში არ დამატებულა; CNAME წარმატებულია. ორივე NS-ის 30 თავდაპირველი query ჯგუფი უცვლელია SOA serial-ის გარდა. მტკიცებულებები ignored `tmp/measurements-20261015/api-domain-20261114/public-information/`-შია.

შემდეგი ზუსტი ნაბიჯი: **2026-11-15, თბილისის 04:35-ის შემდეგ** Google Auth Platform → Branding → View issues → I have fixed the issues → Proceed. შემდეგ წავიკითხოთ რეალური შედეგი; საჭიროებისას Publish branding მხოლოდ დამტკიცების შემდეგ. Domain ownership უკვე დასრულებულია, მაგრამ Branding-ის საბოლოო დამტკიცება ჯერ არა. Google callback/env/login/reCAPTCHA ამ ეტაპზე არ შეცვლილა. Search Console-ის sitemap/ინდექსაციის სხვა ამოცანები კვლავ გადადებულია.

მომხმარებელმა ორივე CSRF შესწორების deployment და შემდეგ კოდით სრული საიტის შესვლა დაადასტურა. დომენისა და დახურული წვდომის ეტაპი დასრულებულია. ქვემოთ ძველი აუდიტის პანელური აღმოჩენები მიმდინარე შეცდომებად არ არის მიჩნეული. გარე ინტეგრაციები ხელახლა უნდა გადამოწმდეს საბოლოო დომენზე.

| პუნქტი | მდგომარეობა | დარჩენილი მოქმედება |
| --- | --- | --- |
| D01 ფოსტა | DNS გამიჯვნა დასრულებულია, მომხმარებელმა წერილების მიწოდება ვებგადართვამდე დაადასტურა | გადართვისშემდგომი კომპანიის ყუთის მიღება/პასუხი და Brevo authentication |
| D02 დომენი/HTTPS | Frontend root/www და backend api დომენები, ორივე IP-ზე TLS და www redirect დასრულებულია | ახალი admin მისამართია `https://api.flexdrive.ge/manager-fd/`; ძველი backend hostname-იც შენარჩუნებულია |
| D03 frontend URL | site URL და deployment დასრულებულია | ინდექსაციის flag D11-ს მიჰყვება, canonical/sitemap/გაზიარება საბოლოო შემოწმებას საჭიროებს |
| D04 backend URL-ები | FRONTEND_BASE_URL/CORS/CSRF, API hostname და BOG/Wingo callback URL-ები განახლებულია; BOG success/fail და Google/Facebook OAuth redirect env საბოლოო root-ზეა | ინტეგრაციების რეალური მუშაობა შესამოწმებელია |
| D05 Facebook საჯარო login | Meta-ში საბოლოო callback დაშვებულია; backend env გასწორდა და deployment Success/Live. App unpublished, Publish disabled; Business verification Incomplete/Pending submission | ბიზნესის ნამდვილი მონაცემებით ვერიფიკაციის დასრულება, შემდეგ testing/review/publish მოთხოვნების შემოწმება და ჩვეულებრივი მომხმარებლით შესვლა |
| D06 Facebook policy | Meta-ში შენახული და reload-ით დადასტურებულია საკუთარი privacy/terms/მონაცემების წაშლის ინსტრუქციის URL-ები; გარე extra.ge ბმული მოიხსნა | ამ URL-ების ნაწილი დასრულებულია; Meta-ს შემდგომი review შედეგი ჯერ უცნობია |
| D07 Google OAuth | Branding URL-ები საჯაროა, ownership დადასტურებულია. Google client-ში root origin/callback დაშვებულია, client ID ემთხვევა backend-ს. Backend `GOOGLE_OAUTH_REDIRECT_URI=https://flexdrive.ge/auth/google/callback` შენახულია; deployment `d0325823-7c6e-499a-86f1-161cdf17c960` Success/Live, app Healthy; შეიცვალა ზუსტად ერთი env | Login/reCAPTCHA ჯერ არ დატესტილა. ლოგო არ ატვირთულა. Branding retry: 2026-11-15 თბილისის 04:35-ის შემდეგ |
| D08 ბანკი | დომენთან დაკავშირებული env გასწორებულია 2026-11-14 | მომხმარებელმა რეალური გადახდა ხვალისთვის გადადო; merchant შეზღუდვა, success/fail/callback ნაკადი და შეკვეთის ერთჯერადი ასახვა ამ ეტაპზე არ დატესტილა |
| D09 გადახდების პერიოდული გადამოწმება | გაშვების გრაფიკი დასადასტურებელია | არსებული scheduler-ის მოძებნა, საჭიროებისას გამართვა, ბოლო წარმატება და შეტყობინება |
| D10 supplier/cleanup/alerts | მიმდინარე კონფიგურაცია დასადასტურებელია | რეალური განახლების სიხშირის შეთანხმება, cleanup და წარუმატებლობის/დაგვიანების შეტყობინებები |
| D11 SEO | საჯარო გახსნის ეტაპისთვის დარჩენილია | საერთო და ინდივიდუალური noindex, robots/sitemap/canonical შემოწმება |
| D12 Search Console | Google Branding-ისთვის Domain property და ownership verification დასრულდა | sitemap/URL Inspection/SEO-ის დანარჩენი სამუშაო მომხმარებლის წინა გადაწყვეტილებით გადადებულია |
| D13 GA4 შიდა ტრაფიკი | ხელახლა შესამოწმებელია | მიმდინარე IP წესის ტესტი და ფილტრის რეჟიმის შეთანხმება |
| D14 GTM/GA4 მოვლენები | `GTM-MVNFL9TH` და `G-CKQC30CKYJ` live იტვირთება 200-ით; თანხმობის შემდეგ root-ის `page_view` მიღებულია 204-ით. GTM Monitored domains-ში დაემატა `flexdrive.ge`, ცხრილში შენახვა დადასტურდა; diagnostics გახდა Good. Workspace changes 0 | ძიება/cart/checkout/purchase, GEL და დუბლირების არქონა კვლავ დასატესტია. დამატებითი ადმინისტრატორის რჩევა პანელში რჩება |
| D15 Meta დომენი | ხელახლა შესამოწმებელია | დომენის დადასტურება და გაზიარების preview |
| D16 Pixel/CAPI | GTM Meta Pixel Base იყენებს სწორ `1020718363721235` ID-ს. Meta Settings-ში Traffic permissions-ის სია შექმნილი არ არის (Create allow list). Pixel დაკავშირებულია არსებულ FlexDrive სარეკლამო ანგარიშთან `1462913205812039`: Meta-მ წარმატება და ერთი Connected asset აჩვენა. Backend component-ის 47 ENV-ში CAPI ჩართულია, სწორი Pixel ID და masked access token მითითებულია, graph v25.0/timeout 2; app-level FRONTEND_BASE_URL არის https://flexdrive.ge. საერთო 37 ENV-ში CAPI override არ არის. „Conversions API with Meta — Connection pending“ Meta-ს ცალკე შეთავაზებული კავშირის სტატუსია | რეკლამა არ გაშვებულა. Browser `fbevents.js` იბლოკებოდა ERR_BLOCKED_BY_CLIENT-ით; მომხმარებელმა ამ ეტაპზე პარამეტრებით შემოფარგვლა აირჩია. რეალური browser/server მიღება და Purchase deduplication დაუდასტურებელია |
| D17 Business ანგარიშები | დასადასტურებელია | საბოლოო დომენის სტატისტიკა, რეალური გაყიდვების საწყისი თარიღი და სატესტო შეკვეთების წარმოდგენა |
| D18 კომპანიის რეკვიზიტები | დასასრულებელია | მფლობელის ზუსტი იურიდიული მისამართი/ტელეფონი, პირობები და ქვითარი |
| D19 ავტორიზაციის წერილები | საბოლოო დომენზე შესამოწმებელია | აქტივაცია/პაროლის აღდგენა, სწორი ბმულები, contact/ოპერატორის წერილები |
| D20 აღდგენა/დაბრუნება | DNS ასლები და მიგრაციის backup შენახულია | არსებული restore-ის მტკიცებულება ან შეთანხმებული იზოლირებული ტესტი და დაბრუნების საბოლოო ჩანაწერი |
| D21 Cloudinary | გაშვების შემდგომი დაკვირვება დარჩენილია | მიმდინარე quota, ზრდა და შეტყობინებები. ძველი აუდიტის პროცენტი დღევანდელ მოხმარებად არ ჩაითვალოს |

Wingo ძველი აუდიტის შემდგომ დაემატა. ინტეგრაციის კოდი და production მიგრაციები გაკეთებულია, რეალური production ანგარიშის/გამგზავნის პარამეტრები, ცნობარები/ტარიფები და ცოცხალი booking/label/status ნაკადი ცალკე შესამოწმებელია. დომენის მიბმისას მხოლოდ ვებმისამართისა და წვდომის პარამეტრები შეიცვალა.

შემდგომი რიგი არის ბანკი, Google/Facebook/reCAPTCHA და წერილები, Wingo-ს production გამართვა, კომპანიის ქვითარი და ავტომატური პროცესები, სრული შეკვეთის შემოწმება. ანალიტიკა/SEO/Business ანგარიშების გაშვების პარამეტრებიც დასრულდეს შეთანხმებულ ეტაპზე. საბოლოო საჯარო გახსნას კვლავ admin-ის ერთი ღილაკი მართავს.

## პირველი ეტაპი — ფოსტის დამოუკიდებლობა

### შესრულებულია — ფოსტის ორი DNS ჩანაწერი

2026-11-13 მომხმარებლის „დაიწყე გააკეთე“ ნებართვით Computer Use-ით შევინახეთ ზუსტად ორი ცვლილება:

- `mail.flexdrive.ge` CNAME → A `136.243.25.146`, TTL 14400.
- `flexdrive.ge` MX → `mail.flexdrive.ge`, priority 0, TTL 14400.

cPanel-ში ორივე შენახვა წარმატებულია; 28 ჩანაწერის UI შედარებით მხოლოდ ეს ორი განსხვავდება. ორივე ავტორიტეტული nameserver-ის ახალი DNS პასუხიც ადასტურებს ზუსტ MX/A მნიშვნელობებს. დანარჩენი 26 query ჯგუფი უცვლელია; SOA serial განახლდა. TXT/NS პასუხების მიმდევრობა შედარებამდე დალაგდა, რადგან DNS პასუხის რიგი სტაბილური არ არის.

ავტორიტეტული DNS-ის before/after JSON ასლები (ორივე NS, ყველა 28 ჩანაწერი და NS/SOA) ინახება ignored `tmp/measurements-20261015/domain-cutover-20261113/`-ში. ძირითადი ვებ A კვლავ `136.243.25.146`-ია. რეალური შემოსული/გამავალი წერილით შემოწმება ჯერ არ ჩატარებულა. მხარდაჭერისთვის დასრულების შეტყობინება მომხმარებელმა უნდა გაგზავნოს; დროებითი სრული DNS წვდომის გამორთვა ჯერ არ დადასტურებულა. Computer Use დასრულდა და REPL reset შესრულდა ჩარჩოს მოსაშორებლად.

### Namespace-ის პასუხი და წვდომის შემოწმება — ცვლილებამდე

- მხარდაჭერამ დაადასტურა ფოსტის IP `136.243.25.146` და ინსტრუქცია: `mail.flexdrive.ge` CNAME შეიცვალოს A ჩანაწერით ამ IP-ზე, შემდეგ MX სამიზნე გახდეს `mail.flexdrive.ge`.
- მხარდაჭერის განმარტებით, Mail Hosting პაკეტში სრული Zone Editor ჩვეულებრივ შეზღუდულია. დროებით ჩართეს; დასრულების შემდეგ მომხმარებელმა უნდა შეატყობინოს, რომ ისევ გამორთონ.
- Computer Use-ით გადავამოწმეთ: ახლა ჩანს 28/28 ჩანაწერი და A/CNAME/MX მართვის ველები. MX კვლავ root-ზეა, mail კვლავ root-CNAME-ია. DNS ცვლილება არ შესრულებულა.
- ყველა 28 ჩანაწერის სახელი/TTL/ტიპი/მნიშვნელობა წაკითხულია cPanel UI-დან ამ სესიის ჩანაწერში. ეს ხედი არ შეიცავს SOA/NS-ს და BIND export არ არის. სხვა ჩანაწერებში არის Brevo verification, ორი Brevo DKIM, ადგილობრივი DKIM, DMARC, SPF და cPanel სერვისები.
- root-ის საბოლოო A ცვლილებამდე ცალკე გადასამოწმებელია SPF-ის `a` მექანიზმი და root-ზე მიმართული CalDAV/CardDAV SRV ჩანაწერები; ეს ფოსტის ორი მიმდინარე ცვლილების მოცულობაში არ შედის.

1. Namespace-ს დავუდასტურებინოთ ამ Mail Hosting პაკეტისთვის სწორი, ვებდომენის A-სგან დამოუკიდებელი MX სამიზნე, SSL IMAP/SMTP hostname, შესაბამისი A/CNAME ჩანაწერები და DNS ზონის სრული ასლის/რედაქტირების ადგილი.
2. DNS-ის სრული ასლი შევინახოთ და ცვლილებები ზუსტად იმ ჩანაწერებით მოვამზადოთ, რასაც პროვაიდერი დაადასტურებს. Brevo verification/DKIM, DMARC და სხვა მოქმედი ჩანაწერები უნდა დარჩეს. SPF თავიდან შემოწმდეს, რადგან `a`/`mx` მნიშვნელობა ვებ A-ს ან MX-ს მიჰყვება.
3. სანამ `flexdrive.ge`-ის A შეიცვლება, ფოსტა დამოუკიდებელ მისამართზე გადავიყვანოთ და შემოსული/გამავალი წერილი შევამოწმოთ. cPanel-ის Local Mail Exchanger პარამეტრი დაუდასტურებლად არ შევცვალოთ.

Namespace-სთვის გაგზავნილი თავდაპირველი ტექსტი (ისტორიული):

> გამარჯობა. `flexdrive.ge`-ის ვებსაიტი DigitalOcean App Platform-ზე გადაგვაქვს, ხოლო არსებული Mail Hosting და საფოსტო ყუთები Namespace-ზე უნდა დარჩეს. ამჟამად root A არის `136.243.25.146`, MX priority 0 მიუთითებს `flexdrive.ge`-ზე, `mail.flexdrive.ge` კი root-ის CNAME-ია. cPanel-ში Local Mail Exchanger არის არჩეული, ხოლო SSL IMAP/SMTP სერვერად `cp4.de.namespace.life` ჩანს. გთხოვთ დაგვიდასტუროთ ზუსტად რა MX, mail-host A/CNAME და SPF ცვლილებებია საჭირო, რომ root A-ს DigitalOcean-ზე გადატანისას ფოსტა არ შეწყდეს. შეიძლება თუ არა MX სამიზნედ `cp4.de.namespace.life` გამოყენება, თუ თქვენი რეკომენდაცია სხვა მუდმივი hostname-ია? სად შეგვიძლია ავტორიტეტული DNS ზონის სრული ჩანაწერების ნახვა/ექსპორტი და რედაქტირება? გთხოვთ ჯერ ჩანაწერები არ შეცვალოთ; მხოლოდ სწორი ინსტრუქცია დაადასტუროთ.

## მომზადება საბოლოო გახსნამდე

1. ორივე deployment, `pages.0085` production მიგრაცია, გარემოს გააქტიურება და დახურული რეჟიმის შემოწმება შესრულებულია. მომხმარებელმა admin-ში შექმნა კოდი და `https://flexdrive.ge/__preview`-ზე სრული საიტის შესვლა დაადასტურა. კოდის გარეშე ორივე hostname-ზე წვდომა უკვე შემოწმებულია. ზუსტი ნაბიჯები `docs/STOREFRONT_LAUNCH_ACCESS.md`-შია.
2. `flexdrive.ge`/`www` და `api.flexdrive.ge`, DNS და მოქმედი HTTPS გამართულია. ადმინისტრაციაა `https://api.flexdrive.ge/manager-fd/`. frontend-ის same-origin `/api` პროქსი უკავშირდება იმავე backend-ს API subdomain-ით; ძველი DigitalOcean backend hostname-იც შენარჩუნებულია.
3. დავაყენოთ საბოლოო frontend/backend მისამართები, OAuth/reCAPTCHA, BOG/Wingo callback-ები და დავტესტოთ ყველა მნიშვნელოვანი ნაკადი **შეზღუდულ წვდომაში**. პირდაპირი `ondigitalocean.app` მისამართიც უნდა იყოს დაცული; provider/bank webhook-ებს მხოლოდ საჭირო გამონაკლისები მიეცეთ.
4. საბოლოო საღამოს: ბოლო smoke check, შემდეგ საჯარო წვდომის ჩამრთველის გადართვა და დაუყოვნებელი გარედან შემოწმება. DNS-სა და HTTPS-ს ამ მომენტამდე მოვაგვარებთ; TTL/სერტიფიკატის ლოდინი ბოლო მოქმედებად არ უნდა დარჩეს. საძიებო ინდექსაცია ცალკე გააქტიურდება, როდესაც საჯარო გვერდები მზადაა.

საჯარო გაშვების პირობაა ფოსტის, TLS-ის, ავტორიზაციის, გადახდის/შეკვეთის, callback-ების და აღდგენის შემოწმებების გავლა. ძველი აუდიტის D01–D21 სხვა საკითხები ძალაში რჩება, სანამ თითოეული ხელახლა არ გადამოწმდება.
