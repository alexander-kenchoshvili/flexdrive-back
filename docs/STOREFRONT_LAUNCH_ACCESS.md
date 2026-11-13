# დროებითი დაცვა და საიტის საჯარო გახსნა

2026-11-14 მომზადებულია საჯარო საინფორმაციო გამონაკლისი Google Branding-ისთვის: დახურულ რეჟიმშიც მხოლოდ `/privacy-policy` და `/terms` GET/HEAD გამოაჩენს არსებულ CMS legal ტექსტს; მთავარი მოლოდინის გვერდი აღწერს FlexDrive-ს და ორივე ბმულს აჩვენებს. Backend-ზე ზუსტად ორი slug-ის მინიმალური, სანიტიზებული projection-ია `/api/launch/information/<slug>/`. ზოგადი CMS/API და მაღაზია ისევ კოდითაა. საჭიროა მომხმარებლის ორივე source deployment (backend, შემდეგ frontend); მიგრაცია/env ცვლილება არა. Google verification submission deployment-ისა და ცოცხალი შემოწმების შემდეგ ცალკე სრულდება.

განახლებულია 2026-11-13, დაკავშირებულ backend/frontend პროექტებში. **Production-ში `pages.0085` გამოყენებულია, ორივე დაცვის flag ჩართულია, `flexdrive.ge`/`www` მიბმულია მოქმედი HTTPS-ით და `public_open=False`.**

სატესტო კოდის შექმნის განმეორებითი 403-ის მიზეზი აღმოჩნდა launch admin-ის `Referrer-Policy:no-referrer`. ჩვეულებრივი browser form POST ამ პარამეტრით აგზავნის `Origin:null`-ს და CSRF შემოწმება უარყოფს მას. იგივე header ჰქონდა frontend კოდის ფორმას. ორივეგან მომზადებულია `same-origin` შესწორება. Chromium-ის იზოლირებული HTTPS ფორმით მიზეზი დადასტურდა. 18 backend და 17 frontend ტესტი და scoped ESLint გადის. **2026-11-14 მომხმარებელმა ორივე deployment დაადასტურა. Live frontend-ის `same-origin` header და იზოლირებულ Chromium-ში ნამდვილი ფორმის POST დადასტურებულია. არასწორი კოდი აღწევს კოდის შემოწმებამდე და წვდომა უარყოფილია. 2026-11-14 მომხმარებელმა ადმინისტრაციაში კოდის შექმნა და სრული საიტის შესვლა დაადასტურა.**

საბოლოო დომენის live შემოწმება წარმატებულია. root-ზე მოლოდინისა და კოდის ფორმა 200 private/no-store/noindex-ია, API კოდის გარეშე 403-ია. `www` 308-ით გადადის root-ზე გზის შენარჩუნებით. ორივე hostname-ის სერტიფიკატი ორივე ingress IP-ზე CA/hostname შემოწმებით დადასტურებულია. frontend site URL და backend frontend URL/CORS/CSRF მნიშვნელობები შენახულია. მომხმარებელმა შექმნას სატესტო კოდი admin-ში და გამოიყენოს `https://flexdrive.ge/__preview`-ზე. სრული მაღაზიის რეალური სატესტო შესვლა მომხმარებელმა 2026-11-14 დაადასტურა. DNS/runtime ზუსტი ცვლილებები და დარჩენილი provider სამუშაო `docs/FLEXDRIVE_GE_CUTOVER_2026-11-13.md`-შია.

ორივე საწყისი deployment მომხმარებელმა შეასრულა. SSL კავშირით backup/rollback preview-ის შემდეგ გამოყენებულია მხოლოდ `pages.0085_launch_control`; ახალმა read-only კავშირმა დაადასტურა 61 თავდაპირველი ცხრილის სქემისა და მონაცემების შენარჩუნება, დახურული singleton და ნულოვანი pending migrations. დაემატა მხოლოდ ახალი ცხრილი, მიგრაციის ჩანაწერი, ერთი content type და ოთხი permission. სრული backup და შემოწმებები ignored `tmp/measurements-20261015/launch-access-20261113/production-*` არტეფაქტებშია.

