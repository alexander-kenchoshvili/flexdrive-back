# FlexDrive — კონტექსტი შემდეგი ასისტენტისთვის

განახლებულია: 2026-09-20.

ეს ფაილი შეგიძლია მთლიანად გადასცე ChatGPT-ს ან სხვა ასისტენტს. იგი აჯამებს შეთანხმებულ გადაწყვეტილებებს და მიმდინარე მდგომარეობას. ეს არის კონტექსტის გადაცემა და არა ნებართვა რესურსების შეძენაზე, production მონაცემების შეცვლაზე ან საიტის საჯაროდ გახსნაზე.

## მომხმარებელი და მუშაობის წესი

მომხმარებელი პირველად ათავსებს საიტს production-ზე. აუხსენი ქართულად, მარტივად და თითო ნაბიჯად. არ დააყარო ერთდროულად ბევრი არჩევანი ან ტექნიკური ტერმინი. კონკრეტულ ნაბიჯზე მიუთითე სად შევიდეს, რა აირჩიოს და რა ეღირება. ფასები და შეზღუდვები გადაამოწმე მოქმედ ოფიციალურ დოკუმენტაციაში; ვარაუდი ფაქტად არ წარმოადგინო.

მომხმარებელს უნდა დაბალი ხარჯი, სისწრაფე, უსაფრთხოება და მარტივი მართვა. არ აქვს Docker/WSL და მათი ადგილობრივად დაყენება არ სურს. Windows-ზე მუშაობს. არსებული dev სერვერები თვითნებურად ხელახლა არ გაუშვა. არ გაუშვა ზედმეტი build/test/browser შემოწმებები დოკუმენტური ცვლილებისთვის. კოდის ცვლილებისას გამოიყენე რისკის შესაბამისი შემოწმება და შეინარჩუნე მოქმედი ecommerce ლოგიკა.

არ შეცვალო `.env` ან საიდუმლო პარამეტრები თვითნებურად. პაროლები, ბანკის/API გასაღებები და DB connection string-ები ჩატში/დოკუმენტში არ გაიმეორო. ეს ფაილი secrets-ს არ შეიცავს.

## პროდუქტი და რეალური ვადები

FlexDrive არის ავტონაწილების ონლაინ მაღაზია, დომენით `flexdrive.ge`.

მომხმარებელი რეალურ გაყიდვებს დაახლოებით 2–3 კვირაში გეგმავს. ამ პერიოდში ამთავრებს სურათებს, კატეგორიებსა და დარჩენილ ინტეგრაციებს. სურს production გარემოს მომზადება ახლა, მაგრამ საიტი ჯერ მხოლოდ თვითონ უნდა ნახოს. დახურული deployment და საჯარო გაყიდვების გახსნა ორი სხვადასხვა ეტაპია.

არსებული staging უნდა დარჩეს დამოუკიდებელ სატესტო გარემოდ. მოქმედი frontend/backend, ანგარიშები, კალათა, wishlist, checkout, Django admin, reCAPTCHA და media ფუნქციები არ უნდა დაზიანდეს.

## პროექტის ფაილები და წყაროები

- Backend: `C:\Users\kench\Desktop\flexdriveback`
- Frontend: `C:\Users\kench\Desktop\flexdrivefront`
- სრული განახლებული გზამკვლევი: `C:\Users\kench\Desktop\flexdrivefront\PRODUCTION_DEPLOYMENT_GUIDE_KA.md`
- ეს მოკლე გადასაცემი კონტექსტი: `C:\Users\kench\Desktop\flexdriveback\docs\PRODUCTION_HANDOFF_KA.md`
- ორივე repository-ს `AGENTS.md` წაიკითხე ცვლილებამდე; ძველ ისტორიულ ჩანაწერებზე უპირატესობა აქვს ახალ მომხმარებლის გადაწყვეტილებებსა და მიმდინარე კოდს.
- Backend ბრძანებებისთვის გამოიყენე მისი venv: `C:\Users\kench\Desktop\flexdriveback\venv\Scripts\python.exe`, სამუშაო დირექტორია backend. ჯერ system Python არ გამოიყენო.

