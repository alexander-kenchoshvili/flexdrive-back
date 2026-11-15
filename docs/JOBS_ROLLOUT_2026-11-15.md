# გადახდების და Cross Motors-ის გრაფიკების გამართვა

## საბოლოო მიმდინარე შედეგი — 2026-11-15

**კონფიგურაცია დასრულებულია. ქვემოთ ძველი draft/pending ჩანაწერები ისტორიულია.**

- Cross Motors საათში ერთხელ; ახალი18:01:14 invocation Jobs სიაში Success,
  ID `0c9ae1e6-4a34-42fa-a6d1-477bb2703c65`.
- შექმნილია მხოლოდ ერთი `bog-payment-reconciliation`,512MB;21component ENV,
  იგივე web DATABASE_URL binding,14BOG, DATABASE_CONN_MAX_AGE,5META. Global პარამეტრები
  მემკვიდრეობს. Secret encrypted მნიშვნელობები გამოყენებულია იმავე აპში.
- Readiness deployment `37edaf99-b69a-4c78-8b1f-0d95b825e582` Success/Live;
  `Eligible payments in batch: 0. No API calls, writes or emails.`
- რეალური command:
  `python manage.py reconcile_bog_payments --limit 100 --min-age-minutes 10 --retry-minutes 15 --max-seconds 600`.
  Deployment `1f8c1484-16fe-48d3-8989-babbec6cb813` Success;
  ლოგი `resolved=0 pending=0 review=0 failed=0 skipped=0`.
- საბოლოო cron `*/15 * * * *`, optional timezone ნაგულისხმევი, timeout12m.
  Deployment `367ce7fc-5113-4a49-ac30-5d3489fcc0ab` Live დადასტურდა.
- App-level Failed Job Invocation ჩართულია, DO ანგარიშის არსებული ელფოსტა
  kenchoshvili.alexander1@gmail.com; შენახვის შემდეგ summary reload-ით დასტურდება.
  Payment-level support@flexdrive.ge უცვლელია. შეტყობინების მიღება არ დატესტილა.
- პირველი15წუთიანი scheduled bank invocation ჯერ არ დაკვირვებულა. კანდიდატიანი
  ბანკის აღდგენა/რეალური შესყიდვა და missed-run heartbeat ცალკე რჩება.
- Safe aggregate `final-job-result.json` ignored საქაღალდეში. დროებითი encrypted
  spec YAML წაშლილია; Computer Use kernel reset. საჯარო მაღაზია არ გახსნილა.

მომხმარებელმა მოითხოვა BOG reconciliation-ის სრული production კონფიგურაცია და
Cross Motors-ის ყოველ48საათიანი განახლების საათობრივზე გადასვლა. საჯარო მაღაზიის
გახსნა ამ დავალებაში არ შედის. ქვემოთ მხოლოდ ფაქტობრივად შესრულებული ნაბიჯებია.

## Cross Motors — შენახულია, შესრულების შემოწმება დარჩა

### დამატებითი გადამოწმება ამ გაგრძელებაში

- Activity/Deployments-ში დადასტურდა Live deployment: „Deployed configuration
  changes for crossmotors-sync“, 15 ნოემბერი 17:19:23 (UI დრო). ქვემოთ ძველი
  შენიშვნა deployment-ის დაუდასტურებლობაზე უკვე ისტორიულია.
- Jobs-ის ბოლო ხელმისაწვდომი წარმატება: 00:01:35–00:01:53, 18 წამი; ლოგი:
  „Cross Motors database import applied.“ ეს ძველი daily/parity კონფიგურაციის
  შესრულებაა და ახალი საათობრივი გრაფიკის რეალურ წარმატებას ჯერ არ ამტკიცებს.
- Safe aggregate evidence: `cross-last-execution.json` იმავე ignored საქაღალდეში.

- არსებული backend app `9f8af0f7-ff7e-493c-8238-a51b8e27947f`, component
  `crossmotors-sync`; source `main`, hash `886ca82`, autodeploy გამორთული.
- საწყისი trigger იყო `0 0 * * *`, **Asia/Tbilisi**, ხოლო ბრძანება UTC თარიღის
  ლუწობა/კენტობით უშვებდა იმპორტს დღეგამოშვებით. მარტო cron-ის შეცვლა არასაკმარისია.
- შეიცვალა მხოლოდ run command პირდაპირ იმპორტზე და cron `0 * * * *`-ზე:
  `python manage.py import_crossmotors_products --page-size 1000 --sample-size 0 --bulk --archive-missing --commit`.
  დროის სარტყელი Asia/Tbilisi უცვლელია; trigger-ის სხვა ველები უცვლელია.