DigitalOcean-ის შესაბამის კომპონენტებზე ორივე ახალი flag runtime მნიშვნელობით `true` შენახულია; ძველი 8 frontend/46 backend კომპონენტური ცვლადი უცვლელია. Live GET ადასტურებს დახურულ backend-ს, პირდაპირი API-ის 403 პასუხს და ადმინისტრაციის შესვლის გვერდის მუშაობას. Frontend `/__preview` აბრუნებს 200 ფორმას. დახურული მთავარი გვერდის აპლიკაციის 503 პასუხს DigitalOcean ingress ცვლის თავისი 504 გვერდით (`x-do-orig-status:503`). ამიტომ ადგილობრივ frontend-ში დაგეგმილი დახურული გვერდი შეიცვალა 200-ზე, `private, no-store` და `noindex, nofollow` შენარჩუნებით; რეალური სერვერის შეცდომები ისევ 503-ია. **ეს შესწორება მომხმარებელმა დაადეპლოია და live მოლოდინის გვერდი გადამოწმებულია. დომენი/HTTPS გამართულია. კოდით სრული მაღაზიის რეალური სატესტო შესვლა მომხმარებელმა 2026-11-14 დაადასტურა.**

## რას მიიღებს მფლობელი

- დაცულ რეჟიმში ჩვეულებრივი სტუმარი ხედავს „მალე გავეშვებით“ გვერდს.
- მფლობელი Django admin → Pages → **საიტის საჯარო გახსნა** გვერდზე ქმნის 24-საათიან სატესტო კოდს. საიტზე „სატესტო შესვლა“ → კოდის ჩასმა → შესვლა. ამის შემდეგ მომხმარებლის ანგარიშში შესვლა და სხვა ოპერაციები ჩვეულებრივ სრულდება.
- იმავე admin გვერდზე **„საიტის საჯაროდ გახსნა“** არის ერთი POST ღილაკი. მდგომარეობა backend ბაზიდან ყოველ მოთხოვნაზე მოწმდება; deployment ან DNS ცვლილება ამ ღილაკს არ სჭირდება.
- მფლობელს შეუძლია დაცულ რეჟიმში დაბრუნება და ყველა ძველი სატესტო კოდის გაუქმება. ცვლილება მოქმედებს მომდევნო მოთხოვნაზე; უკვე გახსნილ გვერდს განახლება სჭირდება.

Admin გვერდი: `https://api.flexdrive.ge/manager-fd/pages/launchcontrol/` (2026-11-14 ახალი backend hostname, მოქმედი HTTPS). ჩვეულებრივი admin შესვლა: `https://api.flexdrive.ge/manager-fd/`, იგივე ანგარიშით; ახალ hostname-ზე ხელახალი login საჭიროა. ძველი DigitalOcean backend hostname-იც მოქმედებს. მართვა მხოლოდ აქტიურ superuser-ს შეუძლია. GET საჯარო გახსნას ვერ ასრულებს; POST დაცულია CSRF-ით, მდგომარეობის ცვლილებები და კოდის შექმნა ფიქსირდება admin log-ში. თავად კოდი log-ში/ბაზაში არ ინახება და მხოლოდ შექმნის პასუხში ჩანს.

## როგორ მუშაობს დაცვა

