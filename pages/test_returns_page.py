from django.urls import reverse
from rest_framework.test import APITestCase

from pages.models import Component, FooterSettings, Page


class ReturnsPageAPITests(APITestCase):
    def test_returns_page_includes_seeded_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "returns"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="returns",
            component_type__name="Returns",
        )
        component_key = f"Returns_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 10)
        self.assertEqual(
            component_payload["data"]["title"],
            "პროდუქტისა და თანხის დაბრუნება",
        )
        self.assertEqual(
            component_payload["data"]["subtitle"],
            "ამ გვერდზე აღწერილია FlexDrive-ზე შეძენილი ავტონაწილების დაბრუნების მოთხოვნის ძირითადი წესი, ვადები, ნივთის მდგომარეობის მოთხოვნები და თანხის დაბრუნების პროცესი.",
        )
        self.assertEqual(component_payload["data"]["contentData"]["listcount"], 6)
        self.assertEqual(
            [item["title"] for item in items],
            [
                "დაბრუნების მოთხოვნის გაგზავნა",
                "ჩვეულებრივი დაბრუნების ვადა",
                "პროდუქტის მდგომარეობა",
                "დაზიანებული ან შეკვეთასთან შეუსაბამო პროდუქტი",
                "დაბრუნების ხარჯი",
                "თანხის დაბრუნება",
            ],
        )
        self.assertTrue(all(item["content_type"] == "returns_section" for item in items))
        self.assertTrue(all(item["editor"] for item in items))


class ReturnsFooterAPITests(APITestCase):
    def test_footer_endpoint_includes_returns_in_help_group(self):
        FooterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "brand_name": "AutoMate",
                "brand_description": "აქსესუარების მარტივი არჩევანი ერთ სივრცეში.",
                "email": "support@automate.ge",
            },
        )

        Page.objects.update_or_create(
            slug="delivery",
            defaults={
                "name": "მიწოდება",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.HELP,
                "footer_order": 10,
                "footer_label": "მიწოდება",
            },
        )
        Page.objects.update_or_create(
            slug="returns",
            defaults={
                "name": "დაბრუნება",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.HELP,
                "footer_order": 30,
                "footer_label": "დაბრუნება",
            },
        )

        response = self.client.get(reverse("footer"))

        self.assertEqual(response.status_code, 200)

        help_items = response.data["groups"]["help"]
        help_slugs = [item["slug"] for item in help_items]
        help_labels = {item["slug"]: item["label"] for item in help_items}

        self.assertIn("delivery", help_slugs)
        self.assertIn("returns", help_slugs)
        self.assertGreater(help_slugs.index("returns"), help_slugs.index("delivery"))
        self.assertEqual(help_labels["returns"], "დაბრუნება")
