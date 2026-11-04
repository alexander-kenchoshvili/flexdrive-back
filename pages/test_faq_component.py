from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.urls import reverse
from rest_framework.test import APITestCase

from pages.models import Component, ContentItem, Page


class HomepageFaqTests(APITestCase):
    def test_homepage_has_editable_faq_with_no_published_sample_answers(self):
        response = self.client.post(reverse("get-current-content"), {"slug": "main"}, format="json")
        self.assertEqual(response.status_code, 200)
        component = Component.objects.get(page__slug="main", component_type__name="Faq")
        payload = response.data["secondary"][f"Faq_{component.pk}"]
        self.assertEqual(payload["conf"]["componentName"], "Faq")
        self.assertEqual(payload["data"]["contentData"]["name"], "faq_questions")
        self.assertEqual(payload["data"]["contentData"]["list"], [])
        self.assertTrue(component.enabled)

    def test_admin_question_order_and_updates_reach_existing_homepage_api(self):
        component = Component.objects.get(page__slug="main", component_type__name="Faq")
        ContentItem.objects.create(content=component.content, title="Question B", description="Answer B", position=20)
        item = ContentItem.objects.create(content=component.content, title="Question A", description="Answer A", position=10)
        response = self.client.post(reverse("get-current-content"), {"slug": "main"}, format="json")
        payload = response.data["secondary"][f"Faq_{component.pk}"]
        self.assertEqual([row["title"] for row in payload["data"]["contentData"]["list"]], ["Question A", "Question B"])
        component.title = "Admin title"
        component.enabled = False
        component.save()
        migration = import_module("pages.migrations.0080_seed_homepage_faq")
        migration.seed_homepage_faq(apps, SimpleNamespace(connection=connection))
        component.refresh_from_db()
        self.assertEqual(component.title, "Admin title")
        self.assertFalse(component.enabled)
        self.assertTrue(ContentItem.objects.filter(pk=item.pk, description="Answer A").exists())
        self.assertEqual(Component.objects.filter(page__slug="main", component_type__name="Faq").count(), 1)

    def test_removed_faq_page_returns_404(self):
        self.assertFalse(Page.objects.filter(slug="faq").exists())
        response = self.client.post(reverse("get-current-content"), {"slug": "faq"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_page_cleanup_refuses_to_remove_linked_content(self):
        page = Page.objects.create(slug="faq", name="FAQ")
        child = Page.objects.create(slug="faq-child", name="Child", parent=page)
        migration = import_module("pages.migrations.0080_seed_homepage_faq")
        with self.assertRaises(RuntimeError):
            migration.seed_homepage_faq(apps, SimpleNamespace(connection=connection))
        self.assertTrue(Page.objects.filter(pk=page.pk).exists())
        self.assertTrue(Page.objects.filter(pk=child.pk, parent=page).exists())
