from django.urls import reverse
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from catalog.models import Category, Product, ProductStatus
from pages.models import BlogPost, Component, ComponentType, Content, ContentItem, FooterSettings, Page


class GetCurrentContentAPITests(APITestCase):
    def test_main_page_includes_seeded_order_confidence_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "main"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="main",
            component_type__name="OrderConfidence",
        )
        component_key = f"OrderConfidence_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 40)
        self.assertEqual(
            component_payload["data"]["title"],
            "შეკვეთა Auto[[Mate]]-ზე წინასწარ გასაგებია",
        )
        self.assertEqual(
            component_payload["data"]["subtitle"],
            "ონლაინ ყიდვისას ყველაზე ხშირად რაც აჩენს ეჭვს, აქ წინასწარ ნათელია: პროცესი, გადახდა, რეგისტრაცია და მიწოდება.",
        )
        self.assertEqual(len(items), 4)
        self.assertEqual(
            [item["title"] for item in items],
            [
                "პროცესი წინასწარ ნათელია",
                "გადახდა ისე, როგორც გაწყობს",
                "რეგისტრაცია სავალდებულო არ არის",
                "მიწოდებაზე გაურკვევლობა არ რჩება",
            ],
        )
        self.assertEqual(
            [item["content_type"] for item in items],
            ["trust_card", "trust_card", "trust_card", "trust_card"],
        )
        self.assertTrue(all("<svg" in (item["icon_svg"] or "") for item in items))

    def test_privacy_policy_page_includes_seeded_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "privacy-policy"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="privacy-policy",
            component_type__name="PrivacyPolicy",
        )
        component_key = f"PrivacyPolicy_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 10)
        self.assertEqual(
            component_payload["data"]["title"],
            "კონფიდენციალურობის პოლიტიკა",
        )
        self.assertEqual(
            component_payload["data"]["subtitle"],
            "ამ გვერდზე აღწერილია რა ინფორმაციას ამუშავებს AutoMate, რატომ გვჭირდება ეს მონაცემები, ვისთან შეიძლება გაზიარება და რა არჩევანი გაქვთ თქვენ.",
        )
        self.assertEqual(component_payload["data"]["contentData"]["listcount"], 6)
        self.assertEqual(
            [item["title"] for item in items],
            [
                "რა ინფორმაციას ვაგროვებთ",
                "როგორ ვიყენებთ ინფორმაციას",
                "ვის ვუზიარებთ ინფორმაციას",
                "რამდენ ხანს ვინახავთ მონაცემებს",
                "თქვენი უფლებები და არჩევანი",
                "კონტაქტი და პოლიტიკის განახლებები",
            ],
        )
        self.assertTrue(all(item["content_type"] == "policy_section" for item in items))
        self.assertTrue(all(item["editor"] for item in items))

    def test_terms_page_includes_seeded_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "terms"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="terms",
            component_type__name="Terms",
        )
        component_key = f"Terms_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 10)
        self.assertEqual(component_payload["data"]["title"], "წესები და პირობები")
        self.assertEqual(
            component_payload["data"]["subtitle"],
            "ამ გვერდზე აღწერილია AutoMate-ის ვებსაიტის გამოყენების, ანგარიშების, შეკვეთების, გადახდისა და შეკვეთის ძირითადი პირობები როგორც სტუმარი, ისე რეგისტრირებული მომხმარებლისთვის.",
        )
        self.assertEqual(component_payload["data"]["contentData"]["listcount"], 7)
        self.assertEqual(
            [item["title"] for item in items],
            [
                "საიტის გამოყენება და ანგარიშის ტიპები",
                "პროდუქტები, ფასები და ხელმისაწვდომობა",
                "შეკვეთის გაფორმება და დადასტურება",
                "გადახდის პირობები",
                "მიწოდების მოკლე პირობები",
                "დაბრუნება და თანხის დაბრუნება",
                "ინტელექტუალური საკუთრება, პასუხისმგებლობა და ცვლილებები",
            ],
        )
        self.assertTrue(all(item["content_type"] == "terms_section" for item in items))
        self.assertTrue(all(item["editor"] for item in items))

    def test_delivery_page_includes_seeded_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "delivery"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="delivery",
            component_type__name="Delivery",
        )
        component_key = f"Delivery_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 10)
        self.assertEqual(component_payload["data"]["title"], "მიწოდების პირობები")
        self.assertEqual(
            component_payload["data"]["subtitle"],
            "ამ გვერდზე აღწერილია როგორ ამუშავებს AutoMate შეკვეთებს მიწოდებისთვის, რა ვადები მოქმედებს თბილისში და რეგიონებში, რა შემთხვევაში შეიძლება შეიცვალოს ვადა და როგორ მიიღოთ მხარდაჭერა შეკვეთის სტატუსთან დაკავშირებით.",
        )
        self.assertEqual(component_payload["data"]["contentData"]["listcount"], 6)
        self.assertEqual(
            [item["title"] for item in items],
            [
                "შეკვეთის დამუშავება",
                "მიწოდება თბილისში",
                "მიწოდება რეგიონებში",
                "მისამართი და მიღება",
                "შესაძლო შეფერხებები",
                "შეკვეთის სტატუსი და დახმარება",
            ],
        )
        self.assertTrue(all(item["content_type"] == "delivery_section" for item in items))
        self.assertTrue(all(item["editor"] for item in items))

    def test_page_payload_includes_catalog_category_for_content_items(self):
        page, _ = Page.objects.get_or_create(name="მთავარი", slug="main")
        component_type = ComponentType.objects.create(name="ProblemSolvingTest")
        content = Content.objects.create(name="problem_solving_cards_test")
        category = Category.objects.create(
            name="Interior Test",
            slug="interior-test",
            sort_order=1,
            is_active=True,
        )
        Component.objects.bulk_create(
            [
                Component(
                    page=page,
                    component_type=component_type,
                    content=content,
                    title="რა პრობლემას გიგვარებს AutoMate",
                    subtitle="ავტომობილის ყოველდღიური გამოყენება ბევრ პატარა შეუსაბამობას ქმნის.",
                    enabled=True,
                )
            ]
        )
        component = Component.objects.get(component_type=component_type, content=content)
        ContentItem.objects.bulk_create(
            [
                ContentItem(
                    content=content,
                    title="არეული სალონი",
                    description="ორგანიზატორები და პრაქტიკული აქსესუარები.",
                    content_type="problem_card",
                    position=1,
                    icon_svg="<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    catalog_category=category,
                )
            ]
        )

        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "main"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component_key = f"{component_type.name}_{component.id}"
        component_payload = response.data["secondary"][component_key]
        item_payload = component_payload["data"]["contentData"]["list"][0]

        self.assertEqual(item_payload["catalog_category"]["id"], category.id)
        self.assertEqual(item_payload["catalog_category"]["name"], "Interior Test")
        self.assertEqual(item_payload["catalog_category"]["slug"], "interior-test")

    def test_page_payload_orders_components_by_position(self):
        page = Page.objects.create(name="Ordering Page", slug="ordering-page")
        content_a = Content.objects.create(name="ordering_component_a")
        content_b = Content.objects.create(name="ordering_component_b")
        type_a = ComponentType.objects.create(name="OrderingComponentA")
        type_b = ComponentType.objects.create(name="OrderingComponentB")

        Component.objects.bulk_create(
            [
                Component(
                    page=page,
                    component_type=type_a,
                    content=content_a,
                    title="Later component",
                    position=20,
                    enabled=True,
                ),
                Component(
                    page=page,
                    component_type=type_b,
                    content=content_b,
                    title="Earlier component",
                    position=10,
                    enabled=True,
                ),
            ]
        )

        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "ordering-page"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.data["secondary"].keys()),
            [
                f"{type_b.name}_{Component.objects.get(component_type=type_b).id}",
                f"{type_a.name}_{Component.objects.get(component_type=type_a).id}",
            ],
        )


