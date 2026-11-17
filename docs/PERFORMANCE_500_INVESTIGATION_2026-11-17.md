# PageSpeed-ის პერიოდული 500 — 2026-11-17

## საბოლოო პროდაქშენშემოწმება — შესწორება გამოქვეყნებულია

მომხმარებლისfrontendcommit`546a48a`დეპლოიDigitalOcean-შიHealthy/Liveა
18:22:09Tbilisi. ახალი18:24/18:26PageSpeedტესტები ორივერეჟიმში სრულგვერდებს
იღებს; არცHTTPerrorauditდაარცconsoleerrorauditაღარარის. RuntimeLogs-ის
`public_page_failure`ფილტრიაჩვენებსNoresults. ჩვეულებრივიroot/catalog/product
GETებიმაქსიმუმ2პარალელურობითსამივე200; არიყოload/stressტესტი.

| გვერდი | mobileქულა | desktopქულა | mobileLCP | desktopLCP | SEO |
| --- | --- | --- | --- | --- | --- |
| მთავარი |89|96|3.602s|1.002s|100ორივე|
| კატალოგი |88|87|3.189s|0.834s|100ორივე|

მთავარიTBTmobile41ms/desktop33ms, CLS0.016/0.011; კატალოგიTBT41/250ms,
CLS0.002/0.015, SpeedIndexmobile6.048s. მობილურისLCPდაdesktopკატალოგისTBT
ოპტიმიზაციისკანდიდატებია; ესარისცალკელაბორატორიულიგაზომვა, არაCrUX28დღიანი
შეფასება ან ქულისმომავალშიუცვლელობისგარანტია. რეალურივიზიტორებისCrUXსაკმარისი
მონაცემებიჯერარარის. ცალკეულიCMS404დაh3statusMessagewarningsლოგებშირჩება;
„ყველაგაფრთხილებაგაქრა“არაცხადდება. ამგაფრთხილებებზესკოპიარ გაგვიფართოებია.

ამკონკრეტულიSEO/Pinia500-ისშესწორებაგამოქვეყნებულიადაგადამოწმებულია.
შემდგომიდეპლოი/მიგრაცია/ENVამშემოწმებისშედეგადარსჭირდება.
NativeChromeCUAგათიშულია; ახალიsourcefunctionalცვლილებაარშესრულებულა.