სრული გზამკვლევი 2026-09-20-ზე განახლდა და სტრუქტურა/`git diff --check` შემოწმდა. ბოლო დავალებაში შეიცვალა მხოლოდ ეს Markdown; არც კოდი, არც ბაზები, არც ინფრასტრუქტურა. გზამკვლევის ცვლილება არ დაფუშულა ამ დავალების ფარგლებში. შემდეგმა ასისტენტმა git status თავიდან უნდა შეამოწმოს.

თუ ფაილებთან წვდომა არ გაქვს, თქვი ეს პირდაპირ. კოდი შემოწმებულად არ გამოაცხადო. მომხმარებელს კონკრეტული საჭირო ფაილი/ამონარიდი სთხოვე მხოლოდ შესაბამის ნაბიჯზე.

## რა არის უკვე გაკეთებული DigitalOcean-ში

- ანგარიში შექმნილია.
- საბანკო ბარათი დამატებულია.
- პროექტი `FLEXDRIVE Production` შექმნილია.
- მომხმარებელი PostgreSQL-ის შექმნის ფორმამდე მივიდა, მაგრამ **Create Database Cluster-ს არ დააჭირა**.
- ბოლო დადასტურებული მდგომარეობით ამ გეგმის ფასიანი production რესურსები ჯერ არ შექმნილა.
- დომენი და კომპანიის ელფოსტა უკვე ნაყიდია. DNS/ელფოსტის ჰოსტინგის რეალური ჩანაწერები ჯერ დასაინვენტარებელია; მათი უცვლელად მუშაობა აუცილებელია.

ანგარიში ან პროექტი თავიდან არ შექმნა. ჯერ dashboard-ის მიმდინარე მდგომარეობა გადაამოწმე, თუ მომხმარებელმა შუალედში რამე შეცვალა.

## შეთანხმებული hosting სქემა

Frontend და backend რჩება **DigitalOcean App Platform-ზე**. ბაზა და Redis-თავსებადი cache იქნება DigitalOcean-ის მართვადი მომსახურებები. მომწოდებლის API-ზე წვდომისთვის ვიყენებთ **პატარა Proxy Droplet-ს**.

| ნაწილი | საწყისი ზომა | ფასი თვეში, 2026-09-20-ზე |
|---|---|---:|
| Nuxt frontend — App Platform | 512 MiB / 1 shared vCPU | $5 |
| Django backend — App Platform | 1 GiB / 1 shared vCPU, fixed გეგმა | $10 |
| Managed PostgreSQL Standard/Basic/Regular | 1 GiB RAM / 10 GiB storage | $15.15 |
| Managed Valkey | 1 GiB | $15 |
| Proxy Droplet Basic Regular | 512 MiB | $4 |
| **ფიქსირებული ჯამი** | | **$49.15** |

ეს არის ეკონომიური დახურული deployment-ის საწყისი არჩევანი; რესურსების საკმარისობა ჯერ production დატვირთვით არ გაზომილა. Frontend-ის 1 GiB-მდე გაზრდისას ფიქსირებული ჯამია $54.15. მხოლოდ backend-ის 2 GiB-მდე გაზრდისას $64.15; ორივეს გაზრდისას $69.15.

Job-ების მოხმარება, გადასახადები, კონვერტაცია, ლიმიტების გადაჭარბება, დომენი/კომპანიის ელფოსტა და ბანკის/კურიერის საკომისიოები ცალკეა. Billing alert hard spending cap არ არის. რესურსის შექმნიდან თანხა ირიცხება მაშინაც, როცა storefront დახურულია.

საწყისად სრული კონფიგურაციის 2–3 კვირა დაახლოებით $25–37 ფიქსირებულ ხარჯს ნიშნავს, პროპორციული ბილინგის წესებით, დამატებითი მოხმარების გარეშე. ამიტომ რესურსები იქმნება ეტაპობრივად, როდესაც მათ გამართვასაც ვიწყებთ.

არ შეიძინო ძველი გეგმის $25-იანი Dedicated Egress დამატება. არ გადავიტანოთ მთელი საიტი Droplet-ზე. Spaces, Kubernetes, Load Balancer, ფასიანი Cloudflare/Cloudinary/Brevo და ცალკე მუდმივი worker წინასწარ არ გვჭირდება.

