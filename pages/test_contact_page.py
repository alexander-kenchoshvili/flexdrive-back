from collections import Counter
from unittest.mock import patch

from django.core import mail
from django.urls import reverse
from rest_framework.test import APITestCase

from pages.models import Component, ContactInquiry, FooterSettings


class ContactPageAPITests(APITestCase):
    def test_contact_page_includes_seeded_component(self):
        response = self.client.post(
            reverse("get-current-content"),
            {"slug": "contact"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        component = Component.objects.get(
            page__slug="contact",
            component_type__name="Contact",
        )
        component_key = f"Contact_{component.id}"
        component_payload = response.data["secondary"][component_key]
        items = component_payload["data"]["contentData"]["list"]

        self.assertEqual(component.position, 10)
        self.assertIsNone(component_payload["data"]["title"])
        self.assertEqual(component_payload["data"]["contentData"]["listcount"], 20)
        self.assertEqual(
            Counter(item["content_type"] for item in items),
            {
                "contact_topic": 5,
                "contact_notice": 5,
                "contact_shortcut": 4,
                "contact_expectation": 3,
                "contact_reason": 3,
            },
        )
        self.assertEqual(
            [item["slug"] for item in items if item["content_type"] == "contact_topic"],
            ["product", "order-status", "delivery", "returns", "other"],
        )

    @patch("pages.contact_views.validate_recaptcha", return_value=True)
    def test_contact_inquiry_create_saves_record_and_sends_email(self, mocked_recaptcha):
        FooterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "brand_name": "AutoMate",
                "email": "support@automate.ge",
            },
        )

        response = self.client.post(
            reverse("contact-inquiry-create"),
            {
                "full_name": "áƒáƒœáƒ áƒ‘áƒ”áƒ áƒ˜áƒ«áƒ”",
                "phone": "+995555123456",
                "email": "ana@example.com",
                "topic_slug": "delivery",
                "order_number": "AM-1024",
                "message": "áƒ›áƒ˜áƒœáƒ“áƒ áƒ¡áƒ¢áƒáƒ¢áƒ£áƒ¡áƒ˜áƒ¡ áƒ“áƒáƒ–áƒ£áƒ¡áƒ¢áƒ”áƒ‘áƒ.",
                "recaptcha_token": "valid-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactInquiry.objects.count(), 1)
        inquiry = ContactInquiry.objects.get()
        self.assertTrue(inquiry.topic_label)
        self.assertEqual(inquiry.status, "new")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["support@automate.ge"])
        self.assertEqual(mail.outbox[0].reply_to, ["ana@example.com"])
        mocked_recaptcha.assert_called_once()

    @patch("pages.contact_views.validate_recaptcha", return_value=True)
    def test_contact_inquiry_rejects_invalid_topic_slug(self, mocked_recaptcha):
        response = self.client.post(
            reverse("contact-inquiry-create"),
            {
                "full_name": "áƒáƒœáƒ áƒ‘áƒ”áƒ áƒ˜áƒ«áƒ”",
                "phone": "+995555123456",
                "email": "ana@example.com",
                "topic_slug": "not-existing",
                "message": "áƒ“áƒáƒ®áƒ›áƒáƒ áƒ”áƒ‘áƒ áƒ›áƒ­áƒ˜áƒ áƒ“áƒ”áƒ‘áƒ.",
                "recaptcha_token": "valid-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("topic_slug", response.data)
        self.assertEqual(ContactInquiry.objects.count(), 0)
        mocked_recaptcha.assert_not_called()

    def test_contact_inquiry_requires_mandatory_fields(self):
        response = self.client.post(
            reverse("contact-inquiry-create"),
            {
                "full_name": "",
                "phone": "",
                "email": "",
                "topic_slug": "",
                "message": "",
                "recaptcha_token": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("full_name", response.data)
        self.assertIn("phone", response.data)
        self.assertIn("email", response.data)
        self.assertIn("topic_slug", response.data)
        self.assertIn("message", response.data)
        self.assertIn("recaptcha_token", response.data)

    @patch("pages.contact_views.validate_recaptcha", return_value=False)
    def test_contact_inquiry_rejects_failed_recaptcha(self, mocked_recaptcha):
        response = self.client.post(
            reverse("contact-inquiry-create"),
            {
                "full_name": "áƒáƒœáƒ áƒ‘áƒ”áƒ áƒ˜áƒ«áƒ”",
                "phone": "+995555123456",
                "email": "ana@example.com",
                "topic_slug": "delivery",
                "message": "áƒ“áƒáƒ®áƒ›áƒáƒ áƒ”áƒ‘áƒ áƒ›áƒ­áƒ˜áƒ áƒ“áƒ”áƒ‘áƒ.",
                "recaptcha_token": "bad-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)
        self.assertEqual(ContactInquiry.objects.count(), 0)
        mocked_recaptcha.assert_called_once()




