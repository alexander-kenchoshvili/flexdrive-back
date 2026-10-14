from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase, APIRequestFactory

from common.cache_utils import CACHE_GROUP_PAGES_CONTENT, _build_request_fingerprint, _cache_key
from .models import BlogPost, Component, ComponentType, Content, ContentItem, Page
from .views import GetCurrentContentAPIView


@override_settings(CACHE_ENABLED=False)
class CanonicalContentRoutesTests(APITestCase):
    def setUp(self):
        self.page, _ = Page.objects.get_or_create(slug="blogs", defaults={"name": "Blogs"})
        self.page.seo_noindex = False
        self.page.save(update_fields=["seo_noindex"])
        content, _ = Content.objects.get_or_create(name="bloglist")
        component_type, _ = ComponentType.objects.get_or_create(name="CanonicalBlogList")
        Component.objects.create(page=self.page, content=content, component_type=component_type, enabled=True)
        self.item = ContentItem.objects.create(
            content=content, singlePageRoute=self.page, content_type="blogs",
            title="Real article", slug="real-article", editor="<p>Article text</p>",
        )
        self.blog = BlogPost.objects.create(content_item=self.item, status="published")
        self.url = reverse("get-current-content")
        self.path = f"/blogs/{self.item.pk}-real-article"

    def post(self, **overrides):
        payload = {"slug": "blogs", "single_id": self.item.pk, "single_slug": "real-article"}
        payload.update(overrides)
        return self.client.post(self.url, payload, format="json")

    def test_real_article_url_matches_its_seo_and_sitemap(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["seo"]["canonical"], self.path)
        self.assertIsNone(response.data["canonical_path"])
        sitemap = self.client.get(reverse("sitemap-entries"))
        self.assertIn(self.path, [entry["loc"] for entry in sitemap.data["entries"]])

    def test_wrong_existing_and_invented_prefixes_are_404(self):
        for prefix in ("contact", "invented-prefix", "blogs/extra", "", None, "/blogs", "blogs/"):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.post(slug=prefix).status_code, 404)

    def test_old_slug_under_real_prefix_returns_the_real_redirect_path(self):
        response = self.post(single_slug="old-article-title")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["canonical_path"], self.path)
        self.assertEqual(response.data["seo"]["canonical"], self.path)

    def test_content_type_is_authoritative_when_route_page_differs(self):
        self.item.content_type = "articles"
        self.item.save(update_fields=["content_type"])
        response = self.post(slug="articles")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["seo"]["canonical"], f"/articles/{self.item.pk}-real-article")
        self.assertEqual(self.post(slug="blogs").status_code, 404)

    def test_saved_route_page_is_fallback_for_missing_content_type(self):
        self.item.content_type = ""
        self.item.save(update_fields=["content_type"])
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post(slug="invented-prefix").status_code, 404)

    def test_draft_and_missing_articles_remain_404(self):
        self.blog.status = "draft"
        self.blog.save(update_fields=["status"])
        self.assertEqual(self.post().status_code, 404)
        self.assertEqual(self.post(single_id=999999).status_code, 404)
        self.assertEqual(self.post(single_id="invalid-id").status_code, 404)

    def test_parent_noindex_still_applies_and_excludes_article_from_sitemap(self):
        self.page.seo_noindex = True
        self.page.save(update_fields=["seo_noindex"])
        response = self.post()
        self.assertTrue(response.data["seo"]["noindex"])
        sitemap = self.client.get(reverse("sitemap-entries"))
        self.assertNotIn(self.path, [entry["loc"] for entry in sitemap.data["entries"]])

    @override_settings(CACHE_ENABLED=True, CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "canonical-route-tests",
    }})
    def test_old_cached_alias_cannot_bypass_route_validation(self):
        cache.clear()
        self.addCleanup(cache.clear)
        payload = {"slug": "invented-prefix", "single_id": self.item.pk, "single_slug": "real-article"}
        raw = APIRequestFactory().post(self.url, payload, format="json")
        request = GetCurrentContentAPIView().initialize_request(raw)
        fingerprint = _build_request_fingerprint(request, {}, True)
        cache.set(_cache_key(CACHE_GROUP_PAGES_CONTENT, fingerprint), {
            "data": {"seo": {"canonical": f"/invented-prefix/{self.item.pk}-real-article"}}, "status": 200,
        }, timeout=60)
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 404)
        first, second = self.post(), self.post()
        self.assertEqual(first.headers["X-Cache-Status"], "MISS")
        self.assertEqual(second.headers["X-Cache-Status"], "HIT")
        with self.captureOnCommitCallbacks(execute=True):
            self.item.title = "Updated article"
            self.item.save(update_fields=["title"])
        refreshed = self.post()
        self.assertEqual(refreshed.headers["X-Cache-Status"], "MISS")
        self.assertEqual(next(iter(refreshed.data["secondary"].values()))["data"]["title"], "Updated article")