## რატომ გვჭირდება Proxy Droplet

მომწოდებელს თავისი API AWS-ზე აქვს და წვდომას წყაროს IP-ით ზღუდავს. მომხმარებლის dev IP და Render staging-ის საერთო გამავალი დიაპაზონები უკვე დაშვებულია.

Render იძლევა საერთო outbound დიაპაზონებს. DigitalOcean App Platform-ზე იგივე ტიპის უფასო გარანტირებული allowlist დიაპაზონი ოფიციალურად ვერ დადასტურდა; მათი მზა Dedicated Egress $25/თვეა. მომხმარებელს ექსკლუზიური IP მომსახურება არ სჭირდება და ამ დამატებით ფასს თავს არიდებს.

არჩეული გზა:

```text
Django / Supplier Job (App Platform)
             ↓ კერძო VPC
Proxy Droplet → HTTPS → Supplier API
             ↑ პასუხიც პროქსით ბრუნდება
```

- Proxy მხოლოდ მოთხოვნას/პასუხს ატარებს. პროდუქტის დამუშავება და DB-ში bulk ჩაწერა App Platform-ის Job-ზეა.
- Supplier Job-ს ცალკე, საწყისად 2 GiB რესურსი შეიძლება მივცეთ; ეს მუდმივ backend-ს 2 GiB-ს არ აიძულებს.
- ბანკი/კურიერი/ყველა სხვა მოთხოვნა გლობალური proxy-ით ბრმად არ გავატაროთ. Supplier-only კონფიგურაცია ჯერ გასაკეთებელია.
- არჩეული მიმართულებაა Frankfurt: App `fra`, Droplet და ბაზები შესაბამის `fra1` VPC-ში. რეალური ქსელის/ზომის ხელმისაწვდომობა provisioning-ისას მოწმდება.
- App VPC და $25 Dedicated Egress ერთად ვერ ირთვება. ჩვენს proxy გზას Dedicated Egress არ სჭირდება; DB/Valkey-ს private TLS კავშირი და trusted sources უნდა მოეწყოს.
- Proxy უნდა იყოს მხოლოდ ჩვენი VPC წყაროებისთვის და მხოლოდ Supplier-ის საჭირო მისამართებისთვის გახსნილი. არ იყოს საჯარო open proxy. HTTPS შემოწმება, timeout, streaming, log rotation, updates, SSH key და automatic restart აუცილებელია.
- Supplier-ს მიეწოდება რეალურად გაზომილი გამავალი IPv4, საჭიროებისას `/32` ფორმით. `/3` არასწორია ერთი მისამართისთვის.
- ჩვეულებრივი Droplet IPv4 შეიძლება გამოვიყენოთ. Reserved IP აუცილებელი არაა; თუ ვირჩევთ, მხოლოდ მისი მიბმა outbound IP-ს არ ცვლის — routing ცალკე კონფიგურირდება. მიმაგრებული უფასოა, მიუმაგრებელი ფასიანი.
- Droplet-ის მოვლა ჩვენზეა. მისი გათიშვა supplier sync-ს აჩერებს; საჭიროა last-success freshness alert და მოძველებული მარაგით გაყიდვის ოპერაციული წესი.

## პერიოდული დავალებები

### 1. მომწოდებელი — ყოველ ორ საათში

არსებობს bulk importer. დაგეგმილი schedule: `5 */2 * * *`, timezone `Asia/Tbilisi`.

Deployment Linux გარემოს dry-run:

```bash
python manage.py import_crossmotors_products --page-size 1000 --sample-size 0 --bulk
```

მხოლოდ მზადყოფნის შემდეგ ჩაწერის ვერსიას ემატება `--commit`. საწყისად `--archive-missing` არ გამოიყენება. რეალური API sync თვითნებურად არ გაუშვა.

აუცილებელი მომხმარებლის მოთხოვნა:

- არსებული პროდუქტების ფასები/მარაგები ავტომატურად განახლდეს.
- ახალი SKU დაემატოს **გამოუქვეყნებლად** და admin-ში ადვილად გამოჩნდეს.
- მფლობელმა თავად დაუმატოს სურათი, მიუთითოს კატეგორია და გამოაქვეყნოს.
- მომდევნო sync-მა draft არ გამოაქვეყნოს და ხელით შერჩეული კატეგორია/სურათები არ გადაწეროს.