- ახალი `pages.LaunchControl` singleton: `public_open=False`, კოდების ვერსია და ცვლილების დრო. იგი საჯარო CMS serializer-სა და მის ქეშში არ შედის.
- ახალი read-only endpoint: `/api/launch/status/`. აბრუნებს მხოლოდ ჩართულია თუ არა დაცვა, საჯარო გახსნის მდგომარეობასა და მოცემული preview cookie-ს დაშვებას.
- signed preview code გამოიყენება მხოლოდ `HttpOnly`, production-ში `Secure`, host-only, `SameSite=Lax` cookie-ით. URL/query-ში კოდი არ გადადის. ვადა ითვლება კოდის შექმნიდან; გაუქმება კოდების ვერსიას ცვლის.
- Nuxt middleware ყველა hostname-ზე მუშაობს, მათ შორის პირდაპირ `ondigitalocean.app`-ზეც. API backend-იც კოდს დამოუკიდებლად ამოწმებს; frontend-ის გვერდის ავლა შეზღუდვას არ ხსნის.
- API პროქსი, OAuth cookie forwarding და SSR fetch სატესტო cookie-ს ატარებს. SSR-ში მხოლოდ preview cookie ემატება და მხოლოდ კონფიგურირებულ API origin/path-ზე; გარე მისამართებს არ გადაეცემა.
- კოდის შესაყვანი POST მოითხოვს იმავე origin-ს, production-ში HTTPS-ს და მოცულობით შეზღუდულ form body-ს. არასწორი/ვადაგასული კოდი cookie-ს არ ქმნის.
- დაცულ პასუხებს აქვთ `private, no-store`; შემმოწმებლის გვერდებს დამატებით `noindex, nofollow`. API-ის streaming proxy-ს ცალკე response hook იცავს სათაურების გადაფარვისგან.
- ადმინისტრაციის არსებული ავტორიზაცია მუშაობს. ზუსტად რეგისტრირებული BOG/Wingo POST callback-ები საკუთარი არსებული გადამოწმებით მუშავდება; მთელი API prefix გამონაკლისი არ არის. სხვა endpoint-ებს ჩვეულებრივი ანგარიშის ავტორიზაცია და CSRF ისევ სჭირდება.
- ბაზის/სტატუსის endpoint-ის შეცდომა, დაკარგული control row ან frontend/backend დაცვის შეუსაბამობა წვდომას კეტავს. Nuxt სტატუსის მოთხოვნა 4 წამით არის შეზღუდული. typo backend flag-ში კონფიგურაციის შეცდომაა; frontend flag-ის უცნობი მნიშვნელობა დაცვას ვერ თიშავს.

## deployment და გააქტიურების რიგი

1. მომხმარებელი push/deploy-ს აკეთებს ორივე პროექტში. თავდაპირველად ორივე ახალი guard flag გამორთულია; მიმდინარე საიტი ჩვეულებრივ მუშაობს. Domain DNS-ის ვებ ჩანაწერები ჯერ არ იცვლება.
2. backend deployment-ის დადასტურების შემდეგ, production DB-ის იდენტობის/backup/pending migrations შემოწმებით ცალკე გამოიყენება **მხოლოდ `pages.0085_launch_control`**. ის ქმნის ერთ ახალ ცხრილს/დახურულ row-ს და ჩვეულებრივ content type/permissions-ს; მოქმედი ბიზნეს ცხრილების შეცვლას არ ითხოვს. **Production-ში შესრულებულია 2026-11-13; local ბიზნეს ბაზაში არ გამოყენებულა.**
3. frontend კომპონენტზე განთავსდეს `NUXT_STOREFRONT_ACCESS_GUARD_ENABLED=true` runtime ცვლადი და დაელოდეთ deployment-ს. სანამ backend-ის დაცვა ჩაირთვება, frontend განზრახ მიუწვდომლობის გვერდს აჩვენებს.
4. backend-ზე ჩაირთოს `STOREFRONT_ACCESS_GUARD_ENABLED=true` და დაელოდეთ deployment-ს. `/api/launch/status/` უნდა აჩვენებდეს `guard_enabled:true`, `public_open:false`. პირდაპირი catalog/checkout API შემმოწმებლის cookie-ს გარეშე უნდა უარყოს მოთხოვნა.
5. admin-ში შექმენით preview code; დროებით frontend hostname-ზე დახურული/სატესტო შესვლა და private/no-store პასუხები გადაამოწმეთ. ინკოგნიტო სტუმარს მაღაზია არ უნდა გამოუჩნდეს. ჯანმრთელობის HTTP probe-ის არსებობისას იგი read-only `/api/launch/status/`-ზე მოარგეთ; TCP probe-ს ცვლილება არ სჭირდება.
6. მხოლოდ ამ შემოწმებების შემდეგ მიაბით საბოლოო დომენები/DNS/TLS. შეცვალეთ საბოლოო site URL/origins/OAuth/reCAPTCHA/გადახდის ბმულები და გაატარეთ დარჩენილი cutover checklist. ახალ hostname-ზე შემმოწმებელს ხელახლა შეაქვს კოდი, რადგან cookie host-only არის.
7. საჯარო გახსნის დროს მფლობელი აჭერს admin-ის გახსნის ღილაკს. ინკოგნიტოდ გადაამოწმეთ storefront/API. SEO ინდექსაციის საერთო და გვერდის flags კვლავ თავდაპირველი D11 გეგმით იმართება; საჯაროდ გახსნა მათ ავტომატურად არ ცვლის.

