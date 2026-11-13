# დროებითი დაცვა და საიტის საჯარო გახსნა

მომზადებულია 2026-11-13, დაკავშირებულ backend/frontend პროექტებში. **კოდი მზადდება ცალკე გააქტიურებისთვის; production-ში დაცვა ჯერ ჩართული არ არის.**

## რას მიიღებს მფლობელი

- დაცულ რეჟიმში ჩვეულებრივი სტუმარი ხედავს „მალე გავეშვებით“ გვერდს.
- მფლობელი Django admin → Pages → **საიტის საჯარო გახსნა** გვერდზე ქმნის 24-საათიან სატესტო კოდს. საიტზე „სატესტო შესვლა“ → კოდის ჩასმა → შესვლა. ამის შემდეგ მომხმარებლის ანგარიშში შესვლა და სხვა ოპერაციები ჩვეულებრივ სრულდება.
- იმავე admin გვერდზე **„საიტის საჯაროდ გახსნა“** არის ერთი POST ღილაკი. მდგომარეობა backend ბაზიდან ყოველ მოთხოვნაზე მოწმდება; deployment ან DNS ცვლილება ამ ღილაკს არ სჭირდება.
- მფლობელს შეუძლია დაცულ რეჟიმში დაბრუნება და ყველა ძველი სატესტო კოდის გაუქმება. ცვლილება მოქმედებს მომდევნო მოთხოვნაზე; უკვე გახსნილ გვერდს განახლება სჭირდება.

Admin გვერდი: `/manager-fd/pages/launchcontrol/`. მართვა მხოლოდ აქტიურ superuser-ს შეუძლია. GET საჯარო გახსნას ვერ ასრულებს; POST დაცულია CSRF-ით, მდგომარეობის ცვლილებები და კოდის შექმნა ფიქსირდება admin log-ში. თავად კოდი log-ში/ბაზაში არ ინახება და მხოლოდ შექმნის პასუხში ჩანს.

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
2. backend deployment-ის დადასტურების შემდეგ, production DB-ის იდენტობის/backup/pending migrations შემოწმებით ცალკე გამოიყენება **მხოლოდ `pages.0085_launch_control`**. ის ქმნის ერთ ახალ ცხრილს/დახურულ row-ს და ჩვეულებრივ content type/permissions-ს; მოქმედი ბიზნეს ცხრილების შეცვლას არ ითხოვს. ეს მიგრაცია ამ მომზადებისას არც local ბიზნეს ბაზაში და არც production-ში არ გამოყენებულა.
3. frontend კომპონენტზე განთავსდეს `NUXT_STOREFRONT_ACCESS_GUARD_ENABLED=true` runtime ცვლადი და დაელოდეთ deployment-ს. სანამ backend-ის დაცვა ჩაირთვება, frontend განზრახ მიუწვდომლობის გვერდს აჩვენებს.
4. backend-ზე ჩაირთოს `STOREFRONT_ACCESS_GUARD_ENABLED=true` და დაელოდეთ deployment-ს. `/api/launch/status/` უნდა აჩვენებდეს `guard_enabled:true`, `public_open:false`. პირდაპირი catalog/checkout API შემმოწმებლის cookie-ს გარეშე უნდა უარყოს მოთხოვნა.
5. admin-ში შექმენით preview code; დროებით frontend hostname-ზე დახურული/სატესტო შესვლა და private/no-store პასუხები გადაამოწმეთ. ინკოგნიტო სტუმარს მაღაზია არ უნდა გამოუჩნდეს. ჯანმრთელობის HTTP probe-ის არსებობისას იგი read-only `/api/launch/status/`-ზე მოარგეთ; TCP probe-ს ცვლილება არ სჭირდება.
6. მხოლოდ ამ შემოწმებების შემდეგ მიაბით საბოლოო დომენები/DNS/TLS. შეცვალეთ საბოლოო site URL/origins/OAuth/reCAPTCHA/გადახდის ბმულები და გაატარეთ დარჩენილი cutover checklist. ახალ hostname-ზე შემმოწმებელს ხელახლა შეაქვს კოდი, რადგან cookie host-only არის.
7. საჯარო გახსნის დროს მფლობელი აჭერს admin-ის გახსნის ღილაკს. ინკოგნიტოდ გადაამოწმეთ storefront/API. SEO ინდექსაციის საერთო და გვერდის flags კვლავ თავდაპირველი D11 გეგმით იმართება; საჯაროდ გახსნა მათ ავტომატურად არ ცვლის.

გარემოს ცვლადები წვდომის დაცვის *მექანიზმს* რთავს; საბოლოო საჯარო გახსნას ბაზის ღილაკი მართავს. საბოლოო დომენზე გადართვამდე ორივე ფენის მოქმედება უნდა შემოწმდეს.

## შემოწმება

Backend-ის disposable SQLite runner ბლოკავს outbound ქსელს და არ ეხება სამუშაო ბაზას:

```powershell
venv\Scripts\python.exe _qa/run_launch_access_tests.py
venv\Scripts\python.exe _qa/run_launch_access_tests.py commerce.test_bog_callback_flow
venv\Scripts\python.exe _qa/run_launch_access_tests.py --check-migrations
```

BOG suite ცალკე პროცესში გადის მისი არსებული `serialized_rollback` fixture-ის გამო. პირველი ფართო გაშვებისას ჩვეულებრივი Wingo runner-ის production throttle-ებმა ორი accounts ტესტი შეზღუდა; dedicated runner პროექტის `TESTING` რეჟიმს სწორად აყენებს. ეს runner-ის საკითხები აპლიკაციის ქცევის შესაცვლელად არ გამოყენებულა.

Frontend: `node --test tests/storefrontAccess.test.mjs tests/canonicalDomain.test.mjs`, Nuxt typecheck, scoped ESLint და production build. HTTP ტესტები ამოწმებს რეალურ H3 handler/proxy-ს მხოლოდ loopback სერვერებით: სხეულის ლიმიტს, cookie-ს, API-ს, cache headers-ს, პირდაპირ hostname-ებსა და გახსნა/დახურვას. საბოლოო დომენის/provider-სერვისების live შემოწმება deployment-ის შემდეგ სრულდება.

საბოლოო შემოწმებებში გავიდა 221 backend ტესტი ორ იზოლირებულ გაშვებაში და 17 frontend ტესტი. ტიპების შემოწმება, scoped ESLint, მიგრაციის შესაბამისობა და production build წარმატებით დასრულდა. აწყობილი Nitro აპის loopback გაშვებამაც დაადასტურა ორი hostname-ის დაცვა, Secure/HttpOnly cookie, რეალური API პროქსის no-store პასუხი, გახსნა/დახურვა და სერვერის მიუწვდომლობისას წვდომის შეზღუდვა. სატესტო პროცესები დასრულებულია. შედეგი შენახულია `tmp/measurements-20261015/launch-access-20261113/built-front-smoke-result.json`-ში.