**ეს draft ლოგიკა ჯერ დასრულებული არაა:** კოდის დათვალიერებით importer უპირობოდ `ProductStatus.PUBLISHED`-ს ანიჭებს. ავტომატური ჩართვის წინ შესაცვლელია. Price/stock refresh არ უნდა შეეხოს ProductImage-ებს.

Supplier raw stock (`supplier_stock_qty`) და ეფექტური stock (`stock_qty`) უკვე განცალკევებულია. გაყიდვის შემდეგ SupplierStockHold იცავს დაგვიანებული feed-ისგან; default hold 24 საათია. ორივე importer გზამ ეს უნდა შეინარჩუნოს. წარუმატებელი იმპორტი ძველი მონაცემებით მარაგს არ ზრდის. ახალი პროდუქტების summary/filter და sync failure/freshness alerts დასასრულებელია.

### 2. ბანკი — პერიოდული reconciliation

BOG callback და ხელით `reconcile_bog_payment` არსებობს. პერიოდული არჩევა/გაშვება და operator alerts ჯერ დასასრულებელია. მომხმარებელმა ეს production-ის მომზადებამდე გადადო; ახლა გეგმაშია, მაგრამ ჯერ არ შესრულებულა.

საწყისი საანგარიშო ვარაუდი: ყოველ 15 წუთში მხოლოდ შესაბამისი ასაკის დაუდასტურებელი/პრობლემური ტრანზაქციების შემოწმება. წარმატებით დადასტურებული გადახდა+შეკვეთა მუდმივად არ გადაიკითხოს.

ბანკის ჩვეულებრივი callback მაშინვე მუშავდება — 15 წუთს არ ელის. Cron დამატებითი აღდგენის გზაა, browser-ის დახურვის შემთხვევაშიც.

Paid/no-order ან fulfillment conflict შემთხვევაში operator alert და მკაფიო admin მდგომარეობა საჭიროა. გადამოწმებამ თანხა ხელახლა არ ჩამოჭრას და დაბლოკილი შეკვეთა ბრმად არ შექმნას. საჭირო refund/cancel ცალკე კონტროლდება. Bounded retries, shared lock და idempotency უნდა შენარჩუნდეს.

### 3. საკურიერო — EasyWay

Create/cancel და locations-ის ინტეგრაცია არსებობს; delivery status-ის პერიოდული sync ჯერ დასასრულებელია. საწყისი ვარაუდი: ყოველ 15 წუთში მხოლოდ EasyWay ID-ის მქონე აქტიური გზავნილები. თბილისში საკუთარი მიტანა EasyWay polling-ში არ შედის. საბოლოო მდგომარეობები და API სტატუსების შესაბამისობა ჯერ დასაზუსტებელია.

### 4. ყოველდღიური გასუფთავება

არსებობს `run_daily_cleanup`: ძველი კალათები, expired JWT და stock reservations. დაგეგმილი დრო 03:30, timezone `Asia/Tbilisi`. ეს ყოველდღიური sweep გადახდის რეალურ expiry/reconciliation ლოგიკას არ ცვლის.

აგრეთვე არსებობს `process_outbound_tasks` (Meta purchase dispatch). საჭიროება/queue-ის რეალური გამოყენება შემოწმდეს და ზედმეტი მუდმივი worker წინასწარ არ ვიყიდოთ.

### ფასიანი და უფასო scheduler

- App Platform native Cron მინიმუმ 15-წუთიან ინტერვალს იძლევა და მხოლოდ running time-ზე ირიცხება. ხანგრძლივი Supplier bulk-ისთვის ეს საწყისი არჩევანია.
- ბანკის/კურიერის მოკლე batch-ებისთვის კანდიდატია უფასო `cron-job.org` → დაცული backend HTTP endpoint. ჯერ არ არის საბოლოოდ არჩეული ან განხორციელებული. ამ შემთხვევაში მუშაობას არსებული backend ასრულებს, ამიტომ CPU/RAM/timeout უნდა შევამოწმოთ.
- გარე scheduler-ს ბანკის/DB secrets არ გადაეცემა. endpoint-ს სჭირდება საკუთარი server-only ავტორიზაცია, duplicate/replay დაცვა, shared lock, bounded batch და alerts.
- Browser `setInterval` საიმედო scheduler არ არის; server timer-იც restart/multiple instances-ის პრობლემებს თავისით ვერ აგვარებს.
- თუ შესამოწმებელი არაფერია, Job ბაზის მოკლე შემოწმების შემდეგ დასრულდება; გარე API მოთხოვნა არ გაიგზავნება, მაგრამ გაშვების დრო ნულოვანი არ არის.

