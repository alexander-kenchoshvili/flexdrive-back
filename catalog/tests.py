from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models import Q
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Category, Product, ProductImage, ProductSpec, ProductStatus


def _generate_test_image(filename="sample.jpg", color=(255, 0, 0), size=(100, 100)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


class CatalogAPITests(APITestCase):
    def setUp(self):
        Product.objects.all().delete()
        Category.objects.all().delete()

        self.interior = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.exterior = Category.objects.create(name="Exterior", slug="exterior", sort_order=2)

        self.products = []
        for i in range(12):
            product = Product.objects.create(
                category=self.interior,
                name=f"Product {i}",
                slug=f"product-{i}",
                sku=f"SKU-{i}",
                short_description="Short description",
                description="Long description",
                price=Decimal("10.00") + Decimal(i),
                old_price=Decimal("20.00") + Decimal(i) if i % 2 == 0 else None,
                stock_qty=5 if i % 3 else 0,
                is_new=i < 5,
                is_featured=i in (1, 3, 5),
                status=ProductStatus.PUBLISHED,
            )
            self.products.append(product)

        Product.objects.create(
            category=self.exterior,
            name="Draft Product",
            slug="draft-product",
            sku="SKU-DRAFT",
            price=Decimal("30.00"),
            stock_qty=10,
            status=ProductStatus.DRAFT,
        )

        target = self.products[0]
        ProductSpec.objects.create(product=target, key="Material", value="ABS", sort_order=1)
        ProductSpec.objects.create(product=target, key="Color", value="Black", sort_order=2)
        ProductImage.objects.create(
            product=target,
            image_desktop=_generate_test_image("detail-secondary.jpg", color=(0, 255, 0)),
            is_primary=False,
            sort_order=1,
            alt_text="Secondary test image",
        )
        ProductImage.objects.create(
            product=target,
            image_desktop=_generate_test_image("detail.jpg"),
            is_primary=True,
            sort_order=2,
            alt_text="Primary test image",
        )

    def test_products_list_default_pagination(self):
        response = self.client.get(reverse("catalog-product-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 12)
        self.assertEqual(response.data["current_page"], 1)
        self.assertEqual(response.data["total_pages"], 2)
        self.assertEqual(len(response.data["results"]), 9)

    def test_products_list_second_page(self):
        response = self.client.get(reverse("catalog-product-list"), {"page": 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 3)

    def test_products_filter_on_sale(self):
        response = self.client.get(reverse("catalog-product-list"), {"on_sale": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
        for row in response.data["results"]:
            self.assertTrue(row["on_sale"])

    def test_product_suggestions_require_minimum_query_length(self):
        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "c"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_product_suggestions_return_dropdown_ready_results(self):
        suggested = Product.objects.create(
            category=self.interior,
            name="Fast Charger",
            slug="fast-charger",
            sku="CHARGER-01",
            short_description="Quick charge adapter",
            description="Fast charger for cars",
            price=Decimal("49.00"),
            stock_qty=7,
            is_featured=True,
            status=ProductStatus.PUBLISHED,
        )
        Product.objects.create(
            category=self.interior,
            name="Draft Charger",
            slug="draft-charger",
            sku="CHARGER-DRAFT",
            price=Decimal("59.00"),
            stock_qty=4,
            status=ProductStatus.DRAFT,
        )
        ProductImage.objects.create(
            product=suggested,
            image_desktop=_generate_test_image("fast-charger.jpg", color=(25, 25, 25)),
            is_primary=True,
            sort_order=1,
            alt_text="Fast Charger image",
        )

        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "charger"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "fast-charger")
        self.assertEqual(response.data[0]["category"]["slug"], "interior")
        self.assertEqual(response.data[0]["primary_image"]["alt_text"], "Fast Charger image")
        self.assertTrue(response.data[0]["in_stock"])

    def test_product_suggestions_limit_results_to_five(self):
        for index in range(6):
            Product.objects.create(
                category=self.interior,
                name=f"Charger Result {index}",
                slug=f"charger-result-{index}",
                sku=f"CHARGER-{index}",
                short_description="Charger",
                description="Charger description",
                price=Decimal("15.00") + Decimal(index),
                stock_qty=2,
                status=ProductStatus.PUBLISHED,
            )

        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "charger"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)

    def test_product_detail_returns_gallery_and_specs(self):
        product = self.products[0]
        response = self.client.get(reverse("catalog-product-detail", kwargs={"slug": product.slug}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], product.id)
        self.assertEqual(len(response.data["images"]), 2)
        self.assertEqual(response.data["images"][0]["alt_text"], "Secondary test image")
        self.assertEqual(response.data["primary_image"]["alt_text"], "Primary test image")
        self.assertEqual(len(response.data["specs"]), 2)
        self.assertEqual(response.data["specs"][0]["key"], "Material")
        self.assertIn("related_products", response.data)

    def test_product_detail_returns_empty_related_products_when_no_matches_exist(self):
        solo_category = Category.objects.create(name="Audio", slug="audio", sort_order=3)
        product = Product.objects.create(
            category=solo_category,
            name="Solo Product",
            slug="solo-product",
            sku="SOLO-1",
            short_description="Only product in this category",
            description="Only product in this category",
            price=Decimal("99.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )

        response = self.client.get(reverse("catalog-product-detail", kwargs={"slug": product.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["related_products"], [])

    def test_product_detail_returns_related_products_in_expected_order(self):
        related_category = Category.objects.create(name="Adapters", slug="adapters", sort_order=4)
        product = Product.objects.create(
            category=related_category,
            name="Current Adapter",
            slug="current-adapter",
            sku="CUR-1",
            short_description="Current adapter",
            description="Current adapter",
            price=Decimal("39.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )

        featured_in_older = Product.objects.create(
            category=related_category,
            name="Featured In Older",
            slug="featured-in-older",
            sku="REL-1",
            price=Decimal("40.00"),
            stock_qty=5,
            is_featured=True,
            status=ProductStatus.PUBLISHED,
        )
        featured_in_newer = Product.objects.create(
            category=related_category,
            name="Featured In Newer",
            slug="featured-in-newer",
            sku="REL-2",
            price=Decimal("41.00"),
            stock_qty=7,
            is_featured=True,
            status=ProductStatus.PUBLISHED,
        )
        featured_out = Product.objects.create(
            category=related_category,
            name="Featured Out",
            slug="featured-out",
            sku="REL-3",
            price=Decimal("42.00"),
            stock_qty=0,
            is_featured=True,
            status=ProductStatus.PUBLISHED,
        )
        regular_in_older = Product.objects.create(
            category=related_category,
            name="Regular In Older",
            slug="regular-in-older",
            sku="REL-4",
            price=Decimal("43.00"),
            stock_qty=4,
            is_featured=False,
            status=ProductStatus.PUBLISHED,
        )
        regular_in_newer = Product.objects.create(
            category=related_category,
            name="Regular In Newer",
            slug="regular-in-newer",
            sku="REL-5",
            price=Decimal("44.00"),
            stock_qty=6,
            is_featured=False,
            status=ProductStatus.PUBLISHED,
        )
        Product.objects.create(
            category=related_category,
            name="Regular Out",
            slug="regular-out",
            sku="REL-6",
            price=Decimal("45.00"),
            stock_qty=0,
            is_featured=False,
            status=ProductStatus.PUBLISHED,
        )
        Product.objects.create(
            category=related_category,
            name="Interior Draft",
            slug="interior-draft",
            sku="REL-DRAFT",
            price=Decimal("46.00"),
            stock_qty=10,
            is_featured=True,
            status=ProductStatus.DRAFT,
        )
        Product.objects.create(
            category=self.exterior,
            name="Exterior Published",
            slug="exterior-published",
            sku="REL-EXT",
            price=Decimal("47.00"),
            stock_qty=10,
            is_featured=True,
            status=ProductStatus.PUBLISHED,
        )

        for image_product in (
            featured_in_older,
            featured_in_newer,
            featured_out,
            regular_in_older,
            regular_in_newer,
        ):
            ProductImage.objects.create(
                product=image_product,
                image_desktop=_generate_test_image(f"{image_product.slug}.jpg"),
                is_primary=True,
                sort_order=1,
                alt_text=f"{image_product.name} image",
            )

        response = self.client.get(reverse("catalog-product-detail", kwargs={"slug": product.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["related_products"]), 4)
        self.assertEqual(
            [item["slug"] for item in response.data["related_products"]],
            [
                "featured-in-newer",
                "featured-in-older",
                "featured-out",
                "regular-in-newer",
            ],
        )
        self.assertNotIn(product.slug, [item["slug"] for item in response.data["related_products"]])
        self.assertNotIn("interior-draft", [item["slug"] for item in response.data["related_products"]])
        self.assertNotIn("exterior-published", [item["slug"] for item in response.data["related_products"]])
        self.assertEqual(
            response.data["related_products"][0]["primary_image"]["alt_text"],
            "Featured In Newer image",
        )

    def test_product_detail_returns_404_for_draft_product(self):
        response = self.client.get(reverse("catalog-product-detail", kwargs={"slug": "draft-product"}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_detail_returns_404_for_archived_product(self):
        archived = Product.objects.create(
            category=self.interior,
            name="Archived Product",
            slug="archived-product",
            sku="SKU-ARCHIVED",
            price=Decimal("32.00"),
            stock_qty=2,
            status=ProductStatus.ARCHIVED,
        )

        response = self.client.get(reverse("catalog-product-detail", kwargs={"slug": archived.slug}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_detail_returns_404_for_missing_slug(self):
        response = self.client.get(reverse("catalog-product-detail", kwargs={"slug": "missing-product"}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_category_list_returns_counts(self):
        response = self.client.get(reverse("catalog-category-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "interior")
        self.assertEqual(response.data[0]["product_count"], 12)
        self.assertIn("image", response.data[0])


class SeedCatalogCommandTests(TestCase):
    def test_seed_catalog_creates_products_specs_and_images(self):
        call_command("seed_catalog", count=5, with_images=True, reset=True, seed=123)

        self.assertEqual(Product.objects.filter(sku__startswith="FAKE-").count(), 5)
        self.assertGreaterEqual(Category.objects.count(), 5)
        self.assertGreater(ProductSpec.objects.count(), 0)
        self.assertTrue(
            ProductImage.objects.filter(
                Q(image_desktop__isnull=False)
                | Q(image_tablet__isnull=False)
                | Q(image_mobile__isnull=False)
            ).exists()
        )


class ProductImageNormalizationTests(TestCase):
    def setUp(self):
        Product.objects.all().delete()
        Category.objects.all().delete()

        self.category = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.product = Product.objects.create(
            category=self.category,
            name="Organizer",
            slug="organizer",
            sku="ORG-1",
            short_description="Organizer",
            description="Organizer description",
            price=Decimal("99.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )

    def test_original_upload_generates_standardized_webp_variants(self):
        image = ProductImage.objects.create(
            product=self.product,
            image_original=_generate_test_image(
                "organizer-original.jpg",
                color=(15, 25, 35),
                size=(1600, 900),
            ),
            is_primary=True,
            sort_order=1,
            alt_text="Organizer image",
        )

        image.refresh_from_db()

        self.assertTrue(image.image_original.name.endswith(".jpg"))
        self.assertTrue(image.image_desktop.name.endswith(".webp"))
        self.assertTrue(image.image_tablet.name.endswith(".webp"))
        self.assertTrue(image.image_mobile.name.endswith(".webp"))

        with Image.open(image.image_desktop) as desktop:
            self.assertEqual(desktop.size, (1440, 1440))
            self.assertEqual(desktop.format, "WEBP")

        with Image.open(image.image_tablet) as tablet:
            self.assertEqual(tablet.size, (1080, 1080))
            self.assertEqual(tablet.format, "WEBP")

        with Image.open(image.image_mobile) as mobile:
            self.assertEqual(mobile.size, (720, 720))
            self.assertEqual(mobile.format, "WEBP")

    def test_legacy_manual_variant_upload_still_converts_to_webp(self):
        image = ProductImage.objects.create(
            product=self.product,
            image_desktop=_generate_test_image("organizer-desktop.jpg"),
            is_primary=True,
            sort_order=1,
            alt_text="Legacy organizer image",
        )

        image.refresh_from_db()

        self.assertFalse(bool(image.image_original))
        self.assertTrue(image.image_desktop.name.endswith(".webp"))

        with Image.open(image.image_desktop) as desktop:
            self.assertEqual(desktop.format, "WEBP")


class CategoryImageNormalizationTests(TestCase):
    def setUp(self):
        Category.objects.all().delete()

    def test_original_upload_generates_standardized_webp_variants(self):
        category = Category.objects.create(
            name="Brake System",
            slug="brake-system",
            sort_order=1,
            image_original=_generate_test_image(
                "brake-system.jpg",
                color=(25, 35, 45),
                size=(1600, 900),
            ),
            image_alt_text="Brake parts",
        )

        category.refresh_from_db()

        self.assertTrue(category.image_original.name.endswith(".jpg"))
        self.assertTrue(category.image_desktop.name.endswith(".webp"))
        self.assertTrue(category.image_tablet.name.endswith(".webp"))
        self.assertTrue(category.image_mobile.name.endswith(".webp"))

        with Image.open(category.image_desktop) as desktop:
            self.assertEqual(desktop.size, (1440, 1440))
            self.assertEqual(desktop.format, "WEBP")

        with Image.open(category.image_tablet) as tablet:
            self.assertEqual(tablet.size, (1080, 1080))
            self.assertEqual(tablet.format, "WEBP")

        with Image.open(category.image_mobile) as mobile:
            self.assertEqual(mobile.size, (720, 720))
            self.assertEqual(mobile.format, "WEBP")

    def test_legacy_manual_variant_upload_still_converts_to_webp(self):
        category = Category.objects.create(
            name="Filters",
            slug="filters",
            sort_order=1,
            image_desktop=_generate_test_image("filters-desktop.jpg"),
        )

        category.refresh_from_db()

        self.assertFalse(bool(category.image_original))
        self.assertTrue(category.image_desktop.name.endswith(".webp"))

        with Image.open(category.image_desktop) as desktop:
            self.assertEqual(desktop.format, "WEBP")


@override_settings(
    CACHE_ENABLED=True,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "catalog-cache-tests",
            "TIMEOUT": None,
        }
    },
)
class CategoryCacheTests(APITestCase):
    def setUp(self):
        cache.clear()
        Product.objects.all().delete()
        Category.objects.all().delete()
        self.category = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        Product.objects.create(
            category=self.category,
            name="Organizer",
            slug="organizer",
            sku="ORG-1",
            short_description="Organizer",
            description="Organizer description",
            price=Decimal("99.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )

    def tearDown(self):
        cache.clear()

    def test_category_list_returns_miss_then_hit_and_invalidates_on_product_save(self):
        first_response = self.client.get(reverse("catalog-category-list"))
        second_response = self.client.get(reverse("catalog-category-list"))

        Product.objects.create(
            category=self.category,
            name="Console Tray",
            slug="console-tray",
            sku="TRAY-1",
            short_description="Console tray",
            description="Console tray description",
            price=Decimal("49.00"),
            stock_qty=3,
            status=ProductStatus.PUBLISHED,
        )

        third_response = self.client.get(reverse("catalog-category-list"))

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.headers["X-Cache-Status"], "MISS")
        self.assertEqual(second_response.headers["X-Cache-Status"], "HIT")
        self.assertEqual(third_response.headers["X-Cache-Status"], "MISS")
        self.assertEqual(third_response.data[0]["product_count"], 2)