class SitemapEntriesAPITests(APITestCase):
    def test_sitemap_endpoint_returns_only_indexable_entries(self):
        page_content = Content.objects.create(name="sitemap_page_content")
        page_component_type = ComponentType.objects.create(name="SitemapPageComponent")

        main_page, _ = Page.objects.update_or_create(
            slug="main",
            defaults={"name": "Main", "seo_noindex": False},
        )
        blogs_page, _ = Page.objects.update_or_create(
            slug="blogs",
            defaults={"name": "Blogs", "seo_noindex": False},
        )
        hidden_page = Page.objects.create(
            name="Hidden Page",
            slug="hidden-page",
            seo_noindex=True,
        )

        Component.objects.create(
            page=main_page,
            component_type=page_component_type,
            content=page_content,
            enabled=True,
        )
        Component.objects.create(
            page=blogs_page,
            component_type=page_component_type,
            content=page_content,
            enabled=True,
        )
        Component.objects.create(
            page=hidden_page,
            component_type=page_component_type,
            content=page_content,
            enabled=True,
        )

        visible_category = Category.objects.create(
            name="Interior Sitemap",
            slug="interior-sitemap",
            is_active=True,
            sort_order=1,
        )
        hidden_category = Category.objects.create(
            name="Hidden Sitemap Category",
            slug="hidden-sitemap-category",
            is_active=True,
            sort_order=2,
            seo_noindex=True,
        )

        visible_product = Product.objects.create(
            category=visible_category,
            name="Visible Sitemap Product",
            slug="visible-sitemap-product",
            sku="VISIBLE-SITEMAP-1",
            short_description="Visible sitemap product",
            description="Visible sitemap product",
            price="99.00",
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )
        Product.objects.create(
            category=visible_category,
            name="Draft Sitemap Product",
            slug="draft-sitemap-product",
            sku="DRAFT-SITEMAP-1",
            price="79.00",
            stock_qty=5,
            status=ProductStatus.DRAFT,
        )
        hidden_product = Product.objects.create(
            category=visible_category,
            name="Hidden Sitemap Product",
            slug="hidden-sitemap-product",
            sku="HIDDEN-SITEMAP-1",
            price="109.00",
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
            seo_noindex=True,
        )
        Product.objects.create(
            category=hidden_category,
            name="Hidden Category Product",
            slug="hidden-category-product",
            sku="HIDDEN-CATEGORY-1",
            price="119.00",
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )

        blog_content, _ = Content.objects.get_or_create(name="bloglist")
        visible_blog_item = ContentItem.objects.create(
            content=blog_content,
            title="Visible Sitemap Blog",
            slug="visible-sitemap-blog",
            content_type="blogs",
            singlePageRoute=blogs_page,
        )
        BlogPost.objects.create(
            content_item=visible_blog_item,
            status="published",
            published_at=timezone.now(),
        )

        hidden_blog_item = ContentItem.objects.create(
            content=blog_content,
            title="Hidden Sitemap Blog",
            slug="hidden-sitemap-blog",
            content_type="blogs",
            singlePageRoute=blogs_page,
        )
        BlogPost.objects.create(
            content_item=hidden_blog_item,
            status="published",
            published_at=timezone.now(),
            seo_noindex=True,
        )

        response = self.client.get(reverse("sitemap-entries"))

        self.assertEqual(response.status_code, 200)
        locs = {entry["loc"] for entry in response.data["entries"]}

        self.assertIn("/", locs)
        self.assertIn("/blogs", locs)
        self.assertNotIn("/hidden-page", locs)

        self.assertIn("/catalog/category/interior-sitemap", locs)
        self.assertNotIn("/catalog/category/hidden-sitemap-category", locs)

        self.assertIn(f"/catalog/{visible_product.slug}", locs)
        self.assertNotIn(f"/catalog/{hidden_product.slug}", locs)
        self.assertNotIn("/catalog/draft-sitemap-product", locs)

        self.assertIn(f"/blogs/{visible_blog_item.id}-visible-sitemap-blog", locs)
        self.assertNotIn(f"/blogs/{hidden_blog_item.id}-hidden-sitemap-blog", locs)