ახალიანგარიშები: [მთავარი](https://pagespeed.web.dev/analysis/https-flexdrive-ge/ylgfk21n1d?form_factor=mobile),
[კატალოგი](https://pagespeed.web.dev/analysis/https-flexdrive-ge-catalog/zqutirnyzs?form_factor=mobile).
ქვემოთშესწორებისმომზადების/პირველიდიაგნოსტიკისჩანაწერებიისტორიულია.

## განახლება — მიზეზი გამეორებულია და შესწორება მომზადებულია

მომხმარებელმა17:46Tbilisiდეპლოი გააკეთა.17:50:13PageSpeedrootახალტესტში
mobile/desktopრეალურად500დაბრუნდა; მაღალი89/98speedქულები errorpage-სეკუთვნის.
13:50:29UTCfrontendRuntimeLogs-შიახალმადიაგნოსტიკამმიიღო:

`public_page_failure`, route=home, TypeError, hint=missing_value,
server.mjs3168:29 →3229:3. APIstack2544 დაSEOpluginchain წარმოებისასლთან
შესადარებლადგამოვიყენეთ.შეცდომისადგილიარის`useSeoDefaults`-ისახალი
`useSiteSettings()`მოძებნა`await fetchSiteSettings()`-ისშემდეგ.

ნამდვილიPinia3.0.4productionSDK-ით ტესტმა გამეორა ზუსტად
`Cannot read properties of undefined (reading '_s')`: settingsAPIკითხვისას
activePiniaკონტექსტისდაკარგვა; ასევეორიSSRმოთხოვნისერთმანეთისგავლენა.
ორივერეგრესია ძველკოდზეარასწორადმუშაობდა დაახალზეწარმატებულია.

შესწორება: SEOpluginსაწყისშივეიყენებს`useSiteSettings(nuxtApp.$pinia as Pinia)`;
შენახულიrequest-ownedstoreგადაეცემაგადმოწერილიმონაცემებისშემდეგ
`useSeoDefaults(siteSettingsStore)`-ს. composableაღარეძებსglobalactivePinia-ს.
SEOველი/canonical/robots/ინდექსაციისპოლიტიკაარიცვლება; ფინანსები/ავტორიზაცია
არამოდიფიცირებულა. დიაგნოსტიკარჩება.

26SEO/error/diagnosticტესტი, scopedESLint, typecheckდაproductionბილდიწარმატებულია.
ActualbuiltNuxt+loopbackAPIში settingsპასუხისმოსვლისასგანზრახგასუფთავდაactivePinia;
root/catalogორი პარალელურიმოთხოვნაორივეHTTP200/სწორიშიგთავსით/SEO-თიდაბრუნდა,
დიაგნოსტიკურიშეცდომაარასდროსგამოჩნდა. QAგაჩერებულია.
**საჭიროაახალიფრონტისდეპლოი**;
ესშესწორებაპროდაქშენზეჯერარარის. ბექი/მიგრაცია/ENVცვლილებაარ სჭირდება.
ქვემოთ„მიზეზიუნახავია“ჩანაწერებიისტორიულისაფეხურებია დაარაახლანდელისტატუსი.

## დადასტურებული მდგომარეობა

17ნოემბერი14:43/14:48Tbilisi ტესტებში მობილური სრული გვერდი იყო, desktop-ზე კი
რეალური HTTP500/ჩვენი Nuxt error page. შეცდომის გვერდის მაღალი performance
ქულები ნამდვილი გვერდის სიჩქარედ არ უნდა ჩაითვალოს.

| ტესტი | მთავარი mobile | კატალოგი mobile | Desktop |
| --- | --- | --- | --- |
| პირველი |85, LCP3.976s, TBT58ms, CLS0.016|88, LCP3.376s, TBT43ms, CLS0.001|ორივე500; ქულა უვარგისია|
| ახალი, კოდის შეუცვლელად |83, SEO100|91, SEO100|მთავარი96/SEO100; კატალოგი97/SEO100|

- ახალი მთავარი15:12:13Tbilisi: desktop FCP0.371s, LCP1.083s, TBT110ms,
  CLS0.031, SpeedIndex1.368s. BestPractices100. სრულგვერდიანი ნორმალური შედეგი.
- ახალი კატალოგი15:14:38Tbilisi: desktop FCP0.310s, LCP0.661s, TBT16ms,
  CLS0.007, SpeedIndex1.679s. BestPractices100. 500აღარ ჩანს.
- PageSpeed არ აჩვენებს საკმარისCrUXმონაცემებს; ეს ლაბორატორიული გაზომვებია,
  არა ყველა მომხმარებლის რეალური28დღიანი შეფასება.
- მთავარი mobileLCPელემენტი heroსურათია: eager/highpriority უკვე აქვს.
  გამოქვეყნებულ ანგარიშში resource load delay1.67s; render-blocking შეფასება590ms.
  ამიტომ მხოლოდ„დაამატეfetchpriority“დასკვნა მცდარი იქნებოდა.
- პირველი კატალოგის desktop console audit მხოლოდ დოკუმენტისHTTP500-ს ასახელებს;
  შეტყობინებაში JavaScript/SSRმიზეზის stack არ არის.
- ცალკე ანონიმურიGETები root/catalog/product200; ChromeDesktop, HeadlessChrome,
  ChromeMobile და Chrome-Lighthouseსუფიქსი200. ძირითადი HTMLbrკომპრესირებულია.
  არ ყოფილა დატვირთვის/stressტესტი, ყიდვა/ჩარიცხვა/ბაზის ცვლილება.
- გახსნილfrontendRuntimeLogs-ში10:48UTCh3statusMessageგაფრთხილებები და11:01UTC
  CMS404ები ჩანდა. ეს ნიმუში არ ადგენს PageSpeed500-ის მიზეზს. არ ვაცხადებთ,
  რომ500იყო აუცილებლადrobots/noindex/ქეშის/თროთლინგის/აგენტის პრობლემა.
- ოფიციალური საჯარო PageSpeedAPIერთხელ ვცადეთ დამატებითიJSONისთვის;429
  RESOURCE_EXHAUSTED. გასაღები/API/გეგმა/წვდომა არ შეგვიქმნია ან შეგვიცვლია.

## მიზნობრივი ცვლილება — დიაგნოსტიკა, არა დაუდგენელი მიზეზის გამოსწორება

ფრონტში დამატებულია server-onlyNuxt`app:error`pre-plugin და Nitro`error`hook.
ორივე იყენებს ერთhelper-ს და იმავეrequest-ზე მხოლოდერთჩანაწერს წერს:
`event: public_page_failure`. ჩანაწერი შეიცავს მხოლოდhome/catalog/productკლასს,
დაშვებულerrorტიპს/status/code-ს და გენერირებულიserverკოდისფაილის/ხაზისადგილს,
მაქსიმუმ3cause/4location-ით. Rawmessage/URL/query/header/cookie/body/stack არ იბეჭდება.
პირადი/API/writeმარშრუტები და4xx არ იწერება. ზღვარი20ჩანაწერი/წუთი/პროცესი,
requestdedup; ლოგერის/არასწორიობიექტის ხარვეზი პასუხს არ ცვლის.

არ დამატებულაendpoint/service/cron/ENV/DBmigration/ფინანსურიოპერაცია. წინა
ბიზნესანალიტიკის დაუფუშავი ცვლილებები შენარჩუნებულია. მომხმარებელი აკეთებს
push/deploy-ს. მხოლოდამის შემდეგ ჩაირთვება ახალი დიაგნოსტიკა პროდაქშენზე.

## ვალიდაცია დასრულებულია

-5მიზნობრივიტესტი: redact/cause/status/location, პირადიმარშრუტებისდაცვა,
  requestdedup/20წუთობრივიზღვარი, cyclic/getter/loggerხარვეზებისუსაფრთხოება,
  ნამდვილიplugincallback-ებისრეგისტრაცია. ScopedESLint/strictTypeScript/buildწარმატებულია.
- ActualbuiltNuxtserver + loopbackფიქსტურა500: GETroot/catalogორივესHTTP500
  შეუნარჩუნდა; მიიღეთ ზუსტად2`public_page_failure`ჩანაწერი, buildფაილის/ხაზის
  ადგილებით დაcauseსტატუსებით. დიაგნოსტიკაში არცprivateსატესტონიშანი დაარც
  upstreamURLგაჟონილა; ფიქსტურისprivateნიშანი არცHTMLპასუხშიგამოჩნდა.
  ეს ადასტურებსდიაგნოსტიკისმუშაობას, **არა ძველიproduction500-ისმიზეზს**.
- QAპორტები3107/8128გაჩერებულია; nativeChromeCUAგათიშულია. პროდაქშენზე
  source/deploy/configმუტაციაარ შესრულებულა. ბილდში არსებულიNodeDEP0155warningრჩება.

**დარჩა:** frontendდეპლოი; PageSpeedხელახალიგაშვება; თუ500განმეორდება,
RuntimeLogs-ში`public_page_failure`ჩანაწერისმიხედვით ზუსტი მიზეზისგამოსწორება.
თუ არ განმეორდა, მიზეზი დაუდგენელად რჩება; შემთხვევა სრულად მოგვარებულად არ მოინიშნება.

ანგარიშები:

- [პირველი მთავარი](https://pagespeed.web.dev/analysis/https-flexdrive-ge/pfupcop2xc?form_factor=desktop)
- [პირველი კატალოგი](https://pagespeed.web.dev/analysis/https-flexdrive-ge-catalog/sjvzpucwmr?form_factor=desktop)
- [ახალი მთავარი](https://pagespeed.web.dev/analysis/https-flexdrive-ge/rcgz3iots8?form_factor=desktop)
- [ახალი კატალოგი](https://pagespeed.web.dev/analysis/https-flexdrive-ge-catalog/6mb78eaibz?form_factor=desktop)

საფუძველი: [Nuxt4errorhooks](https://nuxt.com/docs/4.x/getting-started/error-handling),
[PageSpeedfield/labგაზომვები](https://developers.google.com/speed/docs/insights/v5/about).
