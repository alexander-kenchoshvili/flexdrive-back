# FlexDrive — საჯარო გახსნის შემდეგ SEO

მომხმარებელმა მაღაზია თავად გახსნა 2026-11-16. ანონიმური launch API ადასტურებს
`guard_enabled=true`, `public_open=true`. ეს ანგარიში ცვლის ძველი გეგმის
„მაღაზია დახურულია“ მიმდინარე სტატუსს; ძველი ჩანაწერები ისტორიულია.

## საიტზე დადასტურებულია

- [x] მთავარი და კატალოგი საჯაროდ200, `index, follow`; ერთი სწორი canonical.
- [x] `robots.txt`:200/text/plain, `Allow: /`, ბიზნესპანელის აკრძალვა და სწორი sitemap.
- [x] `sitemap.xml`:200/application/xml,1995 უნიკალური URL:1979 პროდუქტი,
  8 კატეგორია,3 სტატია,5 სხვა გვერდი. ყველა URL-ის ჰოსტი/ფორმატი შემოწმებულია.
  კერძო/query/fragment/დუბლირებული მისამართი არ შედის.
- [x]36 შერჩეული გზა: ყველა8 კატეგორია და3 სტატია,6 პროდუქტის ნიმუში,
  მთავარი/კატალოგი/page2/ძებნა/ფილტრები/პირადი/უცნობი გზები.
  ეს არ ნიშნავს1995-ვე გვერდის ინდივიდუალურ ჩამოტვირთვას.
- [x] გვერდი2 საკუთარ canonical-ს ინარჩუნებს. ძებნა/მარკა/დალაგების query-ები
  `noindex, follow` და სუფთა კატალოგის canonical-ია. პირადი გზები noindex რჩება.
- [x] უცნობი ჩვეულებრივი/პროდუქტის გვერდები ნამდვილი404/noindex-ია.
- [x]6 პროდუქტის JSON-LD-ში სახელი, FD SKU, GEL, დადებითი ფასი და availability;
  3 სტატიის Article და Breadcrumb JSON-LD იკითხება parse შეცდომის გარეშე.
  უმარაგო ერთ ნიმუშს სურათი არ აქვს — მომხმარებლის არსებული პოლიტიკა უცვლელია.
  ეს ადგილობრივი სტრუქტურის შემოწმებაა და არა Google Rich Results-ის დასტური.
- [x] დროებით DO hostname-ზე X-Robots-Tag `noindex,nofollow` რჩება და canonical
  flexdrive.ge-ზეა. www გადადის root-ზე და page query ინარჩუნებს.

პირველი5 პარალელური მოთხოვნის ჯგუფში4 გვერდმა500 დააბრუნა. ცალ-ცალკე განმეორებით
ოთხივე200 იყო. მიზეზი არ არის დადგენილი; არ ვაცხადებთ სრულ გამძლეობის ტესტს ან
შეფერხების მიზეზის აღმოფხვრას. HTML parser-ის თავდაპირველი title დეფექტი
(SVG logo-ს title ფარავდა document title-ს) შემოწმების სკრიპტში გასწორდა;
განმეორებით ნამდვილ head title-ებში კონტექსტური სათაურებია.

## Google Search Console — გახსნის ძირითადი ეტაპი დასრულებულია

- [x] Owner-ის `sc-domain:flexdrive.ge` property გახსნილია.
- [x] sitemap ფორმა მომზადდა. შემდეგ უკვე გამოჩნდა სიაში16ნოემბრის ჩანაწერი;
  აგენტს SUBMIT-ზე დაჭერა არ დაუფიქსირებია. ვის მიერ გაიგზავნა, არ ვამტკიცებთ.
  მომხმარებელმა შემდეგ sitemap-ის გაგზავნა პირდაპირ დაადასტურა.
- [x] sitemap წარმატებით წაიკითხა Google-მ: საბოლოო live სიაში ტიპი `Sitemap`,
  Submitted/Last read16Nov2026, მწვანე **Success**, **1,995 discovered pages**,
  videos0. თავდაპირველი `Couldn't fetch / General HTTP error` /0 გვერდის
  ჩანაწერი უკვე ისტორიულია; პრობლემა ქვემოთ აღწერილი recrawl-ით დაიხურა.
- [x] sitemap URL-ის Google LIVE TEST რეალურად შესრულდა16ნოემბერს21:12:
  `Blocked by robots.txt`. robots ანგარიშში ნანახი ბოლო ვერსია15ნოემბერი22:56,
  26bytes, პირდაპირი შიგთავსი `User-agent: *` / `Disallow: /`.
  ცოცხალი საიტი meanwhile `Allow: /`-ს აბრუნებს. Google-ის ქეშში ძველი აკრძალვაა.
