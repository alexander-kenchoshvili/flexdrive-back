from django.urls import reverse
from rest_framework.test import APITestCase

from pages.models import FooterSettings, Page


class FooterFaqVisibilityTests(APITestCase):
    def test_footer_endpoint_does_not_include_faq_link(self):
        FooterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "brand_name": "AutoMate",
                "brand_description": "აქსესუარების მარტივი არჩევანი ერთ სივრცეში.",
                "email": "support@automate.ge",
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
            slug="main",
            defaults={
                "name": "მთავარი",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.NAVIGATION,
                "footer_order": 20,
            },
        )
        Page.objects.update_or_create(
            slug="faq",
            defaults={
                "name": "ხშირად დასმული კითხვები",
                "show_in_footer": False,
                "footer_group": Page.FooterGroup.NAVIGATION,
                "footer_order": 40,
            },
        )

        response = self.client.get(reverse("footer"))

        self.assertEqual(response.status_code, 200)
        navigation_slugs = [item["slug"] for item in response.data["groups"]["navigation"]]

        self.assertIn("catalog", navigation_slugs)
        self.assertIn("main", navigation_slugs)
        self.assertNotIn("faq", navigation_slugs)