ძველი საანგარიშო მაგალითი: 30 დღეში supplier 360×5 წუთი, ბანკი და კურიერი თითო 2,880×1 წუთი, ყველა Job 2 GiB ზომაზე → დაახლოებით $4.70 დამატებით. ეს არის ჰიპოთეტური runtime-ებით გათვლა, არა გაზომილი ინვოისი ან ფასის გარანტია. ამ მაგალითით ჯამი ~$53.85; $55–60 მხოლოდ დაგეგმვის სამიზნეა.

## Cloudinary — დამოუკიდებლობა აუცილებელია

არსებული Cloudinary ანგარიში შეიძლება გამოვიყენოთ უფასო ლიმიტებში, მაგრამ production-ს უნდა ჰქონდეს დამოუკიდებელი asset public ID-ები. მხოლოდ ცალკე DB ან dashboard folder ავტომატურად დამოუკიდებლობას არ ნიშნავს.

- ერთი და იგივე ფაილის URL ორ ბაზაში → storage არ ორმაგდება, მაგრამ წაშლა ორივე გარემოს აზიანებს.
- დამოუკიდებელი ასლები: პირობითად staging 500 MB + production 500 MB ≈ 1 GB, სხვა ვარიანტების/გარდაქმნების გათვალისწინებით.
- კოდში ProductImage-ის წაშლა Cloudinary ფაილის წაშლასაც იწვევს. სხვა გამოყენებას მხოლოდ იმავე DB-ში ეძებს.
- uploader `overwrite=True`-ს იყენებს; საერთო public ID ატვირთვისასაც სახიფათოა.
- ამიტომ upload/storage paths-ის გარემოს მიხედვით გამოყოფა და არსებული ფაილების ასლების შექმნა **ჯერ კოდში გასაკეთებელია**. დაგეგმილია `staging/` და `production/` განსხვავებული IDs, ყველა media ტიპისთვის.
- ორიგინალი და desktop/tablet/mobile/AI ვარიანტები წარმატებით დაკოპირდეს; მხოლოდ შემდეგ production DB ბმულები ტრანზაქციულად შეიცვალოს. SKU/alt/primary/sort შენარჩუნდეს.
- staging-ის ფაილები არ წაიშალოს production-ის დამოუკიდებლობის დადასტურებამდე. ამის შემდეგ staging-ზე მცირე სატესტო ნაკრების დატოვება storage-ს გაათავისუფლებს.
- storage-ის წაშლა უკვე დახარჯულ bandwidth-ს არ აბრუნებს. Cloudinary-ის ლიმიტში storage, transformations და delivery ერთად მონაწილეობს; მიმდინარე usage ჯერ არ გაზომილა.
- საერთო ანგარიში account-level უსაფრთხოების სრული იზოლაცია არაა; ამ განსხვავებას მომხმარებელი უნდა იცნობდეს.

## დახურული წვდომა და უსაფრთხოება

ეს ნაწილი ჯერ გასამართია და პირველ გარე deployment-მდე მზად უნდა იყოს.

საწყისი მიმართულებაა Cloudflare Access მხოლოდ მფლობელის email allowlist-ით, მოქმედი Free პირობების შემოწმებით. `noindex`, დამალული URL ან CORS დახურულ წვდომას არ უზრუნველყოფს.

