# FlexDrive — SEO გახსნის წინ, 2026-11-15

## განხორციელების მიმდინარე მდგომარეობა — 2026-11-15

მომხმარებელმა სრული SEO გეგმის თანმიმდევრული შესრულება დაავალა. ქვემოთ არსებული
აუდიტი საწყის მდგომარეობას აღწერს; მიმდინარე შესრულება ამ სექციაში ფიქსირდება.
მაღაზია არ გახსნილა, production ENV არ შეცვლილა, push/deploy არ შესრულებულა.

- [x] საჯარო/პირადი გზების პოლიტიკა კოდში მომზადებულია. `order-status`, preview,
  auth და manager გზები დამატებით დაცულია noindex-ით. საკონტაქტო პოლიტიკა უცვლელია.
- [x] robots/sitemap დახურულსა და preview რეჟიმში აბრუნებს ნამდვილ ტექსტს/ცარიელ XML-ს,
  პროდუქტის მონაცემების მოთხოვნის გარეშე; backend outage-ზე503/Retry-After. ღიაზე
  sitemap backend-ის სწორ API გზას კითხულობს, არაკანონიკურ/პირად/query URL-ებს ფილტრავს.
- [x] საერთო indexing ENV-ის მკაცრი parsing; მხოლოდ `https://flexdrive.ge` ჰოსტი
  იღებს ინდექსაციის ნებართვას. starter-ს noindex header და დახურული robots/ცარიელი
  sitemap რჩება. forwarded-host-ით ნებართვის მოტყუება არ გამოდის.
- [x] კატეგორიის ხილული H1/შესავალი იყენებს მის სახელს/SEO აღწერას; ძებნის ტექსტი დაცულია.
- [x] აღმოჩენილი პროდუქტის canonical bug გასწორდა backend-ში: ხელით მოცემულ ძველ
  slug-ზე FD კოდი ორჯერ აღარ მიეწერება. ზუსტად ძველი პროდუქტის path გადადის საჯარო
  path-ზე, სხვა override/query არ გადაიწერება. მონაცემთა მიგრაცია არ სჭირდება.
- [x] ძველი standalone SEO test loader გასწორდა რეალური gallery composable-ებით.
  frontend79 ტესტი წარმატებულია, scoped ESLint/typecheck/production build წარმატებულია.
  backend48 ტესტი წარმატებულია (ერთი SQLite locking ტესტი გამოტოვებულია).
  აწყობილ Nitro-ზე10 სცენარი და4 outage შემოწმება წარმატებულია: closed/preview/open/
  starter/reclosed და runtime `true`/`false` ENV. ეს ლოკალური შემოწმებაა, არა live deploy.
- [x] CMS: Pages სიაში მხოლოდ contact(5), blogs(3), catalog(2) noindex უჯრები
  მოიხსნა. მომხმარებლის ახალ retry-ზე Save წარმატებულია: **3 pages were changed
  successfully**; reload-ით სამივე მოუნიშნავი დარჩა. სხვა120 ხელმისაწვდომი editable
  მნიშვნელობა იგივეა. main/about-us უკვე მოუნიშნავი იყო; legal/help/სხვა flags
  უცვლელია. anonymous API კვლავ guard=true/public_open=false; root noindex/holding.
- [x] Admin-ის read-only ფილტრებით1981 გამოქვეყნებულ პროდუქტსა და13 კატეგორიაში
  noindex=true ჩანაწერი0, არაცარიელი canonical override0.3 BlogPost-ში ორივე ფილტრი0.
  SEO ფლაგების დამატებითი მასობრივი ცვლილება საჭირო არ აღმოჩნდა.
- [ ] ფოტოები/კონტენტი:1981 გამოქვეყნებული პროდუქტიდან256-ს ProductImage ჩანაწერი
  საერთოდ არა აქვს. ეს მიმდინარე ზუსტი ფილტრის შედეგია, არა ძველი353 რიცხვი.
  დანარჩენების ფოტოების ხელმისაწვდომობა/სისწორე/alt ინდივიდუალურად ჯერ არ შეფასებულა.
  სურათები/მონაცემები არ შეგვიცვლია; მომხმარებლის რეალური ფოტოები/წყარო დაგვჭირდება.
- [ ] ორივე რეპოზიტორიის push/deploy მომხმარებელს ეკუთვნის, backend შემდეგ frontend.
  საჭიროა ახალი source ვერსიების deployment **ინდექსაციის ENV ჩართვამდე**.
- [ ] DO-ს მოქმედი `NUXT_PUBLIC_SITE_URL`/`NUXT_PUBLIC_ALLOW_INDEXING`/guard editor
  ჯერ წასაკითხია (სესია გასული იყო). ახალი კოდის deployment-ის დადასტურების შემდეგ
  შეიძლება indexing flag=true მომზადდეს, public_open=false შენარჩუნებით; რეალურ
  ჰოსტზე დახურული პასუხების დაცვა დამოუკიდებლად გადამოწმდეს.
