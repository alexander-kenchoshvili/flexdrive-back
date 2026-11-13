from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings

from pages.models import Component, ComponentType, Content, ContentItem, LaunchControl, Page


@override_settings(STOREFRONT_ACCESS_GUARD_ENABLED=True)
class PublicLegalInformationTests(TestCase):
    def setUp(self):
        self.control, _ = LaunchControl.objects.update_or_create(
            pk=1, defaults={"public_open": False, "preview_version": 1},
        )
        for slug, component_type, item_type in (
            ("privacy-policy", "PrivacyPolicy", "policy_section"),
            ("terms", "Terms", "terms_section"),
        ):
            page, _ = Page.objects.get_or_create(slug=slug, defaults={"name": slug})
            page.components.all().delete()
            content = Content.objects.create(name=f"launch-legal-test-{slug}")
            kind, _ = ComponentType.objects.get_or_create(name=component_type)
            Component.objects.create(page=page, component_type=kind, content=content, title=f"Legal {slug}", subtitle="Existing policy")
            ContentItem.objects.create(content=content, content_type=item_type, title="First", editor='<p>Public policy <a href="/terms">Terms</a></p><script>bad()</script>', position=1)
            ContentItem.objects.create(content=content, content_type=item_type, title="Second", description="Plain <unsafe> text", position=2)
            ContentItem.objects.create(content=content, content_type="product", title="PRIVATE PRODUCT", editor="hidden")

    def test_exact_two_documents_are_safe_public_reads_without_unlocking(self):
        for slug in ("privacy-policy", "terms"):
            url = f"/api/launch/information/{slug}/"
            response = self.client.get(url, {"slug": "catalog", "content_id": 1})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["slug"], slug)
            self.assertEqual([s["title"] for s in data["sections"]], ["First", "Second"])
            self.assertIn('<a href="/terms">', data["sections"][0]["html"])
            self.assertNotIn("<script", response.content.decode())
            self.assertIn("&lt;unsafe&gt;", data["sections"][1]["html"])
            self.assertNotIn("PRIVATE PRODUCT", response.content.decode())
            self.assertEqual(set(data), {"slug", "title", "intro", "sections"})
            self.assertIn("no-store", response["Cache-Control"])
            self.assertFalse(response.cookies)
            self.assertEqual(self.client.head(url).status_code, 200)
        self.control.refresh_from_db()
        self.assertFalse(self.control.public_open)
        self.assertEqual(self.control.preview_version, 1)

    def test_general_cms_and_near_matches_and_mutations_stay_blocked(self):
        for url in (
            "/api/pages/privacy-policy/", "/api/pages/terms/", "/api/pages/getCurrentContent/?slug=terms",
            "/api/catalog/", "/api/accounts/session/", "/api/pages/site-settings/",
            "/api/launch/information/catalog/", "/api/launch/information/terms/extra/",
            "/api/launch/information/Terms/",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.json()["code"], "storefront_not_open")
        for method in (self.client.post, self.client.put, self.client.delete, self.client.options):
            response = method("/api/launch/information/terms/")
            self.assertEqual(response.status_code, 403)

    def test_disabled_and_unrelated_components_are_not_published(self):
        page = Page.objects.get(slug="terms")
        page.components.update(enabled=False)
        other, _ = ComponentType.objects.get_or_create(name="Catalog")
        Component.objects.create(page=page, component_type=other, title="PRIVATE COMPONENT")
        response = self.client.get("/api/launch/information/terms/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"PRIVATE", response.content)

    def test_database_failure_returns_no_internal_details(self):
        with patch("pages.public_information.Component.objects.filter", side_effect=DatabaseError("private database details")):
            response = self.client.get("/api/launch/information/terms/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"code": "information_unavailable"})
