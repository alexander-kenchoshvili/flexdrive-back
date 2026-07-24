import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase
from PIL import Image

from catalog.models import Brand, Category, Product, ProductImage, ProductStatus
from catalog.suo_lun_gallery_backup_import import (
    build_gallery_backup_report,
    import_gallery_backup_matches,
)


class SuoLunGalleryBackupImportTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Body", slug="body-gallery")
        self.brand = Brand.objects.create(name="Suo Lun", slug="suo-lun-gallery")

    def _product(self, sku):
        return Product.objects.create(
            category=self.category,
            brand=self.brand,
            name=f"Part {sku}",
            slug=sku.lower(),
            sku=sku,
            price=Decimal("10.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )

    def _write_image(self, path, color):
        Image.new("RGB", (80, 60), color).save(path, format="JPEG")

    def test_report_uses_only_approved_retained_local_images_and_main_first(self):
        approved = self._product("CM-APPROVED")
        existing = self._product("CM-EXISTING")
        rejected = self._product("CM-REJECTED")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "suo-lun-amazon-gallery-review-assets"
            assets.mkdir()
            self._write_image(assets / "approved-one.jpg", (10, 20, 30))
            self._write_image(assets / "approved-main.jpg", (40, 50, 60))
            self._write_image(assets / "existing.jpg", (70, 80, 90))
            self._write_image(assets / "rejected.jpg", (100, 110, 120))

            backup_path = root / "backup.json"
            backup_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 6,
                        "statuses": {
                            approved.sku: "approved",
                            existing.sku: "approved",
                            rejected.sku: "rejected",
                        },
                        "deletedImgs": {
                            approved.sku: [
                                "suo-lun-amazon-gallery-review-assets/deleted.jpg"
                            ]
                        },
                        "manualImgs": {
                            approved.sku: [
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/"
                                        "approved-one.jpg"
                                    )
                                },
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/"
                                        "approved-main.jpg"
                                    )
                                },
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/"
                                        "deleted.jpg"
                                    )
                                },
                            ],
                            existing.sku: [
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/"
                                        "existing.jpg"
                                    )
                                }
                            ],
                        },
                        "addedImgs": {
                            approved.sku: [
                                {"url": "https://example.test/source-image.jpg"}
                            ]
                        },
                        "mainImgs": {
                            approved.sku: (
                                "suo-lun-amazon-gallery-review-assets/"
                                "approved-main.jpg"
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            html_path = root / "review.html"
            html_path.write_text(
                """
                <article class='card'><header><b>CM-APPROVED</b></header>
                <section class='gallery'></section></article>
                <article class='card'><header><b>CM-EXISTING</b></header>
                <section class='gallery'></section></article>
                <article class='card'><header><b>CM-REJECTED</b></header>
                <section class='gallery'><img src='suo-lun-amazon-gallery-review-assets/rejected.jpg'></section></article>
                """,
                encoding="utf-8",
            )

            with self.settings(MEDIA_ROOT=root / "media"):
                ProductImage.objects.bulk_create(
                    [
                        ProductImage(
                            product=existing,
                            image_original="existing/already.jpg",
                            is_primary=True,
                        )
                    ]
                )
                report = build_gallery_backup_report(
                    backup_path,
                    html_path,
                    assets,
                    products=[approved, existing, rejected],
                )

        self.assertEqual(report.approved_count, 2)
        self.assertEqual(report.approved_image_count, 3)
        self.assertEqual(report.existing_image_skus, ("CM-EXISTING",))
        self.assertEqual(len(report.matches), 1)
        self.assertEqual(
            [image.path.name for image in report.matches[0].images],
            ["approved-main.jpg", "approved-one.jpg"],
        )
        self.assertEqual(len(report.ignored_remote_entries), 1)
        self.assertFalse(report.has_blockers)

    def test_report_blocks_missing_files_and_approved_cards_without_images(self):
        missing_file = self._product("CM-MISSING-FILE")
        no_image = self._product("CM-NO-IMAGE")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "suo-lun-amazon-gallery-review-assets"
            assets.mkdir()
            backup_path = root / "backup.json"
            backup_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 6,
                        "statuses": {
                            missing_file.sku: "approved",
                            no_image.sku: "approved",
                        },
                        "manualImgs": {
                            missing_file.sku: [
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/"
                                        "does-not-exist.jpg"
                                    )
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            html_path = root / "review.html"
            html_path.write_text(
                """
                <article class='card'><b>CM-MISSING-FILE</b><section class='gallery'></section></article>
                <article class='card'><b>CM-NO-IMAGE</b><section class='gallery'></section></article>
                """,
                encoding="utf-8",
            )
            report = build_gallery_backup_report(
                backup_path,
                html_path,
                assets,
                products=[missing_file, no_image],
            )

        self.assertTrue(report.has_blockers)
        self.assertEqual(len(report.missing_file_entries), 1)
        self.assertEqual(
            set(report.no_image_skus),
            {"CM-MISSING-FILE", "CM-NO-IMAGE"},
        )

    def test_import_creates_all_images_with_selected_main_as_primary(self):
        product = self._product("CM-IMPORT")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "suo-lun-amazon-gallery-review-assets"
            assets.mkdir()
            self._write_image(assets / "one.jpg", (10, 20, 30))
            self._write_image(assets / "main.jpg", (40, 50, 60))
            backup_path = root / "backup.json"
            backup_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 6,
                        "statuses": {product.sku: "approved"},
                        "manualImgs": {
                            product.sku: [
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/one.jpg"
                                    )
                                },
                                {
                                    "url": (
                                        "suo-lun-amazon-gallery-review-assets/main.jpg"
                                    )
                                },
                            ]
                        },
                        "mainImgs": {
                            product.sku: (
                                "suo-lun-amazon-gallery-review-assets/main.jpg"
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            html_path = root / "review.html"
            html_path.write_text(
                "<article class='card'><b>CM-IMPORT</b><section class='gallery'></section></article>",
                encoding="utf-8",
            )
            with self.settings(MEDIA_ROOT=root / "media"):
                expected_main_content = (assets / "main.jpg").read_bytes()
                report = build_gallery_backup_report(
                    backup_path,
                    html_path,
                    assets,
                    products=[product],
                )
                result = import_gallery_backup_matches(report.matches)
                images = list(ProductImage.objects.filter(product=product))

        self.assertEqual(result.imported_products, 1)
        self.assertEqual(result.imported_images, 2)
        self.assertEqual(result.errors, ())
        self.assertEqual(len(images), 2)
        self.assertTrue(images[0].is_primary)
        with images[0].image_original.open("rb") as stored_main:
            self.assertEqual(stored_main.read(), expected_main_content)
        self.assertFalse(images[1].is_primary)
