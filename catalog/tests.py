from decimal import Decimal
from io import BytesIO
import os
import tempfile
from unittest import skipUnless

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.forms.models import inlineformset_factory
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductImage,
    ProductPlacement,
    ProductSide,
    ProductSpec,
    ProductStatus,
    SupplierProductBlock,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)
from .admin import (
    ProductImageAdminForm,
    ProductImageInlineFormSet,
    _regenerate_manual_fitment_descriptions,
)
from .management.commands.audit_cloudinary_orphans import (
    format_bytes,
    normalize_storage_name,
    storage_name_to_public_id,
    top_level_folder,
)
from .search_cache import VEHICLE_SEARCH_CACHE_KEY
from .views import _build_search_context


def _generate_test_image(filename="sample.jpg", color=(255, 0, 0), size=(100, 100)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


def _generate_whitespace_test_image(filename="part.jpg", size=(800, 600)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, (255, 255, 255))
    for x in range(320, 480):
        for y in range(250, 350):
            image.putpixel((x, y), (10, 10, 10))
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


def _generate_gray_background_test_image(filename="gray-part.jpg", size=(800, 600)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, (180, 180, 180))
    for x in range(300, 500):
        for y in range(220, 380):
            image.putpixel((x, y), (12, 12, 12))
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


class CatalogAdminTests(TestCase):
    def test_calculated_price_preview_handles_unsaved_product_without_price(self):
        product_admin = site._registry[Product]

        self.assertEqual(
            product_admin.calculated_customer_price_readonly(Product()),
            "",
        )

    def test_manual_fitment_description_regeneration_uses_current_fitment(self):
        category = Category.objects.create(name="Lighting", slug="manual-lighting")
        make = VehicleMake.objects.create(name="Subaru", slug="manual-subaru")
        model = VehicleModel.objects.create(
            make=make,
            name="Forester",
            slug="manual-forester",
        )
        product = Product.objects.create(
            category=category,
            name="ეკრანის ქვედა ძირის ზედა მხარე",
            slug="manual-fitment-description",
            sku="CM-MANUAL",
            price=Decimal("80.00"),
            placement=ProductPlacement.UPPER,
            preserve_manual_fitment_content=True,
            status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(
            product=product,
            vehicle_model=model,
            year_from=2020,
            year_to=2024,
            notes="Manual corrected fitment",
        )

        _regenerate_manual_fitment_descriptions(product)

        product.refresh_from_db()
        self.assertEqual(
            product.short_description,
            "ეკრანის ქვედა ძირის ზედა მხარე - Subaru Forester - 2020-2024",
        )
        self.assertEqual(
            product.description,
            "ეკრანის ქვედა ძირის ზედა მხარე - Subaru Forester, 2020-2024, ზედა.",
        )
        self.assertEqual(product.seo_description, product.short_description)

    def test_product_admin_action_blocks_crossmotors_product_from_supplier_import(self):
        user = get_user_model().objects.create_superuser(
            username="supplier-block-admin",
            email="supplier-block-admin@example.com",
            password="password",
        )
        self.client.force_login(user)
        category = Category.objects.create(name="Lighting", slug="admin-block-lighting")
        supplier_product = Product.objects.create(
            category=category,
            name="Supplier Headlight",
            slug="admin-supplier-headlight",
            sku="CM-000015",
            price=Decimal("250.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )
        manual_product = Product.objects.create(
            category=category,
            name="Manual Headlight",
            slug="admin-manual-headlight",
            sku="MANUAL-000015",
            price=Decimal("250.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )

        response = self.client.post(
            reverse("admin:catalog_product_changelist"),
            {
                "action": "action_block_supplier_products",
                "_selected_action": [str(supplier_product.pk), str(manual_product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        supplier_product.refresh_from_db()
        manual_product.refresh_from_db()
        self.assertEqual(supplier_product.status, ProductStatus.ARCHIVED)
        self.assertEqual(manual_product.status, ProductStatus.PUBLISHED)
        self.assertTrue(
            SupplierProductBlock.objects.filter(
                source_name="Cross Motors",
                supplier_sku="CM-000015",
            ).exists()
        )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_product_image_crop_admin_post_updates_crop(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        self.client.force_login(user)
        category = Category.objects.create(name="Interior", slug="admin-interior")
        product = Product.objects.create(
            category=category,
            name="Mirror Cap",
            slug="admin-mirror-cap",
            sku="ADMIN-MIRROR",
            price=Decimal("10.00"),
            stock_qty=5,
            status=ProductStatus.PUBLISHED,
        )
        image = ProductImage.objects.create(
            product=product,
            image_original=_generate_whitespace_test_image("mirror-cap.jpg"),
            is_primary=True,
        )
        url = reverse("admin:catalog_productimage_crop", args=[product.pk, image.pk])

        get_response = self.client.get(url)

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "Manual crop")

        response = self.client.post(
            url,
            {
                "action": "manual",
                "crop_x": "0.25000",
                "crop_y": "0.25000",
                "crop_width": "0.50000",
                "crop_height": "0.40000",
            },
        )

        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertEqual(image.crop_x, Decimal("0.25000"))
        self.assertEqual(image.crop_height, Decimal("0.40000"))

        response = self.client.post(url, {"action": "white_bg"})

        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertTrue(image.replace_background_with_white)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_product_image_inline_allows_moving_primary_to_new_image(self):
        category = Category.objects.create(name="Lighting", slug="admin-lighting")
        product = Product.objects.create(
            category=category,
            name="Headlight",
            slug="admin-headlight",
            sku="ADMIN-HEADLIGHT",
            price=Decimal("20.00"),
            stock_qty=3,
            status=ProductStatus.PUBLISHED,
        )
        image = ProductImage.objects.create(
            product=product,
            image_original=_generate_test_image("old-headlight.jpg"),
            is_primary=True,
            sort_order=1,
        )
        formset_class = inlineformset_factory(
            Product,
            ProductImage,
            form=ProductImageAdminForm,
            formset=ProductImageInlineFormSet,
            fields=(
                "image_original",
                "alt_text",
                "is_primary",
                "sort_order",
            ),
            extra=1,
            can_delete=True,
        )
        data = {
            "images-TOTAL_FORMS": "2",
            "images-INITIAL_FORMS": "1",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
            "images-0-id": str(image.pk),
            "images-0-product": str(product.pk),
            "images-0-alt_text": "Old image",
            "images-0-sort_order": "1",
            "images-1-id": "",
            "images-1-product": str(product.pk),
            "images-1-alt_text": "New primary image",
            "images-1-is_primary": "on",
            "images-1-sort_order": "2",
        }
        files = {
            "images-1-image_original": _generate_test_image("new-headlight.jpg"),
        }

        formset = formset_class(data=data, files=files, instance=product, prefix="images")

        self.assertTrue(formset.is_valid(), formset.errors)

    def test_product_image_inline_rejects_multiple_primary_images(self):
        category = Category.objects.create(name="Body", slug="admin-body")
        product = Product.objects.create(
            category=category,
            name="Bumper",
            slug="admin-bumper",
            sku="ADMIN-BUMPER",
            price=Decimal("40.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )
        image = ProductImage.objects.create(
            product=product,
            image_original=_generate_test_image("old-bumper.jpg"),
            is_primary=True,
            sort_order=1,
        )
        formset_class = inlineformset_factory(
            Product,
            ProductImage,
            form=ProductImageAdminForm,
            formset=ProductImageInlineFormSet,
            fields=(
                "image_original",
                "alt_text",
                "is_primary",
                "sort_order",
            ),
            extra=1,
            can_delete=True,
        )
        data = {
            "images-TOTAL_FORMS": "2",
            "images-INITIAL_FORMS": "1",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
            "images-0-id": str(image.pk),
            "images-0-product": str(product.pk),
            "images-0-alt_text": "Old image",
            "images-0-is_primary": "on",
            "images-0-sort_order": "1",
            "images-1-id": "",
            "images-1-product": str(product.pk),
            "images-1-alt_text": "New image",
            "images-1-is_primary": "on",
            "images-1-sort_order": "2",
        }
        files = {
            "images-1-image_original": _generate_test_image("new-bumper.jpg"),
        }

        formset = formset_class(data=data, files=files, instance=product, prefix="images")

        self.assertFalse(formset.is_valid())
        self.assertIn(
            "Only one product image can be marked as primary.",
            formset.non_form_errors(),
        )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_product_admin_delete_selected_images_keeps_user_on_product(self):
        user = get_user_model().objects.create_superuser(
            username="bulk-delete-admin",
            email="bulk-delete-admin@example.com",
            password="password",
        )
        self.client.force_login(user)
        category = Category.objects.create(name="Panels", slug="admin-panels")
        product = Product.objects.create(
            category=category,
            name="Door Panel",
            slug="admin-door-panel",
            sku="ADMIN-PANEL",
            price=Decimal("30.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        other_product = Product.objects.create(
            category=category,
            name="Fender",
            slug="admin-fender",
            sku="ADMIN-FENDER",
            price=Decimal("35.00"),
            stock_qty=2,
            status=ProductStatus.PUBLISHED,
        )
        first_image = ProductImage.objects.create(
            product=product,
            image_original=_generate_test_image("door-panel-1.jpg"),
            is_primary=True,
            sort_order=1,
        )
        second_image = ProductImage.objects.create(
            product=product,
            image_original=_generate_test_image("door-panel-2.jpg"),
            sort_order=2,
        )
        other_image = ProductImage.objects.create(
            product=other_product,
            image_original=_generate_test_image("fender.jpg"),
            is_primary=True,
            sort_order=1,
        )
        url = reverse(
            "admin:catalog_product_images_delete_selected",
            args=[product.pk],
        )

        response = self.client.post(
            url,
            {
                "image_ids": [
                    str(first_image.pk),
                    str(second_image.pk),
                    str(other_image.pk),
                ]
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('admin:catalog_product_change', args=[product.pk])}#images-group",
            fetch_redirect_response=False,
        )
        self.assertFalse(
            ProductImage.objects.filter(pk__in=[first_image.pk, second_image.pk]).exists()
        )
        self.assertTrue(ProductImage.objects.filter(pk=other_image.pk).exists())


class CloudinaryOrphanAuditCommandTests(TestCase):
    def test_storage_name_to_public_id_removes_cloudinary_version_and_extension(self):
        self.assertEqual(
            storage_name_to_public_id(
                "v1783414062/catalog/products/4133/images/image.webp"
            ),
            "catalog/products/4133/images/image",
        )
        self.assertEqual(
            storage_name_to_public_id("catalog/products/4133/images/image.jpg"),
            "catalog/products/4133/images/image",
        )

    def test_normalize_storage_name_preserves_non_versioned_v_folder(self):
        self.assertEqual(
            normalize_storage_name("vfolder/catalog/image.webp"),
            "vfolder/catalog/image.webp",
        )

    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024 * 1024), "1.00 MB")

    def test_top_level_folder(self):
        self.assertEqual(top_level_folder("catalog/products/1/image"), "catalog")
        self.assertEqual(top_level_folder("seo/image"), "seo")
        self.assertEqual(top_level_folder("image"), "image")
        self.assertEqual(top_level_folder(""), "(root)")


class CatalogAPITests(APITestCase):
    def setUp(self):
        Product.objects.all().delete()
        Category.objects.all().delete()

        self.interior = Category.objects.create(name="Interior", slug="interior", sort_order=1)
        self.exterior = Category.objects.create(name="Exterior", slug="exterior", sort_order=2)
        self.brand = Brand.objects.create(name="Taiwan Parts", slug="taiwan-parts", sort_order=1)
        self.other_brand = Brand.objects.create(name="Roadline", slug="roadline", sort_order=2)

        self.toyota = VehicleMake.objects.create(name="Toyota", slug="toyota", sort_order=1)
        self.honda = VehicleMake.objects.create(name="Honda", slug="honda", sort_order=2)
        self.empty_make = VehicleMake.objects.create(name="Empty Make", slug="empty-make", sort_order=3)
        self.inactive_make = VehicleMake.objects.create(
            name="Inactive Make",
            slug="inactive-make",
            sort_order=4,
            is_active=False,
        )
        self.camry = VehicleModel.objects.create(
            make=self.toyota,
            name="Camry",
            slug="camry",
            sort_order=1,
        )
        self.corolla = VehicleModel.objects.create(
            make=self.toyota,
            name="Corolla",
            slug="corolla",
            sort_order=2,
        )
        self.accord = VehicleModel.objects.create(
            make=self.honda,
            name="Accord",
            slug="accord",
            sort_order=1,
        )
        self.hybrid_engine = VehicleEngine.objects.create(
            model=self.camry,
            name="2.5 Hybrid",
            slug="25-hybrid",
            sort_order=1,
        )
        self.gas_engine = VehicleEngine.objects.create(
            model=self.camry,
            name="2.5 Gas",
            slug="25-gas",
            sort_order=2,
        )
        self.inactive_engine = VehicleEngine.objects.create(
            model=self.camry,
            name="Inactive Engine",
            slug="inactive-engine",
            sort_order=3,
            is_active=False,
        )

        self.products = []
        for i in range(12):
            product = Product.objects.create(
                category=self.interior,
                brand=self.brand if i % 2 == 0 else self.other_brand,
                name=f"Product {i}",
                slug=f"product-{i}",
                sku=f"SKU-{i}",
                manufacturer_part_number=f"MPN-{i}",
                short_description="Short description",
                description="Long description",
                price=Decimal("10.00") + Decimal(i),
                old_price=Decimal("20.00") + Decimal(i) if i % 2 == 0 else None,
                placement=ProductPlacement.FRONT if i % 2 == 0 else ProductPlacement.REAR,
                side=ProductSide.LEFT if i % 2 == 0 else ProductSide.RIGHT,
                stock_qty=5 if i % 3 else 0,
                is_new=i < 5,
                is_featured=i in (1, 3, 5),
                is_universal_fitment=i == 3,
                status=ProductStatus.PUBLISHED,
            )
            self.products.append(product)

        ProductFitment.objects.create(
            product=self.products[0],
            vehicle_model=self.camry,
            year_from=2018,
            year_to=2020,
            notes="Generic Camry fitment",
        )
        ProductFitment.objects.create(
            product=self.products[1],
            vehicle_model=self.camry,
            engine=self.hybrid_engine,
            year_from=2018,
            year_to=2019,
            notes="Hybrid only",
        )
        ProductFitment.objects.create(
            product=self.products[2],
            vehicle_model=self.camry,
            engine=self.gas_engine,
            year_from=2018,
            year_to=2018,
            notes="Gas only",
        )
        ProductFitment.objects.create(
            product=self.products[4],
            vehicle_model=self.accord,
            year_from=2017,
            year_to=2019,
        )
        ProductFitment.objects.create(
            product=self.products[5],
            vehicle_model=self.camry,
            engine=self.inactive_engine,
            year_from=2018,
            year_to=2018,
        )

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

    def test_products_list_orders_in_stock_products_first(self):
        response = self.client.get(reverse("catalog-product-list"), {"page_size": 12})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stock_flags = [row["in_stock"] for row in response.data["results"]]
        first_out_of_stock = stock_flags.index(False)
        self.assertNotIn(True, stock_flags[first_out_of_stock:])

    def test_products_list_keeps_in_stock_first_with_explicit_price_sort(self):
        response = self.client.get(
            reverse("catalog-product-list"),
            {"page_size": 12, "ordering": "price_asc"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        stock_flags = [row["in_stock"] for row in results]
        first_out_of_stock = stock_flags.index(False)
        self.assertNotIn(True, stock_flags[first_out_of_stock:])

        in_stock_prices = [
            Decimal(row["price"])
            for row in results
            if row["in_stock"]
        ]
        self.assertEqual(in_stock_prices, sorted(in_stock_prices))

    def test_products_filter_on_sale(self):
        response = self.client.get(reverse("catalog-product-list"), {"on_sale": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
        for row in response.data["results"]:
            self.assertTrue(row["on_sale"])

    def test_products_filter_has_image(self):
        response = self.client.get(reverse("catalog-product-list"), {"has_image": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "product-0")
        self.assertTrue(response.data["results"][0]["primary_image"]["desktop"])

    def test_products_filter_by_vehicle_model_year(self):
        response = self.client.get(
            reverse("catalog-product-list"),
            {"make": "toyota", "model": "camry", "year": "2018"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-0", "product-1", "product-2", "product-3"})
        compatibility = {row["slug"]: row["compatibility"] for row in response.data["results"]}
        self.assertEqual(compatibility["product-0"]["match_type"], "vehicle_year")
        self.assertEqual(compatibility["product-3"]["match_type"], "universal")

    def test_products_filter_by_vehicle_engine_matches_exact_and_generic_fitments(self):
        response = self.client.get(
            reverse("catalog-product-list"),
            {
                "make": "toyota",
                "model": "camry",
                "year": "2018",
                "engine": "25-hybrid",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-0", "product-1", "product-3"})
        compatibility = {row["slug"]: row["compatibility"] for row in response.data["results"]}
        self.assertEqual(compatibility["product-1"]["match_type"], "engine")
        self.assertNotIn("product-2", slugs)

    def test_products_filter_by_vehicle_make_only(self):
        ProductFitment.objects.create(
            product=self.products[6],
            vehicle_model=self.corolla,
            year_from=2015,
            year_to=2017,
        )

        response = self.client.get(reverse("catalog-product-list"), {"make": "toyota"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-0", "product-1", "product-2", "product-3", "product-6"})
        self.assertNotIn("product-4", slugs)
        self.assertNotIn("product-5", slugs)

    def test_products_filter_by_vehicle_make_and_model_without_year(self):
        response = self.client.get(
            reverse("catalog-product-list"),
            {"make": "toyota", "model": "camry"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-0", "product-1", "product-2", "product-3"})
        self.assertNotIn("product-4", slugs)
        self.assertNotIn("product-5", slugs)

    def test_products_filter_by_vehicle_make_and_year_without_model(self):
        response = self.client.get(
            reverse("catalog-product-list"),
            {"make": "toyota", "year": "2018"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-0", "product-1", "product-2", "product-3"})

    def test_products_vehicle_filter_rejects_out_of_order_vehicle_params(self):
        response = self.client.get(reverse("catalog-product-list"), {"model": "camry"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("make", response.data)

        response = self.client.get(
            reverse("catalog-product-list"),
            {"make": "toyota", "model": "camry", "engine": "25-hybrid"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("year", response.data)

    def test_products_filter_by_brand_placement_and_side(self):
        response = self.client.get(
            reverse("catalog-product-list"),
            {
                "brand": "taiwan-parts",
                "placement": ProductPlacement.FRONT,
                "side": ProductSide.LEFT,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
        for row in response.data["results"]:
            self.assertEqual(row["brand"]["slug"], "taiwan-parts")
            self.assertEqual(row["placement"], ProductPlacement.FRONT)
            self.assertEqual(row["side"], ProductSide.LEFT)
        self.assertIn("brands", response.data["facets"])
        self.assertIn("placements", response.data["facets"])
        self.assertIn("sides", response.data["facets"])

    def test_products_search_matches_manufacturer_part_number(self):
        response = self.client.get(reverse("catalog-product-list"), {"q": "MPN-0"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "product-0")
        self.assertEqual(response.data["results"][0]["manufacturer_part_number"], "MPN-0")

    def test_product_search_rejects_too_short_query(self):
        response = self.client.get(reverse("catalog-product-list"), {"q": "a"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("q", response.data)

    def test_product_search_rejects_too_long_query(self):
        response = self.client.get(reverse("catalog-product-list"), {"q": "a" * 101})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("q", response.data)

    def test_product_search_query_count_stays_bounded_for_unknown_phrase(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("catalog-product-list"),
                {"q": "unknown vehicle brake pads"},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 15)

    def test_products_search_matches_georgian_name_from_latin_transliteration(self):
        Product.objects.create(
            category=self.interior,
            brand=self.brand,
            name="ხუნდები Toyota Camry",
            slug="toyota-camry-brake-pads",
            sku="BRAKE-GE-01",
            manufacturer_part_number="BRK-GE-01",
            short_description="ხარისხიანი სამუხრუჭე ხუნდები",
            description="Toyota Camry-ს სამუხრუჭე ხუნდები",
            price=Decimal("65.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )

        response = self.client.get(reverse("catalog-product-list"), {"q": "xundebi"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "toyota-camry-brake-pads")

    def test_products_search_matches_vehicle_make_fitments(self):
        response = self.client.get(reverse("catalog-product-list"), {"q": "toyota"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-0", "product-1", "product-2", "product-3"})
        self.assertNotIn("product-4", slugs)

    def test_products_search_matches_vehicle_make_from_georgian_query(self):
        subaru = VehicleMake.objects.create(name="Subaru", slug="subaru", sort_order=5)
        impreza = VehicleModel.objects.create(
            make=subaru,
            name="Impreza",
            slug="impreza",
            sort_order=1,
        )
        ProductFitment.objects.create(
            product=self.products[7],
            vehicle_model=impreza,
            year_from=2012,
            year_to=2016,
        )

        response = self.client.get(reverse("catalog-product-list"), {"q": "სუბარუ"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-3", "product-7"})

    def test_products_search_matches_vehicle_make_from_partial_georgian_query(self):
        subaru = VehicleMake.objects.create(name="Subaru", slug="subaru", sort_order=5)
        impreza = VehicleModel.objects.create(
            make=subaru,
            name="Impreza",
            slug="impreza",
            sort_order=1,
        )
        ProductFitment.objects.create(
            product=self.products[7],
            vehicle_model=impreza,
            year_from=2012,
            year_to=2016,
        )

        response = self.client.get(reverse("catalog-product-list"), {"q": "სუბარ"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"product-3", "product-7"})

    def test_products_search_combines_vehicle_and_product_terms(self):
        response = self.client.get(reverse("catalog-product-list"), {"q": "toyota camry Product 0"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "product-0")

    def test_products_search_orders_direct_product_matches_before_related_accessories(self):
        subaru = VehicleMake.objects.create(name="სუბარუ", slug="subaru", sort_order=10)
        forester = VehicleModel.objects.create(
            make=subaru,
            name="Forester",
            slug="forester",
            sort_order=1,
        )
        direct_wing = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="წინა კრილო",
            slug="subaru-front-wing",
            sku="SUB-WING-01",
            manufacturer_part_number="SUB-WING-01",
            short_description="Subaru Forester wing",
            description="Subaru Forester front wing",
            price=Decimal("180.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(
            product=direct_wing,
            vehicle_model=forester,
            year_from=2015,
            year_to=2018,
        )
        for index in range(10):
            accessory = Product.objects.create(
                category=self.exterior,
                brand=self.brand,
                name=f"კრილოს მოლდინგი {index}",
                slug=f"subaru-wing-molding-{index}",
                sku=f"SUB-WING-MOLD-{index}",
                manufacturer_part_number=f"SUB-WING-MOLD-{index}",
                short_description="Subaru Forester wing molding",
                description="Subaru Forester wing molding",
                price=Decimal("45.00") + Decimal(index),
                stock_qty=4,
                status=ProductStatus.PUBLISHED,
            )
            ProductFitment.objects.create(
                product=accessory,
                vehicle_model=forester,
                year_from=2015,
                year_to=2018,
            )

        response = self.client.get(
            reverse("catalog-product-list"),
            {"q": "სუბარუს კრილო"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 9)
        self.assertEqual(response.data["results"][0]["slug"], "subaru-front-wing")

    def test_products_search_matches_georgian_vehicle_alias_and_product_term(self):
        mercedes = VehicleMake.objects.create(name="Mercedes", slug="mercedes", sort_order=10)
        glc = VehicleModel.objects.create(
            make=mercedes,
            name="GLC",
            slug="glc",
            sort_order=1,
        )
        hood = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="კაპოტი",
            slug="mercedes-glc-hood",
            sku="MB-HOOD-01",
            manufacturer_part_number="MB-HOOD-01",
            short_description="Mercedes GLC hood",
            description="Mercedes GLC hood",
            price=Decimal("900.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(
            product=hood,
            vehicle_model=glc,
            year_from=2020,
            year_to=2024,
        )

        response = self.client.get(
            reverse("catalog-product-list"),
            {"q": "მერსედესის კაპოტი"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "mercedes-glc-hood")


    def test_product_suggestions_require_minimum_query_length(self):
        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "c"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_product_suggestions_return_dropdown_ready_results(self):
        suggested = Product.objects.create(
            category=self.interior,
            brand=self.brand,
            name="Fast Charger",
            slug="fast-charger",
            sku="CHARGER-01",
            manufacturer_part_number="CHG-FAST-01",
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

    def test_product_suggestions_match_manufacturer_part_number(self):
        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "MPN-0"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "product-0")
        self.assertEqual(response.data[0]["manufacturer_part_number"], "MPN-0")

    def test_product_suggestions_match_georgian_name_from_latin_transliteration(self):
        Product.objects.create(
            category=self.interior,
            brand=self.brand,
            name="ხუნდები Honda Civic",
            slug="honda-civic-brake-pads",
            sku="BRAKE-GE-02",
            manufacturer_part_number="BRK-GE-02",
            short_description="სამუხრუჭე ხუნდები",
            description="Honda Civic-ის სამუხრუჭე ხუნდები",
            price=Decimal("70.00"),
            stock_qty=3,
            status=ProductStatus.PUBLISHED,
        )

        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "xundebi"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "honda-civic-brake-pads")

    def test_product_suggestions_match_vehicle_make_fitments(self):
        response = self.client.get(reverse("catalog-product-suggestions"), {"q": "toyota"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data}
        self.assertIn("product-0", slugs)
        self.assertIn("product-3", slugs)
        self.assertNotIn("product-4", slugs)

    def test_product_suggestions_order_direct_product_matches_before_related_accessories(self):
        subaru = VehicleMake.objects.create(name="სუბარუ", slug="subaru", sort_order=10)
        forester = VehicleModel.objects.create(
            make=subaru,
            name="Forester",
            slug="forester",
            sort_order=1,
        )
        direct_wing = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="წინა კრილო",
            slug="suggestion-subaru-front-wing",
            sku="SUG-SUB-WING-01",
            manufacturer_part_number="SUG-SUB-WING-01",
            short_description="Subaru Forester wing",
            description="Subaru Forester front wing",
            price=Decimal("180.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        accessory = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="კრილოს მოლდინგი",
            slug="suggestion-subaru-wing-molding",
            sku="SUG-SUB-WING-MOLD",
            manufacturer_part_number="SUG-SUB-WING-MOLD",
            short_description="Subaru Forester wing molding",
            description="Subaru Forester wing molding",
            price=Decimal("45.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        for product in (direct_wing, accessory):
            ProductFitment.objects.create(
                product=product,
                vehicle_model=forester,
                year_from=2015,
                year_to=2018,
            )

        response = self.client.get(
            reverse("catalog-product-suggestions"),
            {"q": "სუბარუს კრილო"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["slug"], "suggestion-subaru-front-wing")

    def test_product_suggestions_match_vehicle_possessive_and_product_term(self):
        subaru = VehicleMake.objects.create(name="სუბარუ", slug="subaru", sort_order=10)
        forester = VehicleModel.objects.create(
            make=subaru,
            name="Forester",
            slug="forester",
            sort_order=1,
        )
        headlight = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="ფარი Forester",
            slug="forester-headlight",
            sku="SUB-FARI-01",
            manufacturer_part_number="SUB-FARI-01",
            short_description="წინა ფარი",
            description="Subaru Forester-ის ფარი",
            price=Decimal("120.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(
            product=headlight,
            vehicle_model=forester,
            year_from=2015,
            year_to=2018,
        )

        response = self.client.get(
            reverse("catalog-product-suggestions"),
            {"q": "სუბარუს ფარი"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["slug"], "forester-headlight")

    def test_product_suggestions_match_latin_vehicle_possessive_and_product_term(self):
        subaru = VehicleMake.objects.create(name="სუბარუ", slug="subaru", sort_order=10)
        forester = VehicleModel.objects.create(
            make=subaru,
            name="Forester",
            slug="forester",
            sort_order=1,
        )
        headlight = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="ფარი Forester",
            slug="forester-headlight-latin",
            sku="SUB-FARI-02",
            manufacturer_part_number="SUB-FARI-02",
            short_description="წინა ფარი",
            description="Subaru Forester-ის ფარი",
            price=Decimal("120.00"),
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(
            product=headlight,
            vehicle_model=forester,
            year_from=2015,
            year_to=2018,
        )

        response = self.client.get(
            reverse("catalog-product-suggestions"),
            {"q": "subarus fari"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["slug"], "forester-headlight-latin")
        self.assertEqual(response.data[0]["fitment_summary"], "სუბარუ Forester · 2015-2018")

    def test_product_suggestions_parse_latin_vehicle_side_placement_and_product_terms(self):
        subaru = VehicleMake.objects.create(name="სუბარუ", slug="subaru", sort_order=10)
        forester = VehicleModel.objects.create(
            make=subaru,
            name="Forester",
            slug="forester",
            sort_order=1,
        )
        front_left_door = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="კარი Forester",
            slug="forester-front-left-door",
            sku="SUB-DOOR-FL",
            manufacturer_part_number="SUB-DOOR-FL",
            short_description="Forester door",
            description="Subaru Forester door",
            price=Decimal("220.00"),
            placement=ProductPlacement.FRONT,
            side=ProductSide.LEFT,
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        rear_left_door = Product.objects.create(
            category=self.exterior,
            brand=self.brand,
            name="კარი Forester",
            slug="forester-rear-left-door",
            sku="SUB-DOOR-RL",
            manufacturer_part_number="SUB-DOOR-RL",
            short_description="Forester door",
            description="Subaru Forester door",
            price=Decimal("210.00"),
            placement=ProductPlacement.REAR,
            side=ProductSide.LEFT,
            stock_qty=4,
            status=ProductStatus.PUBLISHED,
        )
        for product in (front_left_door, rear_left_door):
            ProductFitment.objects.create(
                product=product,
                vehicle_model=forester,
                year_from=2015,
                year_to=2018,
            )

        response = self.client.get(
            reverse("catalog-product-suggestions"),
            {"q": "subarus wina marcxena kari"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [row["slug"] for row in response.data]
        self.assertIn("forester-front-left-door", slugs)
        self.assertNotIn("forester-rear-left-door", slugs)

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
        self.assertEqual(response.data["brand"]["slug"], "taiwan-parts")
        self.assertEqual(response.data["manufacturer_part_number"], "MPN-0")
        self.assertEqual(len(response.data["fitments"]), 1)
        self.assertEqual(response.data["fitments"][0]["make"]["slug"], "toyota")
        self.assertIn("related_products", response.data)

    def test_product_detail_returns_compatibility_for_vehicle_query(self):
        response = self.client.get(
            reverse("catalog-product-detail", kwargs={"slug": "product-0"}),
            {"make": "toyota", "model": "camry", "year": "2018"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["compatibility"]["match_type"], "vehicle_year")

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
                "regular-in-newer",
                "regular-in-older",
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

    def test_vehicle_make_options_return_only_makes_with_published_fitments(self):
        response = self.client.get(reverse("catalog-vehicle-make-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data}
        self.assertEqual(slugs, {"toyota", "honda"})
        self.assertNotIn("empty-make", slugs)
        self.assertNotIn("inactive-make", slugs)

    def test_vehicle_model_options_return_only_models_for_make_with_published_fitments(self):
        response = self.client.get(
            reverse("catalog-vehicle-model-list"),
            {"make": "toyota"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data}
        self.assertEqual(slugs, {"camry"})
        self.assertNotIn("corolla", slugs)

    def test_vehicle_year_options_expand_published_fitment_ranges(self):
        response = self.client.get(
            reverse("catalog-vehicle-year-list"),
            {"make": "toyota", "model": "camry"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["year"] for row in response.data],
            [2018, 2019, 2020],
        )

    def test_vehicle_engine_options_return_only_active_engines_for_selected_year(self):
        response = self.client.get(
            reverse("catalog-vehicle-engine-list"),
            {"make": "toyota", "model": "camry", "year": "2018"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data}
        self.assertEqual(slugs, {"25-hybrid", "25-gas"})
        self.assertNotIn("inactive-engine", slugs)


@override_settings(
    CACHE_ENABLED=True,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "catalog-search-performance-tests",
            "TIMEOUT": None,
        }
    },
)
class CatalogSearchPerformanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.make = VehicleMake.objects.create(
            name="Toyota",
            slug="toyota",
            sort_order=1,
        )
        self.model = VehicleModel.objects.create(
            make=self.make,
            name="Camry",
            slug="camry",
            sort_order=1,
        )
        VehicleEngine.objects.create(
            model=self.model,
            name="2.5 Hybrid",
            slug="25-hybrid",
            sort_order=1,
        )
        cache.delete(VEHICLE_SEARCH_CACHE_KEY)

    def tearDown(self):
        cache.clear()

    def test_search_context_loads_vehicle_catalog_once_on_cold_cache(self):
        with CaptureQueriesContext(connection) as queries:
            context = _build_search_context("unknown vehicle brake pads")

        self.assertIsNotNone(context)
        self.assertEqual(len(queries), 3)

    def test_search_context_uses_cached_vehicle_catalog_without_queries(self):
        _build_search_context("toyota camry brake pads")

        with self.assertNumQueries(0):
            context = _build_search_context("toyota camry brake pads")

        self.assertEqual(
            context["search_parts"]["vehicle_filter"]["make_id"],
            self.make.id,
        )
        self.assertEqual(
            context["search_parts"]["vehicle_filter"]["model_id"],
            self.model.id,
        )

    def test_vehicle_catalog_cache_invalidates_after_vehicle_change(self):
        _build_search_context("toyota")
        self.assertIsNotNone(cache.get(VEHICLE_SEARCH_CACHE_KEY))

        with self.captureOnCommitCallbacks(execute=True):
            VehicleMake.objects.create(name="Honda", slug="honda", sort_order=2)

        self.assertIsNone(cache.get(VEHICLE_SEARCH_CACHE_KEY))
        with CaptureQueriesContext(connection) as queries:
            context = _build_search_context("honda")

        self.assertEqual(len(queries), 3)
        self.assertIsNotNone(context["search_parts"]["vehicle_filter"])


@skipUnless(
    connection.vendor == "postgresql",
    "Catalog DB constraints are installed on PostgreSQL.",
)
class CatalogDatabaseConstraintTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Constraint Category",
            slug="constraint-category",
            markup_percent=Decimal("10.00"),
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Constraint Product",
            slug="constraint-product",
            sku="CONSTRAINT-1",
            price=Decimal("100.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )

    def assert_database_rejects(self, operation):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                operation()

    def test_database_rejects_invalid_category_markup(self):
        self.assert_database_rejects(
            lambda: Category.objects.filter(pk=self.category.pk).update(
                markup_percent=Decimal("1000.01")
            )
        )

    def test_database_rejects_negative_product_prices(self):
        self.assert_database_rejects(
            lambda: Product.objects.filter(pk=self.product.pk).update(
                price=Decimal("-0.01")
            )
        )
        self.assert_database_rejects(
            lambda: Product.objects.filter(pk=self.product.pk).update(
                supplier_price=Decimal("-0.01")
            )
        )

    def test_database_rejects_invalid_product_markup_and_old_price(self):
        self.assert_database_rejects(
            lambda: Product.objects.filter(pk=self.product.pk).update(
                markup_percent_override=Decimal("1000.01")
            )
        )
        self.assert_database_rejects(
            lambda: Product.objects.filter(pk=self.product.pk).update(
                old_price=Decimal("100.00")
            )
        )


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

    def test_seed_catalog_filters_enriches_products_and_filter_options(self):
        call_command("seed_catalog", count=6, reset=True, seed=123)
        call_command("seed_catalog_filters", product_limit=6, reset_fitments=True, seed=123)

        self.assertEqual(Product.objects.filter(sku__startswith="FAKE-", brand__isnull=False).count(), 6)
        self.assertEqual(Product.objects.filter(sku__startswith="FAKE-").exclude(placement="").count(), 6)
        self.assertEqual(Product.objects.filter(sku__startswith="FAKE-").exclude(side="").count(), 6)
        self.assertGreaterEqual(Brand.objects.filter(is_active=True).count(), 6)
        self.assertGreater(VehicleMake.objects.filter(is_active=True).count(), 0)
        self.assertGreater(VehicleModel.objects.filter(is_active=True).count(), 0)
        self.assertGreater(VehicleEngine.objects.filter(is_active=True).count(), 0)
        self.assertGreater(ProductFitment.objects.count(), 0)

        makes_response = self.client.get(reverse("catalog-vehicle-make-list"))
        self.assertEqual(makes_response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(makes_response.json()), 0)

        engines_response = self.client.get(
            reverse("catalog-vehicle-engine-list"),
            {"make": "toyota", "model": "camry", "year": "2018"},
        )
        self.assertEqual(engines_response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(engines_response.json()), 0)

        products_response = self.client.get(reverse("catalog-product-list"))
        self.assertEqual(products_response.status_code, status.HTTP_200_OK)
        facets = products_response.json()["facets"]
        self.assertGreater(len(facets["brands"]), 0)
        self.assertGreater(len(facets["placements"]), 0)
        self.assertGreater(len(facets["sides"]), 0)

        camry_response = self.client.get(
            reverse("catalog-product-list"),
            {"make": "toyota", "model": "camry", "year": "2018"},
        )
        self.assertEqual(camry_response.status_code, status.HTTP_200_OK)
        for row in camry_response.json()["results"]:
            self.assertTrue("Camry" in row["name"] or row["is_universal_fitment"])


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
            self.assertEqual(desktop.size, (1440, 810))
            self.assertEqual(desktop.format, "WEBP")

        with Image.open(image.image_tablet) as tablet:
            self.assertEqual(tablet.size, (1080, 608))
            self.assertEqual(tablet.format, "WEBP")

        with Image.open(image.image_mobile) as mobile:
            self.assertEqual(mobile.size, (720, 405))
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

    def test_crop_metadata_regenerates_variants_from_original_crop(self):
        image = ProductImage.objects.create(
            product=self.product,
            image_original=_generate_test_image(
                "organizer-crop-original.jpg",
                color=(15, 25, 35),
                size=(1600, 900),
            ),
            is_primary=True,
        )

        image.crop_x = Decimal("0.25000")
        image.crop_y = Decimal("0.25000")
        image.crop_width = Decimal("0.50000")
        image.crop_height = Decimal("0.40000")
        image.save(
            update_fields=[
                "crop_x",
                "crop_y",
                "crop_width",
                "crop_height",
                "updated_at",
            ]
        )
        image.refresh_from_db()

        with Image.open(image.image_desktop) as desktop:
            self.assertEqual(desktop.size, (800, 360))
            self.assertEqual(desktop.format, "WEBP")

    def test_auto_crop_from_original_detects_whitespace(self):
        image = ProductImage.objects.create(
            product=self.product,
            image_original=_generate_whitespace_test_image("organizer-whitespace.jpg"),
            is_primary=True,
        )

        self.assertTrue(image.auto_crop_from_original())
        image.save(
            update_fields=[
                "crop_x",
                "crop_y",
                "crop_width",
                "crop_height",
                "updated_at",
            ]
        )
        image.refresh_from_db()

        self.assertIsNotNone(image.crop_x)
        self.assertLess(image.crop_width, Decimal("1.00000"))
        self.assertLess(image.crop_height, Decimal("1.00000"))

    def test_flat_background_replacement_generates_white_background_variants(self):
        image = ProductImage.objects.create(
            product=self.product,
            image_original=_generate_gray_background_test_image("organizer-gray.jpg"),
            is_primary=True,
        )

        image.replace_background_with_white = True
        image.save(update_fields=["replace_background_with_white", "updated_at"])
        image.refresh_from_db()

        with Image.open(image.image_desktop) as desktop:
            corner = desktop.convert("RGB").getpixel((2, 2))
            center = desktop.convert("RGB").getpixel(
                (desktop.width // 2, desktop.height // 2)
            )

        self.assertGreaterEqual(corner[0], 245)
        self.assertGreaterEqual(corner[1], 245)
        self.assertGreaterEqual(corner[2], 245)
        self.assertLess(center[0], 80)
        self.assertLess(center[1], 80)
        self.assertLess(center[2], 80)

    def test_delete_removes_product_image_files_from_storage_after_commit(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                MEDIA_ROOT=media_root,
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage"
                    },
                    "staticfiles": {
                        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                    },
                },
            ):
                image = ProductImage.objects.create(
                    product=self.product,
                    image_original=_generate_test_image(
                        "organizer-delete-original.jpg",
                        color=(15, 25, 35),
                        size=(1600, 900),
                    ),
                    is_primary=True,
                )
                image.refresh_from_db()
                stored_paths = [
                    getattr(image, field_name).path
                    for field_name in (
                        "image_original",
                        "image_desktop",
                        "image_tablet",
                        "image_mobile",
                    )
                    if getattr(image, field_name)
                ]

                self.assertEqual(len(stored_paths), 4)
                for stored_path in stored_paths:
                    self.assertTrue(os.path.exists(stored_path))

                with self.captureOnCommitCallbacks(execute=True):
                    image.delete()

                for stored_path in stored_paths:
                    self.assertFalse(os.path.exists(stored_path))

    def test_delete_keeps_product_image_file_still_referenced_by_another_row(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                MEDIA_ROOT=media_root,
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage"
                    },
                    "staticfiles": {
                        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                    },
                },
            ):
                shared_name = "catalog/products/shared-image.webp"
                shared_path = os.path.join(media_root, shared_name)
                os.makedirs(os.path.dirname(shared_path), exist_ok=True)
                with open(shared_path, "wb") as shared_file:
                    shared_file.write(b"shared")

                first_image = ProductImage.objects.create(
                    product=self.product,
                    image_desktop=shared_name,
                    is_primary=True,
                )
                second_image = ProductImage.objects.create(
                    product=self.product,
                    image_desktop=shared_name,
                    sort_order=2,
                )

                with self.captureOnCommitCallbacks(execute=True):
                    first_image.delete()

                self.assertTrue(os.path.exists(shared_path))

                with self.captureOnCommitCallbacks(execute=True):
                    second_image.delete()

                self.assertFalse(os.path.exists(shared_path))


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

        with self.captureOnCommitCallbacks(execute=True):
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
