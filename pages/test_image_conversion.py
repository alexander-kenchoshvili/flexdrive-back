from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from pages.models import BlogPost, Component, ComponentType, Content, ContentItem, Page
from pages.serializers import ContentItemSerializer


def _generate_test_image(filename="sample.jpg", color=(255, 0, 0), size=(100, 100)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


class PageImageConversionTests(TestCase):
    def setUp(self):
        self.test_media_root = Path.cwd() / "test_media_tmp"
        self.test_media_root.mkdir(exist_ok=True)
        self.override = override_settings(
            MEDIA_ROOT=self.test_media_root,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {
                        "location": self.test_media_root,
                        "base_url": "/media/",
                    },
                },
                "staticfiles": {
                    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                },
            },
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_component_mixin_converts_uploaded_image_to_webp(self):
        page = Page.objects.create(name="Home", slug="home")
        component_type = ComponentType.objects.create(name="Hero")

        component = Component.objects.create(
            page=page,
            component_type=component_type,
            title="Hero",
            image_desktop=_generate_test_image("hero.jpg"),
        )

        self.assertTrue(component.image_desktop.name.endswith(".webp"))

    def test_blog_cover_conversion_still_saves_webp(self):
        content = Content.objects.create(name="bloglist")
        item = ContentItem.objects.create(
            content=content,
            title="Blog item",
            image_desktop=_generate_test_image("content.jpg", color=(0, 255, 0)),
        )

        blog_post = BlogPost.objects.create(
            content_item=item,
            cover_image_desktop=_generate_test_image("cover.jpg", color=(0, 0, 255)),
        )

        self.assertTrue(blog_post.cover_image_desktop.name.endswith(".webp"))

    def test_blog_original_teaser_generates_all_variants_and_serializer_uses_them(self):
        content = Content.objects.create(name="bloglist")
        item = ContentItem.objects.create(
            content=content,
            title="Blog item",
            image_desktop=_generate_test_image("legacy-content.jpg", color=(0, 255, 0)),
        )

        blog_post = BlogPost.objects.create(
            content_item=item,
            teaser_image_original=_generate_test_image(
                "teaser-original.jpg",
                color=(255, 200, 0),
                size=(1800, 1200),
            ),
        )

        blog_post.refresh_from_db()

        self.assertTrue(blog_post.teaser_image_desktop.name.endswith(".webp"))
        self.assertTrue(blog_post.teaser_image_tablet.name.endswith(".webp"))
        self.assertTrue(blog_post.teaser_image_mobile.name.endswith(".webp"))

        serialized = ContentItemSerializer(item, context={"request": None}).data
        self.assertIn("teaser-desktop.webp", serialized["image"]["desktop"])
        self.assertIn("teaser-desktop.webp", serialized["blog_meta"]["teaser_image"]["desktop"])
        self.assertIn("teaser-desktop.webp", serialized["blog_meta"]["cover_image"]["desktop"])

    def test_blog_original_cover_generates_all_variants(self):
        content = Content.objects.create(name="bloglist")
        item = ContentItem.objects.create(
            content=content,
            title="Blog item",
        )

        blog_post = BlogPost.objects.create(
            content_item=item,
            cover_image_original=_generate_test_image(
                "cover-original.jpg",
                color=(0, 0, 255),
                size=(2200, 1400),
            ),
        )

        blog_post.refresh_from_db()

        self.assertTrue(blog_post.cover_image_desktop.name.endswith(".webp"))
        self.assertTrue(blog_post.cover_image_tablet.name.endswith(".webp"))
        self.assertTrue(blog_post.cover_image_mobile.name.endswith(".webp"))
