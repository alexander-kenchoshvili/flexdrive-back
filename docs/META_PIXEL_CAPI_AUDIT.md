# Pixel/CAPI მიმდინარე აუდიტი — 2026-10-10

მომხმარებელმა მოითხოვა მიმდინარე გადამოწმება. დომენზე გადასვლის სამუშაო ცალკე
რჩება: Meta-ში `flexdrive.ge`-ის დადასტურება/დომენის პარამეტრები შესრულდეს Search
Console-ის გვერდით, დომენის გადასვლისას. ამ აუდიტში დომენის/DNS/allowlist,
GTM-ის ან პროდაქშენის გარემოს ცვლილება არ შესრულებულა.

## რაც დადასტურდა

- Meta Events Manager-ში სწორია FlexDrive Web Pixel `1020718363721235`.
  ნაჩვენებ 12 სექტემბერი–9 ოქტომბრის დიაპაზონში არის PageView 92 და ViewContent
  13, browser Pixel წყაროთი; AddToCart/Purchase და server მიღება არ გამოჩნდა.
  ბოლო აქტივობა ძველია; ჩანაწერის არარსებობა კონკრეტული კოდის ბაგს არ ამტკიცებს.
- საჯაროდ ჩატვირთული Live `GTM-MVNFL9TH` რეალურად შეიცავს ამ Pixel ID-ს,
  `add_to_cart -> AddToCart`, `purchase -> Purchase` და `ecommerce.event_id`-ის
  `fbq(..., {eventID: ...})`-ად გადაცემას. GTM არ შეცვლილა/გამოქვეყნებულა.
- ფრონტის კოდი purchase ID-ს ქმნის `purchase-{order_number/public_token}` ფორმით;
  სერვერი იგივე წესს იყენებს. ონლაინ Purchase მხოლოდ paid შეკვეთისთვისაა
  განკუთვნილი; browser localStorage განმეორებითი view-ის გაგზავნას ზღუდავს.
  კოდის კონტრაქტის დამთხვევა Meta-ს რეალური deduplication-ის მტკიცებულება არ არის.
- მომხმარებლის უკვე გაშვებულ ადგილობრივ https://localhost:3000 საიტზე tracking
  თანხმობისას GTM, GA4 და fbevents სკრიპტები ჩანს. არსებული კალათა იყო ერთი
  FD-04-0669 ნივთი, 1 ცალი, 65 GEL. FD-08-0127 დაემატა ერთი ცალი, 40 GEL;
  UI-მ აჩვენა წარმატება/ორი ნივთი/105 GEL. მხოლოდ დამატებული ნივთი მოიშალა:
  კალათა კვლავ ერთი თავდაპირველი ნივთი/65 GEL არის.
- ადგილობრივი cookie არჩევანი თავდაპირველად ყველა optional კატეგორიაზე false
  იყო. მხოლოდ analytics/marketing ჩაირთო შემოწმებისთვის და შემდეგ false-ზე
  აღდგა. მომხმარებლის არსებული cart/login ან სხვა preferences არ გაწმენდილა.
- ლოკალური settings-ის მხოლოდ boolean შემოწმება: META_CAPI_ENABLED=False,
  META_PIXEL_ID მოსალოდნელ ID-ს არ ემთხვევა (არ არის კონფიგურირებული),
  META_CAPI_ACCESS_TOKEN და test code არ არის მითითებული. Credential მნიშვნელობა
  არ წაკითხულა/გამოტანილა.
- DigitalOcean production backend service settings-ის 41 და app-level settings-ის
  31 variable-name ველი read-only შემოწმდა: META_CAPI_ENABLED, META_PIXEL_ID და
  META_CAPI_ACCESS_TOKEN არც ერთში არ არის. წაკითხული იყო მხოლოდ სახელები,
  მნიშვნელობები არ გამოტანილა. BUSINESS_META_ACCESS_TOKEN service-ის ფორმაში
  ჩანს; ფორმაში არსებობა save/deploy დასრულების მტკიცებულება არ არის. Save,
  Cancel ან deploy არ დაჭერილა. მომხმარებლის გახსნილი ფორმა არ შეცვლილა.
- In-memory order/mock transport კონტრაქტის 5 შემოწმება წარმატებით შესრულდა:
  სტაბილური event ID, Purchase/GEL/value/company SKU, mock test-code გაგზავნა,
  თანხმობის უარყოფის ბლოკირება და CAPI disabled ბლოკირება. რეალური HTTP გაგზავნა
  და სამუშაო ბაზაში შეკვეთის შექმნა არ მომხდარა.
- commerce.test_internal_skus-ის 5 ტესტი წარმატებულია. commerce.tests-ის 3 ძველი
  Meta ტესტი fixture setup-ში შეწყდა `catalog_published_requires_sku` შეზღუდვით,
  თვით Meta კოდამდე; ძველი fixture-ები ამ აუდიტში არ შეცვლილა. ყველა ტესტის
  წარმატებით დასრულების მტკიცება არ შეიძლება.

## რაც ჯერ ვერ დადასტურდა

Meta Test Events-ში ადგილობრივი URL-ის Test events ღილაკი disabled დარჩა;
ხელით გაკეთებული cart მოქმედების მიღება panel-ში არ გამოჩნდა. Browser-ის
runtime/network introspection ამ browser surface-ზე ხელმისაწვდომი არ იყო.
შესაბამისად რეალური AddToCart request-ის წარმატება/Meta-მიღება **დაუდასტურებელია**,
თუნდაც ადგილობრივი UI და Live GTM კონფიგურაცია გამართული ჩანდეს.

Purchase-ის რეალური browser+server მიწოდება და deduplication ასევე დაუდასტურებელია.
ლოკალური CAPI გამორთულია; production service/app-level CAPI ცვლადებიც არ არის
მითითებული. უშუალოდ deployed process გარემო არ წაკითხულა. Reporting-ის
`BUSINESS_META_ACCESS_TOKEN` ცალკე reader-ია და CAPI-ის გასაღებად არ გამოიყენება.
რეალური ან თვითნებურად მონიშნული paid შეკვეთა არ შექმნილა. ბანკის, მომწოდებლის
ან კურიერის მოთხოვნა არ შესრულებულა. Dev server არ დაწყებულა/გაჩერებულა.

შემდეგი კოორდინირებული ნაბიჯი: CAPI კონფიგურაციის მომზადება,
საჭიროებისას მომხმარებლის მიერ არსებული CAPI credential-ის მიწოდება უშუალოდ
env-ში, Meta Test Events რეჟიმის შეთანხმება და მხოლოდ მერე შეთანხმებული
სატესტო გადახდის სცენარი. არ შევცვალოთ credentials/წესები და არ გავუშვათ რეალური
Purchase ტესტი მომხმარებელთან შეთანხმების გარეშე.

ოფიციალური საფუძველი: [Meta Pixel reference/eventID](https://developers.facebook.com/documentation/meta-pixel/reference.md),
[Meta standard event payloads](https://developers.facebook.com/documentation/meta-pixel/implementation/pixel-for-collaborative-ads.md).