- reload-ის შემდეგ UI აჩვენებს Every hour და ზუსტ ახალ ბრძანებას. რესურსის ზომა
  უცვლელია (1GB/1sharedvCPU/1container; UI base plan $12/mo). ფაქტობრივი job ხარჯი
  მუშაობის დროზეა დამოკიდებული; საათობრივი განახლება უფრო მეტ შესრულებას ნიშნავს.
- ცვლილების deployment-ის Building job შეტყობინება დაფიქსირდა. მისი Success/Live
  და ახალი ბრძანებით job-ის რეალური წარმატება **ჯერ არ შემოწმებულა**.
- component Alert Policies ცარიელია. ახალი გაფრთხილება/მიმღები ჯერ არ დამატებულა.
- მომავალი სრული შესრულება კვლავ ინახავს SupplierSyncReport-ს. არსებული
  დაცვის20% missing threshold/transaction/advisory lock უცვლელია.

## გადახდები — მომზადებულია draft, ჯერ არ შექმნილა

### Draft/ENV-ის მიმდინარე მდგომარეობა

- Wizard-ის app-level ინვენტარში ფაქტობრივად 35 key არის, backend component-ში47.
  App-level alert recipient არის support@flexdrive.ge; Brevo/Wingo global ENV
  მემკვიდრეობს, მაგრამ14 BOG და5 Meta component ENV ცალკე სჭირდება ახალ job-ს.
- ქვემოთ აღწერილი draft DATABASE_URL binding UI-მ არავალიდურად მონიშნა;
  წაიშალა მხოლოდ შეუნახავი draft row. ახალი job-ის component ENV ამჟამად ცარიელია.
  App-global DATABASE_URL არსებობს; source web-component override-ის შესაბამისობა
  და production DB readiness ახალი job-ის dry-run-ით ჯერ დასადასტურებელია.
- BOG_CLIENT_SECRET masked არის ENV editor-ში; არ დაკოპირებულა ნიღაბი და არც
  credential გადატანილა app-global-ში. აუცილებელია არსებული encrypted მნიშვნელობების
  უსაფრთხო reuse იმავე აპში; Meta CAPI პარამეტრებიც საჭიროა აღდგენილი Purchase-ისთვის.
- App Settings → App Spec editor გაიხსნა წასაკითხად. სრული spec არ წაკითხულა,
  არაფერი შეცვლილა/შენახულა. View raw-ის მცდელობისას Computer Use URL-confidence
  პოლიტიკამ შეწყვიტა მუშაობა. ამის შემდეგ UI input არ შესრულებულა; kernel reset.
- ძველი wizard draft დარჩენილია tab5-ში, App Spec ბოლო ტაბში. ჯერ ახალი UI
  inventory; არ შექმნა ორი job. ფინანსური საბოლოო შექმნა და ახალი failed-job
  notification subscription მოქმედების წინ კონკრეტულ დასტურს საჭიროებს skill-ის
  confirmations[11]/[10]-ით. ეს დასტური ჯერ არ მოგვითხოვია.

### ხარჯის შეფასება (30 დღის მაგალითი)

Runtime billing, per-second/one-minute minimum; UI rounded rates მიხედვით:
Cross ~$0.018/hr,720 hourly runs →1წთ/run ~$0.22;5წთ/run ~$1.08.
BOG ~$0.007/hr,2880 runs →1წთ/run ~$0.34;5წთ/run ~$1.68.
Cross ისტორიულად18წმ იყო, მომავალი ხანგრძლივობა გარანტირებული არაა. BOG ჯერ არ
გაშვებულა. ეს მოხმარების მაგალითებია და არა ინვოისის გარანტია/ფიქსირებული $12+$5.
ოფიციალური წყარო: https://docs.digitalocean.com/products/app-platform/details/pricing/

ქვემოთ draft binding/37 keys და უცნობი tab-ის ძველი ჩანაწერები ისტორიულია;
მიმდინარე მდგომარეობისთვის ზემოთ დამატებული ჩანაწერი გამოიყენე.

- იმავე app-ში სხვა BOG job კომპონენტი მიმდინარე settings-ში არ ჩანს; ახალი
  resource wizard-ში გამოყენებულია არსებული backend GitHub repo/main, root
  directory; autodeploy გამორთულია. გარე scheduler ამ ეტაპზე არ შემოწმებულა.
- Draft name `bog-payment-reconciliation`, type Job, 512MB/1sharedvCPU/1container.
  UI აჩვენებს **$0.007/hour სამუშაო დროზე**, ახალი რესურსის **$0–$5/month** დიაპაზონს.
  ეს არაა მომავალი ზუსტი მოხმარების პროგნოზი. არსებული App total აქ არ ერევა.
