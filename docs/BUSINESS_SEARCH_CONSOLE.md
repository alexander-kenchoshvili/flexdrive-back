# Search Console ბიზნეს პანელში — 2026-11-14

კოდი მზადაა ორივე რეპოზიტორიაში. მომხმარებელი აკეთებს backend push/deploy-ს,
შემდეგ frontend push/deploy-ს. ახალი ENV, გასაღები ან მიგრაცია არ სჭირდება.

## კავშირი

- Search Console Domain property: `sc-domain:flexdrive.ge`. UI-ში Ownership verified
  დადასტურებულია; საკუთრების არსებული CNAME არ შეცვლილა.
- Google Cloud FLEXDRIVE/flexdrive-494109 პროექტში ჩაირთო Search Console API.
  API-ის პანელმა Enabled აჩვენა. ახალი პროექტი/ანგარიში/გასაღები არ შექმნილა.
- არსებულ `flexdrive-analytics-reader@flexdrive-494109.iam.gserviceaccount.com`
  service account-ს დაემატა მხოლოდ **Restricted** უფლება ამ property-ზე.
  მომხმარებელმა უფლების ახსნის შემდეგ პირდაპირ დაადასტურა „გასაგებია. დაამატე“.
  Users and permissions-ში დარჩა არსებული verified owner და დაემატა reader/Restricted.
- იგივე BUSINESS_GA4_CREDENTIALS_JSON/FILE გამოიყენება. GA4-ის მოთხოვნების scope
  არ იცვლება; Search Console იღებს ცალკე `webmasters.readonly` scope-ის ასლს.
  Customer Google Login/Branding/პაროლები/სხვა Google რესურსები არ იცვლება.
- რეალური read-only პასუხი გახდა HTTP200. სრული ახალი reader-ის ხუთივე მოთხოვნა
  წარმატებულია: მიმდინარე/წინა ჯამები, დღეები, სიტყვები, გვერდები. 1–11 ნოემბრის
  საბოლოო მონაცემები ცარიელია; average position უცნობია, არა0. მტკიცებულება:
  ignored `tmp/measurements-20261015/search-console-20261114/live-read.json`.

## რას აჩვენებს

- `/business` — მოკლე Search Console ბლოკი, ოთხი მთავარი მაჩვენებელი და დეტალების ბმული.
- `/business/users` — ცალკე „როგორ გვპოულობენ Google-ში“: გამოჩენები, დაწკაპუნებები,
  CTR, საშუალო პოზიცია, წინა პერიოდის ცვლილება, დღიური გრაფიკი/ცხრილი და პირველი50
  საძიებო სიტყვა/გვერდი დაწკაპუნებებით. ძველ შიდა ძიებას აშკარად დაერქვა
  „რას ეძებენ ჩვენს საიტზე“. GSC დამოუკიდებელია GA4-ის ჩატვირთვის/წვდომისაგან.
- მაჩვენებლებს ახლავს მარტივი ქართული განმარტებები. CTR ცვლილება პროცენტულ
  პუნქტებშია; პოზიციის კლება გაუმჯობესებაა. უცნობი/მიუწვდომელი არ ჩანაცვლდება0-ით.
- წყარო web Search-ია, რეკლამის გარეშე; მთელი Domain property, www და ქვედომენებიც.
  GSC დაწკაპუნება, GA4 სესია და საკუთარი ბაზის შეკვეთა სხვადასხვა მაჩვენებელია.
  Property-ის ჯამი ცალკე იკითხება, top query/page/daily სიებიდან არ გამოითვლება;
  position/CTR ხელით არ საშუალოვდება. გვერდების აგრეგაცია byPage, დანარჩენი
  byProperty. ანონიმური/იშვიათი მოთხოვნები/API top-row შეზღუდვა გამოკვეთილია.

## თარიღები და დაცვა

კერძო `GET /api/business/search-console/?start=YYYY-MM-DD&end=YYYY-MM-DD`, იგივე
BusinessSession/permission gate და no-store. არ იღებს browser token-ს, property-ს,
URL-ს, scope-ს ან account ID-ს მომხმარებლისგან. ორივე თარიღი/366დღე/დღევანდელი დღის
ზღვარი მოწმდება არსებული კონტრაქტით. API URL/property კოდში ფიქსირებულია.

Search Console იყენებს PT დღეებს (America/Los_Angeles). შეგნებულად გამოტოვებულია
უახლესი3 PT დღე და იკითხება მხოლოდ dataState=final. UI აჩვენებს მოთხოვნილიდან
მიღებულ რეალურ პერიოდს და დაგვიანების განმარტებას; Google-ს მეტი დროც შეიძლება
დასჭირდეს. ისტორია16თვით იზღუდება. წინა პერიოდი ითვლება რეალურად გამოყენებული
პერიოდიდან, არსებული month/equal-days წესით. ძველი მიუწვდომელი შედარება ცალკე ჩანს.
მიღების დრო თბილისის დროითაა; პერიოდები ერთმანეთთან დროის სარტყლით არ აირევა.

წარმატებული პასუხი cache-ში5წუთია; failure backoff60წამი, dated last-good24საათი.
Credential fingerprint/property/პერიოდი cache key-შია. Stale რეჟიმში შედარება
არ ითვლება. HTTP timeout-ები bounded; provider next URL/credentials არ ბრუნდება.
დეტალის შეცდომა ჯამს არ მალავს; ძირითადი წაკითხვის შეცდომა ნულოვან ანგარიშად
არ გარდაიქმნება. Page ბმულები მხოლოდ http(s)/flexdrive.ge-ის ოჯახიდანაა,
credentials/foreign scheme უარყოფილია. ძველი async პასუხი/გასვლა კერძო მონაცემს
ვერ აღადგენს; კომპონენტი onMounted-ზე კითხულობს, ბრაუზერში მუდმივად არ ინახავს.

## შემოწმება

-65 backend business/analytics/Meta/Search Console ტესტი disposable SQLite-ზე,
  ქსელი დაბლოკილი. ფარავს უფლებებს, date/PT/retention საზღვრებს, scope-ს,
  token redaction-ს, აგრეგაციას, URL-ებს, partial/failure/cache/stale ქცევას.
-43 frontend business analytics/report ტესტი; მათ შორის7 Search Console ტესტი:
  მაჩვენებლების განმარტებები/ცვლილებები, private requests, cancellation/logout,
  unknown/zero, ოთხი რეალური Vue template-ის კომპილაცია.
- Nuxt typecheck, scoped ESLint და production build წარმატებულია.
- live API შემოწმებულია მხოლოდ წაკითხვის მოთხოვნებით. არ გაგზავნილა tracking event,
  index/sitemap ცვლილება, რეალური შეკვეთა/გადახდა/რეკლამა. საჯარო მაღაზია არ გახსნილა.
- ახალი ეკრანების ვიზუალური desktop/mobile შეფასება რჩება deploy-ის შემდეგ;
  dev server/browser renderer არ გაშვებულა. Google admin UI გამოყენებულია მხოლოდ
  API enable/მომხმარებლის მიერ დამტკიცებული reader grant-ისთვის; JS reset შესრულდა.

ეს performance ბლოკია. სრული ინდექსაციის შეცდომები, sitemap და URL inspection
Search Console-ში რჩება; ისინი ამ API-ის performance ცხრილებით არ იგონება.

წყაროები: [Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query),
[Scopes](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing),
[Restricted user](https://support.google.com/webmasters/answer/7687615?hl=en).