- [ ] მომხმარებლის მიერ გახსნის შემდეგ live URL/canonical/meta/schema/sitemap,
  Search Console sitemap/inspection, Rich Results და მობილური სიჩქარის შეფასება.
- [ ] შერჩეული თემატური გვერდები/ქართული გზამკვლევები/ნამდვილი ფოტოები საჭიროებს
  რეალურ მონაცემებს/კონტენტს; Merchant Center ცალკე eligibility/language არჩევანია.

წინა URL-confidence შეჩერების შემდეგ მომხმარებლის ახალი retry წარმატებულია;
CMS შენახვა დადასტურდა. შემდეგი აუცილებელი ჩართვა მომხმარებლის ორივე deploy და
DigitalOcean-ში შესვლაა; ახალი კოდის deployment-მდე indexing ENV არ ჩაირთოს.
მტკიცებულება ignored `tmp/measurements-20261015/seo-prelaunch-20261115/`:
`implementation-tests.log`, `typecheck.log`, `build.log`, `built-smoke.json`,
`cms-result.json`, `after-cms-http.json`, `catalog-inventory.json`. Computer Use
kernel reset შესრულდა capture-ის გასათავისუფლებლად.
გაშვების ნაბიჯები: [SEO release](SEO_RELEASE_2026-11-15.md).

## საწყისი აუდიტი (განხორციელებამდე)

შესრულდა აუდიტი და გეგმა, არა ინდექსაციის გახსნა. შემოწმდა მიმდინარე ორივე
რეპოზიტორიის კოდი, production Django admin-ის Pages სია და რვა საჯარო HTTP GET.
CMS/ENV/DNS/მონაცემები/პროგრამის ფუნქციური კოდი არ შეცვლილა. მაღაზია დახურულია.

## მარტივი მნიშვნელობები

- `NUXT_PUBLIC_ALLOW_INDEXING` — საერთო ნებართვა, იმუშავოს საჯარო SEO პოლიტიკამ.
- `noindex` — კონკრეტული გვერდი საძიებო შედეგებში არ შეიტანო. საერთო ნებართვა
  გვერდზე ცალკე არსებულ აკრძალვას არ აუქმებს.
- `robots.txt` — რობოტებისთვის crawl-ის წესები; ინდექსაციის აკრძალვას არ ანაცვლებს.
- `sitemap.xml` — სასურველი, კანონიკური საჯარო მისამართების სია.
- `canonical` — ამ შინაარსის ძირითადი მისამართის მითითება, არა წვდომის დაცვა.

## დღეს დადასტურებული

| თემა | ფაქტი | დასკვნის ზღვარი |
| --- | --- | --- |
| მაღაზიის დაცვა | `/api/launch/status/`: guard=true, public_open=false | ინდექსაცია/გახსნა არ შეგვისრულებია |
| საჯარო HTML | მთავარს/კატალოგს HTTP200 holding გვერდი, robots meta და X-Robots-Tag noindex/nofollow აქვს | სრული პროდუქტის live HTML ამ ეტაპზე არ შემოწმებულა |
| www | `/catalog?page=2` ->308 `https://flexdrive.ge/catalog?page=2` | გზა/query შენარჩუნებულია |
| CMS Page ფლაგები | production ადმინში catalog/blogs/contact მონიშნულია SEO NOINDEX; main/about-us მოუნიშნავია | წაკითხულია მიმდინარე UI; პროდუქტების/კატეგორიების ყველა ფლაგის DB აუდიტი არ ჩატარებულა |
| robots/sitemap დახურულზე | ორივე ანონიმურ მისამართზე guard აბრუნებს holding HTML-ს, არა text/plain/XML-ს | ახლა შინაარსი დაცულია; გახსნის საბოლოო პასუხები ჯერ შესამოწმებელია |
| დროებითი DO ჰოსტი | starter frontend-ზე GET / ჯერ200 holding/noindex-ია, root-ზე redirect არაა | საჯარო გახსნის შემდეგ noindex ქცევა ჯერ live არ შემოწმებულა |
| ENV | კოდში allowIndexing ნაგულისხმევად false, siteUrl production-ში ENV-ით მოდის | ამ აუდიტში DO-ს მოქმედი ENV editor არ გახსნილა; ტაბების სესია გასულია |

## უკვე არსებული საფუძველი — კოდის შემოწმება

- პროდუქტის ავტომატური სათაური იყენებს ნაწილს/მარკას/მოდელს/წლებს/მხარეს/მწარმოებელს;
  ხელით დაწერილი override დაცულია. OEM/SKU-ის სათაურში ხელოვნურად დამატება არ იგეგმება.