- Frontend და backend/admin ორივე დაცული იყოს; `.ondigitalocean.app` პირდაპირი URL-ით შემოვლა არ უნდა შეიძლებოდეს.
- Origin-ზე Access JWT signature/issuer/audience/expiry მოწმდებოდეს ან გამოყენებული იყოს სხვა დადასტურებული origin-level დაცვა. მხოლოდ header-ის არსებობა არ კმარა.
- Nuxt SSR/API proxy-ის server-to-server წვდომა ცალკე მოეწყოს; secrets frontend public config-ში არა. სხვადასხვა Access app-ის token audience ბრმად არ შეერიოს.
- ბანკის ზუსტი callback გამონაკლისი ადამიანის login-ის გარეშე უნდა მუშაობდეს, ბანკის signature შემოწმების შენარჩუნებით. health/scheduler გამონაკლისებიც მინიმალური იყოს; მთელი API არ გაიხსნას.
- მოქმედი admin მისამართია `/manager-fd/`, არა `/admin/`. URL-ის შეცვლა MFA არ არის. დამატებითი admin დაცვა/recovery ჯერ საბოლოოდ გასამართია; ყოველ თანამშრომელს საკუთარი ანგარიში ჰქონდეს.
- ნაღდი გადახდა backend-ში გამორთულია `CASH_ON_DELIVERY_ENABLED=False`-ით და production-შიც ასე რჩება.
- DEBUG=False, ახალი production secrets, HTTPS/TLS, secure cookies, CSRF/CORS/reCAPTCHA, rate limiting და სწორი trusted proxy client IP შემოწმდეს.
- API/auth/cart/checkout/order lookup/personal პასუხები shared cache-ში არ მოხვდეს.
- Cloudinary public სურათის პირდაპირი URL storefront Access-ით ავტომატურად არ იკეტება. კერძო დოკუმენტები იქ public სახით არ ატვირთოთ.
- საჯაროდ გახსნისას მხოლოდ storefront-ის შეზღუდვა იხსნება, admin-ის დაცვა რჩება.

## მონაცემების გადატანა და კოდის deployment

1. ჯერ დავადგინოთ უახლესი წყარო: staging CMS/catalog თუ ლოკალური დასრულებული სურათები/კატეგორიები. ბრმად ერთ გარემოს ყველაფრის წყაროდ არ მივიჩნიოთ.
2. საწყისი snapshot შეიძლება გადაიტანოს მხოლოდ ცარიელ, იზოლირებულ production DB-ში, გამორთული app/jobs/email/payment/courier მოქმედებებით.
3. PostgreSQL version/extensions/restore tooling თავსებადობა და migrations-ის რიგი წინასწარ განისაზღვროს.
4. ზუსტი inventory/შედარება, მხოლოდ დადასტურებული სატესტო მონაცემების cleanup, დამოუკიდებელი staff/accounts/secrets და media ასლები.
5. **როგორც კი production-ში რედაქტირებას დავიწყებთ, სრული staging restore აღარ კეთდება — არც გახსნის დღეს.** მოგვიანებით მხოლოდ შერჩევითი, წინასწარი diff-ით ცვლილებები; production-ის draft/ფოტო/კატეგორია/მომხმარებელი/order არ გადაიწეროს.

Git push კოდს ცვლის და პროდუქტებს თავისით არ აკოპირებს; მაგრამ data migration/seed/import/build command შეიძლება DB-ს ცვლიდეს. ეს ყოველ release-ზე შემოწმდეს.

არსებული `build.sh` აყენებს dependencies-ს, წინასწარ ტვირთავს background-removal მოდელს, აკეთებს collectstatic-ს და **migrate-საც უშვებს**. Production-ისთვის migration-ის ერთ pre-deploy გაშვებად გამოყოფა დაგეგმილია, ჯერ არა შესრულებული. Job-ის build-ებმა migration მრავალჯერ/პარალელურად არ უნდა გაუშვან. Autodeploy საწყისად გამორთული დარჩეს; release commit-ები ჩაიწეროს.

Nuxt არის SSR Node აპი (`node .output/server/index.mjs`); Django გაშვებულია Uvicorn-ით (`bash start.sh`). Backend requirements-ში დათვალიერებისას Django 6.0.8 იყო. Redis/Valkey production-ში სავალდებულოა. Node/Python ვერსიები და lockfile/pins deployment-მდე თავსებადობაზე მოწმდება.

## Backup, აღდგენა და გახსნამდე შემოწმებები