class FooterAPITests(APITestCase):
    def test_footer_endpoint_returns_grouped_links_and_settings(self):
        FooterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "brand_name": "AutoMate",
                "brand_description": "აქსესუარების მარტივი არჩევანი ერთ სივრცეში.",
                "trust_item_1": "მარტივი შეკვეთა",
                "trust_item_2": "სწრაფი მიწოდება",
                "trust_item_3": "უსაფრთხო გადახდა",
                "phone": "+995 500 00 00 00",
                "email": "support@automate.ge",
                "working_hours": "ორშ-პარ, 10:00 - 19:00",
                "city": "თბილისი, საქართველო",
                "instagram_url": "https://instagram.com/automate",
                "facebook_url": "https://facebook.com/automate",
                "copyright_text": "© 2026 AutoMate. ყველა უფლება დაცულია.",
            },
        )

        Page.objects.update_or_create(
            slug="main",
            defaults={
                "name": "მთავარი",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.NAVIGATION,
                "footer_order": 20,
            },
        )
        Page.objects.update_or_create(
            slug="catalog",
            defaults={
                "name": "კატალოგი",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.NAVIGATION,
                "footer_order": 10,
            },
        )
        Page.objects.update_or_create(
            slug="delivery",
            defaults={
                "name": "მიწოდება",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.HELP,
                "footer_order": 10,
            },
        )
        Page.objects.update_or_create(
            slug="privacy-policy",
            defaults={
                "name": "კონფიდენციალურობა",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.LEGAL,
                "footer_order": 10,
                "footer_label": "კონფიდენციალურობა",
            },
        )

        Page.objects.update_or_create(
            slug="terms",
            defaults={
                "name": "წესები და პირობები",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.LEGAL,
                "footer_order": 20,
                "footer_label": "წესები და პირობები",
            },
        )

        response = self.client.get(reverse("footer"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["brand"]["name"], "AutoMate")
        self.assertEqual(
            response.data["trust_items"],
            ["მარტივი შეკვეთა", "სწრაფი მიწოდება", "უსაფრთხო გადახდა"],
        )
        self.assertEqual(response.data["contact"]["email"], "support@automate.ge")
        self.assertEqual(
            [item["slug"] for item in response.data["groups"]["navigation"][:2]],
            ["catalog", "main"],
        )
        self.assertEqual(
            response.data["groups"]["navigation"][1]["url"],
            "/",
        )
        self.assertEqual(
            response.data["groups"]["help"][0]["slug"],
            "delivery",
        )
        self.assertEqual(
            [item["slug"] for item in response.data["groups"]["legal"][:2]],
            ["privacy-policy", "terms"],
        )
        self.assertEqual(
            [item["label"] for item in response.data["groups"]["legal"][:2]],
            ["კონფიდენციალურობა", "წესები და პირობები"],
        )
        self.assertEqual(
            [item["type"] for item in response.data["socials"]],
            ["email", "instagram", "facebook"],
        )


@override_settings(
    CACHE_ENABLED=True,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "pages-cache-tests",
            "TIMEOUT": None,
        }
    },
)
class PublicPagesCacheTests(APITestCase):
    def setUp(self):
        cache.clear()
        BlogPost.objects.all().delete()
        Component.objects.all().delete()
        ContentItem.objects.all().delete()
        Content.objects.all().delete()
        ComponentType.objects.all().delete()
        FooterSettings.objects.all().delete()
        Page.objects.all().delete()

    def tearDown(self):
        cache.clear()

    def test_menu_endpoint_returns_miss_then_hit_and_invalidates_on_page_save(self):
        page = Page.objects.create(
            name="Catalog",
            slug="catalog",
            show_in_menu=True,
            order=1,
        )

        first_response = self.client.get(reverse("menu"))
        second_response = self.client.get(reverse("menu"))

        page.name = "Updated Catalog"
        page.save()

        third_response = self.client.get(reverse("menu"))

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.headers["X-Cache-Status"], "MISS")
        self.assertEqual(second_response.headers["X-Cache-Status"], "HIT")
        self.assertEqual(third_response.headers["X-Cache-Status"], "MISS")
        self.assertEqual(third_response.data[0]["name"], "Updated Catalog")

    def test_get_current_content_returns_miss_then_hit_and_invalidates_on_content_item_save(self):
        page = Page.objects.create(name="Main", slug="main")
        component_type = ComponentType.objects.create(name="CacheCards")
        content = Content.objects.create(name="cache_cards")
        component = Component.objects.create(
            page=page,
            component_type=component_type,
            content=content,
            title="Cached cards",
            enabled=True,
            position=1,
        )
        item = ContentItem.objects.create(
            content=content,
            title="First item",
            content_type="card",
            position=1,
        )

        first_response = self.client.post(
            reverse("get-current-content"),
            {"slug": "main"},
            format="json",
        )
        second_response = self.client.post(
            reverse("get-current-content"),
            {"slug": "main"},
            format="json",
        )

        item.title = "Updated item"
        item.save()

        third_response = self.client.post(
            reverse("get-current-content"),
            {"slug": "main"},
            format="json",
        )

        component_key = f"{component_type.name}_{component.id}"
        third_item_title = third_response.data["secondary"][component_key]["data"]["contentData"]["list"][0]["title"]

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.headers["X-Cache-Status"], "MISS")
        self.assertEqual(second_response.headers["X-Cache-Status"], "HIT")
        self.assertEqual(third_response.headers["X-Cache-Status"], "MISS")
        self.assertEqual(third_item_title, "Updated item")


