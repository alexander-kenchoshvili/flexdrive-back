from django.urls import reverse
from rest_framework.test import APITestCase

from pages.models import Component, FooterSettings, Page


class PaymentMethodsPageAPITests(APITestCase):
    def test_payment_methods_page_includes_seeded_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "payment-methods"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="payment-methods",
            component_type__name="PaymentMethods",
        )
        component_key = f"PaymentMethods_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 10)
        self.assertEqual(
            component_payload["data"]["title"],
            "გადახდის მეთოდები",
        )
        self.assertEqual(
            component_payload["data"]["subtitle"],
            "FlexDrive-ზე შეკვეთის გადახდა ხდება checkout-ში ნაჩვენები აქტიური მეთოდით. საბოლოო თანხა, გადახდის პირობები და შესაძლო დამატებითი ხარჯი მომხმარებელს შეკვეთის დადასტურებამდე ეჩვენება.",
        )
        self.assertEqual(component_payload["data"]["contentData"]["listcount"], 4)
        self.assertEqual(
            [item["title"] for item in items],
            [
                "ხელმისაწვდომი მეთოდები",
                "ნაღდი ანგარიშსწორება",
                "ონლაინ გადახდა",
                "გაუქმება და თანხის დაბრუნება",
            ],
        )
        self.assertTrue(
            all(item["content_type"] == "payment_method_section" for item in items)
        )
        self.assertTrue(all(item["editor"] for item in items))


class PaymentMethodsFooterAPITests(APITestCase):
    def test_footer_endpoint_includes_payment_methods_between_delivery_and_returns(self):
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
            slug="payment-methods",
            defaults={
                "name": "გადახდის მეთოდები",
                "show_in_footer": True,
                "footer_group": Page.FooterGroup.HELP,
                "footer_order": 20,
                "footer_label": "გადახდის მეთოდები",
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
        self.assertEqual(
            [item["slug"] for item in response.data["groups"]["help"][:3]],
            ["delivery", "payment-methods", "returns"],
        )
        self.assertEqual(
            [item["label"] for item in response.data["groups"]["help"][:3]],
            ["მიწოდება", "გადახდის მეთოდები", "დაბრუნება"],
        )