- [x] მომხმარებელმა robots-ის recrawl ცალკე დაადასტურა. ლიმიტით შეჩერებულ მცდელობას
  ქმედება არ შეუსრულებია. გაგრძელებისას შესრულდა მხოლოდ root HTTPS robots-ის
  `Request a recrawl`; Google-ის მწვანე ფანჯარა: **Recrawl request sent**,
  File `https://flexdrive.ge/robots.txt`, `Check back soon to see the results`.
- [x] მოთხოვნის შემდეგ robots ანგარიში განახლდა:16ნოემბერი22:50, `Fetched`,84bytes,
  ძველი15ნოემბერი22:56/26bytes-ის ნაცვლად. ახალი ფაილის პანელი ტრიალებდა და
  ამ მომენტში ახალი ტექსტი UI-ში არ წაკითხულა; განახლებული თარიღი/ზომა დადასტურებულია.
- [x] ამის შემდეგ აგენტმა მომხმარებლის უკვე გაცემული დასტურით იგივე sitemap
  ხელახლა გაგზავნა. Google-ის მწვანე ფანჯარა: **Sitemap submitted successfully**.
  გაგზავნის მიღება არ უდრის sitemap Success-ს ან გვერდების ინდექსაციას.
- [x] ახალი robots-ის Google-ში წამოღება დადასტურებულია16ნოემბერი22:50/84bytes.
- [x] მთავარი გვერდის Google LIVE TEST16ნოემბერი22:57: **URL is available to Google**,
  **Page can be indexed**. წინა GOOGLE INDEX ჩანართში14ნოემბრის noindex შედეგი
  ისტორიულია და ამ LIVE TEST-ით მიმდინარე აკრძალვად არ დასტურდება.
- [x] sitemap-ის Success და1995 მისამართის აღმოჩენა დადასტურებულია.
- [ ] Google-ში გვერდების რეალური ინდექსაცია/გამოჩენა ბუნებრივი შემდგომი პროცესია;
  დასრულებულად არ ვაცხადებთ. წარმატებული live fetch და sitemap Discovery
  არ ნიშნავს უკვე ინდექსირებულ გვერდს ან რანგს.
- [x] Google-ის პროდუქტის რეალური LIVE TEST16ნოემბერი22:55:
  `https://flexdrive.ge/catalog/airbegis-khufi-fd-03-0297` →
  **URL is available to Google**, **Page can be indexed**. Google-მა ამოიცნო
  Product snippets, Merchant listings და Breadcrumbs — თითო1 valid item.
  ეს ინდექსაციის დასრულებას ან search result-ში გამოჩენას არ ადასტურებს.
  Merchant listings-ის3 optional გაფრთხილება: `category` მნიშვნელობა,
  `hasMerchantReturnPolicy` და `shippingDetails`. არ შეგვივსია გამოგონილი
  ტარიფი/დაბრუნების პირობა და source არ შეცვლილა; შემდგომი გაუმჯობესებაა.
- [ ] მობილური სიჩქარის შეფასება: საჯარო PageSpeed API-მ ორივე URL-ზე429 quota
  exceeded დააბრუნა. სიჩქარის ან SEO ქულა არ მოგვეპოვება; საიტის დეფექტად არ ითვლება.

შემდგომ კონტროლზე Search Console → Pages/Performance-ში ვაკვირდებით რეალურ
ინდექსაციასა და ძიების მონაცემებს. ამ ეტაპზე იგივე sitemap-ის დამატებით გაგზავნა,
ახალი კოდის deployment ან indexing ENV-ის გადართვა საჭირო არ აღმოჩნდა.
მთავრისა და პროდუქტის URL Inspection → TEST LIVE URL-მა Google-ის რეალური წვდომა
დაადასტურა. ინდექსაციის ვადა/რანგი გარანტირებული არ არის.

ფუნქციური კოდი/ENV/DNS/CMS/პროდუქტები/გადახდები ამ SEO შემოწმებაში არ შეცვლილა.
შეიცვალა მხოლოდ Google-ში recrawl/sitemap მოთხოვნები და პროექტის სტატუსის დოკუმენტები.
დეტალური aggregate მტკიცებულებები ignored
`tmp/measurements-20261015/seo-prelaunch-20261115/postopen-*.json` და
`mobile-pagespeed.json`-შია. რეალური გადახდის ტესტი დამოუკიდებელი საკითხია.

Google-ის ოფიციალური აღწერები:
[robots ანგარიშის ხელახალი წაკითხვა](https://support.google.com/webmasters/answer/6062598?hl=en),
[sitemap-ის შეცდომები](https://support.google.com/webmasters/answer/7451001).