გარემოს ცვლადები წვდომის დაცვის *მექანიზმს* რთავს; საბოლოო საჯარო გახსნას ბაზის ღილაკი მართავს. საბოლოო დომენზე გადართვამდე ორივე ფენის მოქმედება უნდა შემოწმდეს.

## შემოწმება

Production ingress-ისთვის 200-პასუხიანი შესწორების შემდეგ ხელახლა წარმატებით გავიდა 17 frontend ტესტი, scoped ESLint, Nuxt typecheck, production build და აწყობილი Nitro smoke. ამ შემოწმებებში დაგეგმილი დახურული გვერდი 200-ია, API უარყოფილია, კოდი/გახსნა/დახურვა მუშაობს და რეალური სერვერის შეცდომა წვდომას ისევ კეტავს. Live შედეგი frontend-ის ახალი deployment-ის შემდეგ უნდა დადასტურდეს.

Backend-ის disposable SQLite runner ბლოკავს outbound ქსელს და არ ეხება სამუშაო ბაზას:

```powershell
venv\Scripts\python.exe _qa/run_launch_access_tests.py
venv\Scripts\python.exe _qa/run_launch_access_tests.py commerce.test_bog_callback_flow
venv\Scripts\python.exe _qa/run_launch_access_tests.py --check-migrations
```

BOG suite ცალკე პროცესში გადის მისი არსებული `serialized_rollback` fixture-ის გამო. პირველი ფართო გაშვებისას ჩვეულებრივი Wingo runner-ის production throttle-ებმა ორი accounts ტესტი შეზღუდა; dedicated runner პროექტის `TESTING` რეჟიმს სწორად აყენებს. ეს runner-ის საკითხები აპლიკაციის ქცევის შესაცვლელად არ გამოყენებულა.

Frontend: `node --test tests/storefrontAccess.test.mjs tests/canonicalDomain.test.mjs`, Nuxt typecheck, scoped ESLint და production build. HTTP ტესტები ამოწმებს რეალურ H3 handler/proxy-ს მხოლოდ loopback სერვერებით: სხეულის ლიმიტს, cookie-ს, API-ს, cache headers-ს, პირდაპირ hostname-ებსა და გახსნა/დახურვას. საბოლოო დომენის/provider-სერვისების live შემოწმება deployment-ის შემდეგ სრულდება.

საბოლოო შემოწმებებში გავიდა 221 backend ტესტი ორ იზოლირებულ გაშვებაში და 17 frontend ტესტი. ტიპების შემოწმება, scoped ESLint, მიგრაციის შესაბამისობა და production build წარმატებით დასრულდა. აწყობილი Nitro აპის loopback გაშვებამაც დაადასტურა ორი hostname-ის დაცვა, Secure/HttpOnly cookie, რეალური API პროქსის no-store პასუხი, გახსნა/დახურვა და სერვერის მიუწვდომლობისას წვდომის შეზღუდვა. სატესტო პროცესები დასრულებულია. შედეგი შენახულია `tmp/measurements-20261015/launch-access-20261113/built-front-smoke-result.json`-ში.