- Backup = ბაზის უსაფრთხო სარეზერვო ასლი. DB backup სურათის რეალურ ფაილს არ შეიცავს, ამიტომ media recovery ცალკე გასათვალისწინებელია.
- Restore = ასლიდან ბაზის აღდგენა; ერთხელ იზოლირებულ დროებით ბაზაზე უნდა გამოვცადოთ, რომ backup გამოსადეგია. ეს შესაძლოა მოკლე დამატებით hosting ხარჯს მოითხოვდეს.
- Managed PostgreSQL-ის daily backup/PITR და retention provisioning-ისას დადასტურდეს; საწყის გეგმაში standby replica არ შედის.
- ყოველი მნიშვნელოვანი მონაცემთა ცვლილების წინ backup/ცვლილების ანგარიში; პასუხისმგებელი და აღდგენის ინსტრუქცია ჩაიწეროს.
- კოდის rollback DB migration-ს ავტომატურად არ აბრუნებს. რეალური გაყიდვების შემდეგ ძველ DB backup-ზე დაბრუნებამ ახალი შეკვეთები შეიძლება დაკარგოს — ეს ჩვეულებრივი release rollback არაა.
- გახსნამდე: auth/წერილები, catalog/search/filter, cart/wishlist, guest/registered checkout, bank success/failure/cancel/duplicate/missing callback/refund, order lookup/admin, supplier draft/holds, courier status, media delete isolation, closed-access bypass, alerts და წარმადობა.
- ბანკსა და კურიერთან რეალური მოქმედება მხოლოდ შეთანხმებული კონტროლირებული ტესტით, არა load test-ის ნაწილად.

## შემდეგი ერთი ნაბიჯი — აქედან გააგრძელე

მომხმარებელს უკვე ვუთხარით: **$15.15-იანი ბაზა ისევ საჭიროა, მაგრამ ჯერ Create-ს არ დააჭიროს.**

ახლა უნდა მოვამზადოთ დახურული deployment:

1. არსებული DNS/MX/TXT ჩანაწერების ინვენტარი და კომპანიის ელფოსტის უსაფრთხო შენარჩუნება.
2. დახურული frontend/backend წვდომის კონკრეტული განხორციელება, დროებითი origin URL-ების დაცვის ჩათვლით.
3. production პარამეტრების სახელების checklist, source მონაცემებისა და media-ს თავდაპირველი გადატანის გეგმა.

ამის შემდეგ, როცა იმავე დღეს გამართვას ვიწყებთ, **პირველი ფასიანი ნაბიჯია Managed PostgreSQL-ის შექმნა**, შემდეგ Valkey, დაცული backend/frontend, Proxy და შესაბამისი ავტომატიზაცია კოდის მზადყოფნის შემდეგ.

მომხმარებელს ამ პროცესში თითო ნაბიჯზე მხოლოდ კონკრეტული შემდეგი მოქმედება მიეცი. მთელი გეგმა თავიდან არჩევანის საგნად არ აქციო ახალი არსებითი მიზეზის გარეშე. თუ ახალი შეზღუდვა აღმოაჩინე, ჯერ მისი გავლენა და ალტერნატივის სრული ღირებულება აუხსენი.

## ოფიციალური ცნობარები

- App Platform ფასები: https://docs.digitalocean.com/products/app-platform/details/pricing/
- Managed DB/Valkey: https://www.digitalocean.com/pricing/managed-databases
- Droplet: https://www.digitalocean.com/pricing/droplets
- VPC: https://docs.digitalocean.com/products/app-platform/how-to/enable-vpc/
- Jobs: https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/
- Reserved IP outbound: https://docs.digitalocean.com/products/networking/reserved-ips/how-to/outbound-traffic/
- Cloudflare Access origin validation: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- უფასო scheduler-ის კანდიდატი: https://cron-job.org/en/

ყველა ზემოთ „დაგეგმილი“ ან „დასასრულებელი“ ფუნქცია უნდა ჩაითვალოს შეუსრულებლად, სანამ შესაბამისი კოდი/ინფრასტრუქტურა და შემოწმების შედეგი არ დადასტურდება. მომხმარებლის შემდგომი გადაწყვეტილებები ამ snapshot-ს შეიძლება ცვლიდეს.
