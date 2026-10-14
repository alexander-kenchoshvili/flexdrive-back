from io import BytesIO
from tempfile import TemporaryDirectory

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from catalog.admin import ProductImageAdminForm
from catalog.models import Category, Product, ProductImage
from pages.models import BlogPost, Component, ComponentType, Content, ContentItem, Page


def jxl_upload(filename="sample.jxl", mode="RGB", use_container=False):
    output = BytesIO()
    color = (30, 90, 150, 128) if mode == "RGBA" else (30, 90, 150)
    Image.new(mode, (64, 48), color).save(
        output, format="JXL", lossless=True, use_container=use_container
    )
    return SimpleUploadedFile(filename, output.getvalue(), content_type="image/jxl")


class JxlUploadValidationTests(SimpleTestCase):
    def test_django_accepts_real_jxl_and_uppercase_extension(self):
        for filename in ("sample.jxl", "sample.JXL"):
            for use_container in (False, True):
                with self.subTest(filename=filename, use_container=use_container):
                    upload = forms.ImageField().clean(
                        jxl_upload(filename, use_container=use_container)
                    )
                    self.assertEqual(upload.image.format, "JXL")
                    self.assertEqual(upload.image.size, (64, 48))
                    self.assertEqual(upload.tell(), 0)

    def test_django_accepts_jxl_with_transparency(self):
        upload = forms.ImageField().clean(jxl_upload(mode="RGBA"))
        self.assertEqual(upload.image.mode, "RGBA")

    def test_model_image_extension_validator_accepts_jxl(self):
        upload = jxl_upload()
        ProductImage._meta.get_field("image_original").run_validators(upload)

    def test_invalid_and_truncated_jxl_are_rejected(self):
        valid_bytes = jxl_upload().read()
        for content in (b"not an image", valid_bytes[:16]):
            with self.subTest(content=content):
                upload = SimpleUploadedFile("broken.jxl", content, "image/jxl")
                with self.assertRaises(ValidationError) as caught:
                    forms.ImageField().clean(upload)
                self.assertEqual(caught.exception.code, "invalid_image")


class JxlWebpConversionTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(
            MEDIA_ROOT=self.media.name,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def assert_webp(self, image_field, size=None):
        self.assertTrue(image_field.name.endswith(".webp"))
        image_field.open("rb")
        try:
            with Image.open(image_field) as image:
                image.load()
                self.assertEqual(image.format, "WEBP")
                if size is not None:
                    self.assertEqual(image.size, size)
        finally:
            image_field.close()

    def test_product_admin_form_saves_jxl_and_generates_webp_variants(self):
        category = Category.objects.create(name="Parts", slug="parts")
        product = Product.objects.create(
            category=category, name="Part", slug="part", sku="JXL-TEST", price=10
        )
        form = ProductImageAdminForm(
            data={"product": product.pk, "sort_order": 0, "image_padding": 12},
            files={"image_original": jxl_upload()},
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        image = form.save()
        image.refresh_from_db()
        # Original preservation and variant sizes match the existing workflow.
        self.assertTrue(image.image_original.name.endswith(".jxl"))
        for field_name, (size, _) in image.STANDARDIZED_VARIANT_SPECS.items():
            self.assert_webp(getattr(image, field_name), size)

    def test_category_jxl_original_generates_webp_variants(self):
        category = Category.objects.create(
            name="Parts", slug="parts", image_original=jxl_upload()
        )
        for field_name, (size, _) in category.STANDARDIZED_VARIANT_SPECS.items():
            self.assert_webp(getattr(category, field_name), size)

    def test_component_jxl_converts_to_webp_and_preserves_alpha(self):
        component = Component.objects.create(
            page=Page.objects.create(name="Home", slug="home"),
            component_type=ComponentType.objects.create(name="Hero"),
            image_desktop=jxl_upload(mode="RGBA"),
        )
        self.assert_webp(component.image_desktop, (64, 48))
        component.image_desktop.open("rb")
        try:
            with Image.open(component.image_desktop) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 128)
        finally:
            component.image_desktop.close()

    def test_blog_jxl_originals_generate_webp_variants(self):
        item = ContentItem.objects.create(
            content=Content.objects.create(name="bloglist"), title="Blog"
        )
        blog = BlogPost.objects.create(
            content_item=item,
            teaser_image_original=jxl_upload("teaser.jxl"),
            cover_image_original=jxl_upload("cover.jxl"),
        )
        for prefix in ("teaser", "cover"):
            specs = (
                blog.TEASER_VARIANT_SPECS
                if prefix == "teaser"
                else blog.COVER_VARIANT_SPECS
            )
            for device in ("desktop", "tablet", "mobile"):
                field_name = f"{prefix}_image_{device}"
                self.assert_webp(getattr(blog, field_name), specs[field_name][0])