- პროდუქტი, კატეგორია და ბლოგი იღებს SEO ტექსტს/სურათს/canonical-ს. Product/Offer,
  BreadcrumbList, Article და Organization JSON-LD უკვე წერია. ფასი GEL-ით და რეალური
  მარაგითაა გათვალისწინებული; უცნობ ფასზე Offer არ უნდა გამოიგონოს.
- პირადი/კალათის/checkout/business გზებისთვის ინდექსაციის აკრძალვა არსებობს.
- ფილტრიანი/საძიებო კოლექციები noindex/follow-ს იღებს, ჩვეულებრივი გვერდი2 საკუთარ
  `?page=2` canonical-ს. გადაფურცვლის ბმულები SSR HTML-შია.
- ცარიელი კატეგორია noindex-ს იღებს; გამოგონილი CMS გზები/უცნობი კატეგორიები/error
  სტატუსები მიზნობრივი პოლიტიკით მუშავდება. ძველი ბლოგის slug კანონიკურ გზაზე გადადის.
- sitemap კოდი არჩევს გამოქვეყნებულ, არადამალულ პროდუქტებს, აქტიურ არაცარიელ
  კატეგორიებს და გამოქვეყნებულ ბლოგებს; სხვა origin-ის URL-ს frontend გამორიცხავს.
- Search Console Domain ownership და სტატისტიკის reader უკვე დაკავშირებულია.

ეს სექცია კოდის არსებობას ადასტურებს. ყველა პროდუქტის ახლანდელი საწყისი HTML,
რეალური ფოტოების რაოდენობა, Rich Results და სიჩქარე ცალკე შემოწმების საგანია.

## გახსნამდე შესასრულებელი, ამ თანმიმდევრობით

1. **გახსნის SEO მატრიცა.** მთავარს, კატალოგს, კარგ პროდუქტებს/კატეგორიებს,
   ბლოგის სიასა და სტატიებს ინდექსაცია ექნება. კონტაქტი/about-us საჯარო ინდექსაციისთვის
   შევათანხმოთ. login/register/cart/profile/checkout/business/order-status დაიხურება.
   გადახდის/მიწოდების/დაბრუნების საინფორმაციო გვერდები ინდივიდუალურად გადაწყდეს;
   ყველა noindex-ის ბრმად მოხსნა არ არის საჭირო. მოქმედი საკონტაქტო პოლიტიკა უცვლელია.
2. **robots/sitemap და დაცული რეჟიმი.** დავამზადოთ მკაფიო text/plain robots და
   XML sitemap დახურულ რეჟიმშიც (აკრძალვა/ცარიელი სია); საჯარო URL-ები მანამდე არ
   გამოვიტანოთ. ღია რეჟიმში რეალური sitemap, სწორი Content-Type და crawl-ის წესები.
   Backend sitemap fetch-ის გამართულობა მიმდინარე api.flexdrive.ge კონფიგურაციით
   ცალკე უნდა გადამოწმდეს. source utility/route-ის robots ლოგიკა ნაწილობრივ დუბლირებულია.
3. **ერთი ძირითადი ჰოსტი.** საჯარო SEO root=`https://flexdrive.ge`. კოდში www redirect
   არსებობს, მაგრამ shared frontend starter host-ისთვის ცალკე noindex შეზღუდვა არ ჩანს.
   საერთო ENV-ის ჩართვამ იქაც index meta/ღია robots შეიძლება გამოაჩინოს. პირველადი
   canonical ამის სრული შემცვლელი არ არის. ავირჩიოთ მუდმივი redirect ან host noindex;
   ძველი OAuth მისამართები/preview მოქმედება შემთხვევით არ გავტეხოთ.
4. **მონაცემებისა და ENV-ის მომზადება.** მხოლოდ შეთანხმებული საჯარო CMS ფლაგები;
   `NUXT_PUBLIC_SITE_URL=https://flexdrive.ge`; ინდექსაციის ENV და LaunchControl ცალკე
   ჩამრთველებია. საბოლოო ღილაკთან თანხვედრა დავამტკიცოთ: დახურულ/preview რეჟიმში
   effective noindex რჩება, ღია რეჟიმში სასურველი გვერდები index ხდება. ახალი ფლაგების
   შენახვამდე backup/ზუსტი განსხვავების შემოწმება; ახლა არაფერი შეგვიცვლია.
5. **უკვე ღია საიტის საკონტროლო შემოწმება.** მთავარი, კატეგორია, პროდუქტი, ბლოგი,
   page2, ძებნა/ფილტრი, უცნობი მისამართი, პირადი გვერდი და starter ჰოსტი. თითოეულზე
   HTTP სტატუსი, meta/header robots, ერთი სწორი canonical, სათაური/H1/აღწერა,
   საწყისი HTML/JSON-LD, სურათების წაკითხვადობა. Sitemap URL-ები იყოს200, indexable,
   კანონიკური და უნიკალური. ეს ეტაპი რეალური გახსნის შემდეგ სრულდება.
