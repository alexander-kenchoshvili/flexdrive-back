# ბიზნეს პანელი — გადაწყვეტილების ანგარიშები

მომზადებულია 2026-11-14. კოდი ლოკალურია; მომხმარებელი აკეთებს ორივე push/deploy-ს,
ბექენდი პირველი. მიგრაცია, ახალი ENV, ახალი გასაღები ან ნებართვა საჭირო არ არის.

## რა დაემატა

- `/business` — არსებული გაყიდვების/ფინანსების შეჯამების გვერდით Google/Meta-ს
  მოკლე სურათი, წინა პერიოდთან ცვლილება, განმარტებები და დეტალების ბმულები.
- `/business/users` — Google-ის ვიზიტები, მომხმარებლები, ecommerce შეძენები და
  purchaseRevenue GEL-ში; წყარო/სესიის კამპანიის პირველი 30 ჩანაწერი და სრული
  rowCount; თითოეულზე ვიზიტები, შეძენები და თანხა.
- მომხმარებლის თანმიმდევრული დახურული გზა: `view_item` → `add_to_cart` →
  `begin_checkout` → `purchase`. Google ითვლის activeUsers-ს, არა eventCount-ს.
  მომხმარებელი პირველ ეტაპზე უნდა შევიდეს; შუალედური მოქმედებები/რამდენიმე
  ვიზიტი დასაშვებია არჩეული პერიოდის ფარგლებში. ეს ყველა გადახდილი შეკვეთა არაა.
- `/business/marketing` — შეძენის საშუალო სარეკლამო ფასი, ROAS/დახარჯული 1-ის
  უკუგება, წინა პერიოდის შედარება; კამპანიის მიწერილი თანხა/CPA/ROAS; ცალკე link
  click და landing page view actions. ყველა დაწკაპუნება კვლავ ცალკეა.
- მოკლე ქართული შენიშვნები: არარსებული შეძენის აღრიცხვა, ყველაზე დიდი
  აბსოლუტური დანაკარგი ეტაპებს შორის, ხარჯი შეძენის გარეშე და ძველი პასუხები.
  მონაცემების სიმცირე/თანხმობა/დაგვიანება ცხადადაა აღნიშნული; მიზეზი არ იგონება.

## კონტრაქტი და დაცვა

ახალი კერძო `GET /api/business/decisions/{all|google|meta}/?start=...&end=...`.
არსებული დამოუკიდებელი ბიზნესსესია/უფლება მოწმდება cache/API-მდე, no-store
შენარჩუნებულია. წყვილი თარიღი, დღევანდელი დღის ზღვარი, მაქს366 დღე, შედარების
თარიღის underflow მოწმდება. წყაროს/property/account/hostname არჩევა მომხმარებლის
query-ით არ ხდება. მიმდინარე თვე ედრება წინა თვის შესაბამის ნაწილს არსებული
`previous_period` წესით; სხვა დიაპაზონი — წინა ამავე რაოდენობის დღეებს.

Google: არსებული read-only reader/property538949234, exact flexdrive.ge და კერძო
business/admin/manager-fd გზების გამორიცხვა. ერთი bounded batch იღებს მიმდინარე/
წინა ჯამებს და მიმდინარე წყაროებს. Funnel ცალკე v1alpha მოთხოვნაა; მისი შეცდომა
ძირითად მონაცემებს არ მალავს. v1alpha შესაძლოა შეიცვალოს: headers/rows მოწმდება,
მცდარი პასუხი ნულად არ ითვლება. Live ცარიელ პასუხში Google აბრუნებს ორ ერთნაირ
activeUsers header-ს; ეს ზუსტი ფორმა მხარდაჭერილია. არაცარიელ დუბლირებულ metric-ს
მხოლოდ ტოლი მნიშვნელობებით ვიღებთ; გაურკვეველი მნიშვნელობა უარყოფილია.

Meta: არსებული ანგარიშ1462913205812039/reader; მიმდინარე და წინა Ads ანგარიშს
იგივე5წუთიანი cache აქვს, რაც ძველ marketing გვერდს. შედარებისთვის სოციალურ
ანგარიშებს თავიდან არ ვკითხულობთ. მაქს3 პარალელური read, bounded provider timeout,
60წამი backoff, max24სთ last-good snapshot ძველი დროით. ერთი წყაროს შეცდომა სხვას
არ მალავს. GA4/Meta cache შეიცავს credential fingerprint-ს, საიდუმლო არ ბრუნდება.

CPA = spend / attributed website purchases (fractional modeled count ინახება).
ROAS = Meta-ს account-currency purchase value / spend; ეს მოგება არ არის.
ნულოვან მნიშვნელზე/უცნობ მონაცემზე ჩანს „—“. Meta-ს USD და Google-ის GEL
ერთმანეთზე არ იყოფა. წინა Ads შედარება მხოლოდ განახლებულ, იგივე ვალუტის/დროის
სარტყლის პასუხებზეა. Stale რიცხვებიდან ზრდა არ გამოითვლება. პლატფორმების
შეძენები არც ერთმანეთს და არც ფინანსურ ledger-ს არ ემატება.

## შემოწმება და დარჩენილი ნაბიჯი

-54 backend business/GA4/Meta/access ტესტი disposable SQLite-ზე, ქსელი დაბლოკილი.
-36 frontend analytics/marketing/report/decision ტესტი, მათ შორის CPA/ROAS,
  ნულოვანი/უცნობი მაჩვენებლები, ძველი მოთხოვნის გაუქმება, ავტორიზაცია/გასვლა და
  რეალური Vue template compiler. Typecheck/scoped ESLint და production build წარმატებულია.
- რეალური read-only API, Nov1–14: Google ready (1 session/1 user/0 purchase),
  source rows1; ordered funnel ready/ცარიელი; Meta მიმდინარე/წინა valid empty,
  USD/Asia-Tbilisi. სატესტო tracking event, შეკვეთა ან გადახდა არ გაგზავნილა.
  უსაფრთხო მტკიცებულება ignored tmp/measurements-20261015/business-decisions-20261114/.
- ახალ ეკრანებზე live ვიზუალური/mobile შემოწმება ხდება მომხმარებლის deploy-ის
  შემდეგ. ამ ეტაპზე dev server/browser არ გაშვებულა; layout იყენებს არსებულ
  ტოკენებს, responsive1/2/4 სვეტებს და მხოლოდ ცხრილის შიდა scroll-ს.
- რეალური შესყიდვის მიწოდება/Pixel+CAPI deduplication და არაცარიელი live კამპანიის
  მონაცემები კვლავ ცალკე ტესტია. ჯერ ციფრები მცირეა; მზადმყოფი ანგარიში მათ
  სისწორეს ავტომატურად ვერ ადასტურებს.

რეკლამის შექმნისას URL parameters-ში UTM ნიშნები დაგვჭირდება, რომ Google-ში
კამპანიები გაირჩეს: `utm_source={{site_source_name}}&utm_medium=paid_social&`
`utm_campaign={{campaign.name}}&utm_id={{campaign.id}}&utm_content={{ad.id}}`.
ეს რეკლამის შექმნის ნაბიჯია; ამ სამუშაოში რეკლამა ან ბიუჯეტი არ შეცვლილა.

ოფიციალური საფუძველი: [Google Funnel API](https://developers.google.com/analytics/devguides/reporting/data/v1/funnels),
[GA4 fields](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema),
[Meta Insights](https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights),
[Vue async cleanup](https://vuejs.org/guide/essentials/watchers#side-effect-cleanup).