- პირველი readiness გაშვების command:
  `python manage.py reconcile_bog_payments --dry-run`.
  Trigger **ჯერ ნაგულისხმევი After every successful deploy** დარჩა. ესაა უსაფრთხო
  საწყისი შემოწმებისთვის, არა15წუთიანი საბოლოო scheduler. build command ცარიელია.
- Draft-ში დამატებულია მხოლოდ component `DATABASE_URL=${flexdrive-prod-db.DATABASE_URL}`
  binding, default run/build scope. რეალური პაროლი არ გადაკოპირებულა/გამოტანილა.
- App-level ENV ცხრილმა პირველ გვერდზე10 key აჩვენა; სრული37/app-level და backend
  component ENV სია ჯერ გადასამოწმებელია. BOG credentials/Brevo/alert recipient-ის
  job-ისთვის ხელმისაწვდომობა **ჯერ დაუდასტურებელია**. Component-only ველები
  ავტომატურად სხვა job-ზე არ მემკვიდრეობს; global-ად გადატანა ბრმად არ მოხდეს.
- **Add resources არ დაჭერილა**, ახალი ფასიანი რესურსი არ არსებობს; production
  dry-run/რეალური BOG მოთხოვნა/წერილი ამ ეტაპზე არ შესრულებულა. არსებული .env-ის
  DATABASE_URL production არ არის, ამიტომ მისით production კავშირი არ ყოფილა.

## შეტყობინებები და პანელი

კოდით დადასტურებულია: payment-level reconciliation issue და attempted_at ინახება;
ადმინში Payment transactions-ის „გადახდის გადამოწმება → საჭიროებს ყურადღებას“
ფილტრი/მიზეზი/დრო ჩანს. Business Operations გასცემს issue/checked_at მონაცემებს.
ყოველი reconciliation batch-ის ცალკე SupplierSyncReport არ იქმნება: გაშვებების
ისტორია DO Jobs/logs-ში უნდა გადამოწმდეს. სრული all-job heartbeat/run-history
პანელი ამ დავალებაში ჯერ არ განხორციელებულა.

## გაგრძელების ზუსტი რიგი

1. მიმდინარე browser ტაბების ახალი inventory: ბოლო Alt+Enter navigation-ის შედეგი
   უცნობია. ახალ ტაბში Cross settings უნდა გახსნილიყო და წინა job draft დარჩენილიყო.
   **არ დაამატო მეორე resource ბრმად**; ჯერ არსებული draft/current app state ნახე.
2. Cross latest deployment/Jobs ბოლო შედეგი და დაგეგმილი hourly trigger გადაამოწმე;
   საჭიროებისას არსებული job-ის კონტროლირებული გაშვება და admin report.
3. სრული app/component ENV ინვენტარი, მხოლოდ საჭირო binding/credential reuse იმავე
   DO job-ში; არ გამოიტანო raw secrets/screenshots/ფაილები. არსებული production
   migration0031 ადრე გამოყენებულია SKU სამუშაოში (AGENTS), ძველი pending doc staleა.
4. ფასიანი job-ის საბოლოო Add resources-მდე კონკრეტული cost approval მოითხოვე
   Computer Use confirmations [11]-ის მიხედვით; ჯერჯერობით approval არ გვიკითხავს.
   ახალი cloud notification subscription-საც action-time confirmation სჭირდება.
5. შექმნის შემდეგ პირველადი dry-run და app/db/cache/credential readiness; საჭირო
   failure alerts და მათი მიმღები. მერე run command რეალურზე და schedule
   `*/15 * * * *` (min-age10/retry15/limit100/max-seconds600), რეალური გაშვების შედეგი.
6. დაგვიანებული/გამოტოვებული job-ის detection ცალკე დარჩა; component failed alert
   თავისით „არ გაეშვა“ სცენარს არ ფარავს. ეს თუ ჯერ ვერ მოეწყო, სრული მზადყოფნა
   არ გამოაცხადო. სატესტო ნამდვილი გადახდა მომხმარებელთან ცალკე რჩება.

Computer Use გაჩერდა URL-confidence პოლიტიკით Alt+Enter ახალი ტაბის გახსნისას.
ამ შეჩერების შემდეგ UI input არ შესრულებულა; kernel reset შესრულდა capture-ის
გასათავისუფლებლად. მომხმარებლის ახალ retry-ზე გაგრძელება შეიძლება.
Safe evidence: ignored `tmp/measurements-20261015/jobs-20261115/cross-original.json`
და `cross-configured.json`. credentials არ ინახება.

ოფიციალური საყრდენი: [DigitalOcean Jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/).
