# SEO — deployment და გახსნის ნაბიჯები

ეს არის [SEO გეგმის](SEO_PRELAUNCH_AUDIT_2026-11-15.md) შესრულების მოკლე ინსტრუქცია.
მაღაზიის გახსნის დრო მომხმარებელს ეკუთვნის. ახალი source კოდი ჯერ production-ში
არ არის დადასტურებული; ლოკალური წარმატება live გამართულობის მტკიცებულება არ არის.

1. მომხმარებელი push/deploy-ს აკეთებს **backend-ზე, შემდეგ frontend-ზე**. ორივე
   საჭიროა: backend ასწორებს პროდუქტის canonical მისამართს; frontend — SEO რეჟიმებს,
   robots/sitemap-ს, ჰოსტის დაცვას და კატეგორიის H1-ს. ახალი მიგრაცია არ სჭირდება.
2. ჯერ `public_open=false` შევინარჩუნოთ და დავადასტუროთ backend/frontend Healthy.
   რეალურ root/starter-ზე anonymous და preview პასუხები noindex უნდა დარჩეს.
   `/robots.txt` უნდა იყოს text/plain, `Disallow: /`; `/sitemap.xml` — XML, ცარიელი.
   sitemap-ისთვის private, no-store პასუხი; პროდუქტის სია დახურულ რეჟიმში არ გაიცემა.
3. DigitalOcean frontend ENV-ის მოქმედი მნიშვნელობები წავიკითხოთ. მიზანი:
   `NUXT_PUBLIC_SITE_URL=https://flexdrive.ge`, სწორი `NUXT_INTERNAL_API_URL`,
   `NUXT_STOREFRONT_ACCESS_GUARD_ENABLED=true`. არსებული scope/სხვა ველები დაცული რჩება.
   **მხოლოდ ახალი კოდის deployment-ის დადასტურების შემდეგ** მოვამზადოთ
   `NUXT_PUBLIC_ALLOW_INDEXING=true`. ეს SEO-ს მზაობაა, არა მაღაზიის გახსნა:
   launch guard დახურულსა და preview რეჟიმში ისევ noindex/ცარიელ sitemap-ს მოითხოვს.
4. ENV deployment-ის შემდეგ იგივე დახურული პასუხები რეალურ ჰოსტზე ხელახლა
   შევამოწმოთ. ამ ეტაპზე DNS/ბანკი/OAuth/LaunchControl-ის public flag არ იცვლება.
5. მომხმარებელი ასრულებს მეგობრის სატესტო გადახდას და თავისი დროით ხსნის მაღაზიას.
   შემდეგ ვამოწმებთ მთავარს/კატეგორიას/პროდუქტს/ბლოგს/page2/ფილტრს/უცნობ და პირად
   გზებს: სტატუსი, robots header/meta, canonical, title/H1/description/JSON-LD.
   starter რჩება noindex; www308 ინარჩუნებს გზასა და query-ს. კრიტიკული შეცდომისას
   დროებით გამოვრთოთ indexing ENV; საჯარო წვდომის შეცვლა მომხმარებელთან შეთანხმდება.
6. ღია sitemap უნდა შეიცავდეს მხოლოდ კანონიკურ, ინდექსირებად200 URL-ებს. sitemap
   Search Console-ში ვაგზავნით მხოლოდ ამის შემდეგ; მთავარ/პროდუქტის რამდენიმე URL-ზე
   URL Inspection/Rich Results. ინდექსაციის ან რანგის გარანტია არ არსებობს.
7. რეალურ მობილურ გვერდებზე PageSpeed/Core Web Vitals; პრობლემები გაზომვით
   პრიორიტეტდება. დახურული holding-ის ქულა კატალოგის სიჩქარის შეფასება არ არის.

შემდგომი კონტენტის სამუშაო (ნამდვილი ფოტოები/თავსებადობა/გზამკვლევები/შერჩეული
მოდელი+ნაწილის გვერდები) რეალურ მონაცემებსა და კონტენტს მოითხოვს. ყველა ფილტრის
მასობრივი ინდექსაცია არ იგეგმება. Merchant Center ცალკე ენის/eligibility საკითხია.
