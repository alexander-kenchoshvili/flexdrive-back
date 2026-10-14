from datetime import datetime, timezone

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework.test import APITestCase

from .models import BlogPost, Component, ComponentType, Content, ContentItem, Page
from .serializers import ContentItemSerializer


@override_settings(CACHE_ENABLED=False)
class BlogModificationDatesTests(APITestCase):
    def setUp(self):
        self.published = datetime(2026, 10, 10, 9, tzinfo=timezone.utc)
        self.older = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
        self.newer = datetime(2026, 10, 12, 9, tzinfo=timezone.utc)
        self.page, _ = Page.objects.get_or_create(slug="blogs", defaults={"name": "Blogs"})
        self.page.seo_noindex = False
        self.page.save(update_fields=["seo_noindex"])
        content, _ = Content.objects.get_or_create(name="bloglist")
        component_type, _ = ComponentType.objects.get_or_create(name="BlogDateList")
        Component.objects.create(page=self.page, content=content, component_type=component_type, enabled=True)
        self.item = ContentItem.objects.create(
            content=content, singlePageRoute=self.page, content_type="blogs",
            title="Article", slug="article", editor="<p>Original text</p>",
        )
        self.blog = BlogPost.objects.create(
            content_item=self.item, status="published", published_at=self.published,
        )
        self.path = f"/blogs/{self.item.pk}-article"
        self.payload = {"slug": "blogs", "single_id": self.item.pk, "single_slug": "article"}

    def set_dates(self, text_updated, metadata_updated):
        ContentItem.objects.filter(pk=self.item.pk).update(updated_at=text_updated)
        BlogPost.objects.filter(pk=self.blog.pk).update(updated_at=metadata_updated)

    def article_data(self):
        response = self.client.post(reverse("get-current-content"), self.payload, format="json")
        self.assertEqual(response.status_code, 200)
        return next(iter(response.data["secondary"].values()))["data"]

    def assert_public_dates(self, expected_modified, expected_published=None):
        expected_published = expected_published or self.published
        article = self.article_data()
        listing = self.client.get(reverse("blog-post-list"))
        self.assertEqual(listing.status_code, 200)
        listed = next(item for item in listing.data["results"] if item["id"] == self.item.pk)
        for data in (article, listed):
            self.assertEqual(parse_datetime(data["updated_at"]), expected_modified)
            self.assertEqual(parse_datetime(data["blog_meta"]["published_at"]), expected_published)
        sitemap = self.client.get(reverse("sitemap-entries"))
        self.assertEqual(sitemap.status_code, 200)
        entry = next(entry for entry in sitemap.data["entries"] if entry["loc"] == self.path)
        self.assertEqual(parse_datetime(entry["lastmod"]), expected_modified)
        self.blog.refresh_from_db()
        self.assertEqual(self.blog.published_at, expected_published)

    def test_newer_text_edit_reaches_article_listing_and_sitemap(self):
        self.set_dates(self.newer, self.older)
        self.assert_public_dates(self.newer)

    def test_newer_metadata_edit_reaches_article_listing_and_sitemap(self):
        self.set_dates(self.older, self.newer)
        self.assert_public_dates(self.newer)

    def test_legacy_missing_text_timestamp_uses_metadata_timestamp(self):
        self.set_dates(None, self.newer)
        self.assert_public_dates(self.newer)

    def test_publication_date_edit_is_preserved_separately(self):
        self.set_dates(self.older, self.newer)
        changed_publication = datetime(2026, 10, 9, 9, tzinfo=timezone.utc)
        self.blog.published_at = changed_publication
        self.blog.save()
        self.assert_public_dates(self.blog.updated_at, changed_publication)

    def test_non_blog_content_keeps_its_own_nullable_timestamp(self):
        content, _ = Content.objects.get_or_create(name="date-test-card")
        item = ContentItem.objects.create(content=content, title="Card")
        self.assertEqual(parse_datetime(ContentItemSerializer(item).data["updated_at"]), item.updated_at)
        item.updated_at = None
        self.assertIsNone(ContentItemSerializer(item).data["updated_at"])

    @override_settings(CACHE_ENABLED=True, CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "blog-date-tests",
    }})
    def test_saves_invalidate_cached_article_and_listing_dates(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.set_dates(self.older, self.older)
        self.assert_public_dates(self.older)
        self.assert_public_dates(self.older)
        with self.captureOnCommitCallbacks(execute=True):
            self.item.editor = "<p>Changed article text</p>"
            self.item.save()
        self.assert_public_dates(self.item.updated_at)
        with self.captureOnCommitCallbacks(execute=True):
            self.blog.excerpt = "Changed excerpt"
            self.blog.save()
        self.assert_public_dates(self.blog.updated_at)