6. **Google-ს მიწოდება.** სწორი sitemap-ის დამატება Search Console-ში, რამდენიმე
   მნიშვნელოვანი URL-ის live inspection და Rich Results შემოწმება. მერე Page indexing,
   sitemap errors და Search Console clicks/impressions ყოველდღიურად პირველ პერიოდში.
   sitemap-ის მიწოდება ინდექსაციის/პირველი პოზიციის გარანტია არ არის.

## მაღალი სარგებლის დამატებითი სამუშაო — გაშვებისგან ცალკე

- კატეგორიის ხილული H1 ამჟამად ზოგადი კომპონენტის title-დან მოდის (`კატალოგი` fallback).
  კონკრეტული კატეგორიის სახელი და მოკლე გამოსადეგი ტექსტი თემას უკეთ განმარტავს.
- მოდელი+ნაწილის მოთხოვნებზე ხარისხიანი შერჩეული გვერდები: მაგალითად Toyota Camry-ის
  შესაბამისი წლების ბამპერები, რეალური თავსებადობით/მარაგით/ბმულებით. ყველა ფილტრის
  ავტომატურად გახსნა და ათასობით ცარიელი გვერდი არ იგეგმება.
- ნამდვილი ფოტოები, ზუსტი alt, OEM/თავსებადობის სრული ტექსტი, აღწერების გაუმჯობესება.
  წინა აუდიტის ფოტო-დანაკლისის რიცხვი ძველია; დღეს ხელახლა არ დათვლილა.
- გამოსადეგი ქართული გზამკვლევები, რომლებიც შესაბამის პროდუქტებზე გადადის:
  მოდელის თაობის/წლის გარჩევა, მარცხენა-მარჯვენა ნაწილი, ანალოგის სწორად არჩევა.
- მობილური Core Web Vitals/PageSpeed შემოწმება რეალურ გვერდებზე; ახლა სიჩქარე არ
  გაზომილა და მწვანე ქულა არ მიგვიწერია. სურათის ზომა, LCP, CLS და JS საჭიროებისამებრ.
- Merchant Center შეიძლება იყოს დამატებითი არხი: საქართველო/GEL მხარდაჭერილია,
  მაგრამ ქართული არ არის მხარდაჭერილი feed ენების მიმდინარე სიაში. ქართული feed-ის
  პირდაპირ მზადყოფნას არ ვაცხადებთ. შესაბამისი ენა/landing/checkout, პოლიტიკები და
  eligibility ჯერ ცალკე უნდა შეფასდეს; ეს ორგანული ქართული Search SEO-ს არ კეტავს.

## ტესტები და შეზღუდვები

არსებული ექვსი SEO suite:39 ტესტიდან33 გავიდა,6 ვერ შესრულდა — ყველა შეცდომა
`Cannot find module '~/composables/catalog/useProductGalleryPreload'`. მოდული რეალურად
არსებობს; ძველი standalone ტესტების loader ახალ Nuxt alias import-ს არ ამუშავებს.
ეს production-ზე მოდულის არქონის მტკიცებულება არ არის, მაგრამ Product/JSON-LD-ის
მიმდინარე სრულ რეგრესიას წარმატებულად ვერ ვაცხადებთ. loader/stubs გასაახლებელია და
ტესტები თავიდან გასაშვებია. ამ აუდიტში არც ტესტის კოდი შეცვლილა.

Frontend git status აუდიტის შემდეგ სუფთაა. HTTP მტკიცებულება და test log:
ignored `tmp/measurements-20261015/seo-prelaunch-20261115/`.
პირველი HTTP script-ის stdout-ს ქართული ტექსტის encoding შეცდომა ჰქონდა; შედეგის
JSON მანამდე წარმატებით ჩაიწერა და დამოუკიდებლად წავიკითხეთ. დამხმარე script მოიხსნა.

## ოფიციალური საყრდენი

- [ახალი მაღაზიის გაშვება Google-ში](https://developers.google.com/search/docs/specialty/ecommerce/how-to-launch-an-ecommerce-website)
- [URL/canonical სტრუქტურა](https://developers.google.com/search/docs/specialty/ecommerce/designing-a-url-structure-for-ecommerce-sites)
- [robots-ის დანიშნულება](https://developers.google.com/search/docs/crawling-indexing/robots/intro)
- [sitemap-ის მომზადება](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Product მონაცემები](https://developers.google.com/search/docs/appearance/structured-data/product-snippet)
- [Merchant Center-ის ენები/ვალუტები](https://support.google.com/merchants/answer/160637?hl=en)
