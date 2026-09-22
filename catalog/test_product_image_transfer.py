import base64
from copy import deepcopy
import gzip
from io import BytesIO, StringIO
import json
from unittest.mock import Mock, patch
from PIL import Image

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase, override_settings

from catalog.models import Category, Product, ProductImage
from catalog.product_image_transfer import export_snapshot, import_snapshot
from common.storage_backends import CloudinaryMediaStorage


CLOUD_SETTINGS = dict(
    USE_CLOUDINARY_MEDIA=True, CLOUDINARY_SHARED_MEDIA=True,
    CLOUDINARY_CLOUD_NAME="test-cloud", CLOUDINARY_API_KEY="test-key", CLOUDINARY_API_SECRET="test-secret",
    STORAGES={
        "default": {"BACKEND": "common.storage_backends.CloudinaryMediaStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)


@override_settings(**CLOUD_SETTINGS)
class SharedCloudinaryStorageTests(SimpleTestCase):
    def test_editing_same_name_keeps_original_asset_and_returns_unique_paths(self):
        storage = CloudinaryMediaStorage()
        assets = {"catalog/products/1/original": b"staging-image"}
        uploader = Mock()

        def upload(content, **kwargs):
            self.assertFalse(kwargs["overwrite"])
            public_id = kwargs["public_id"]
            self.assertNotIn(public_id, assets)
            assets[public_id] = content.read()
            return {"public_id": public_id, "version": 1783414062, "format": "webp"}

        uploader.upload.side_effect = upload
        with patch.object(storage, "_cloudinary_modules", return_value=(Mock(), uploader, Mock())):
            first = storage.save("v1783414000/catalog/products/1/original.webp", ContentFile(b"edit-1"), max_length=100)
            second = storage.save("v1783414000/catalog/products/1/original.webp", ContentFile(b"edit-2"), max_length=100)
            storage.delete("v1783414000/catalog/products/1/original.webp")
        self.assertNotEqual(first, second)
        self.assertEqual(assets["catalog/products/1/original"], b"staging-image")
        self.assertEqual(assets[storage._parse_name(first)["public_id"]], b"edit-1")
        self.assertLessEqual(len(first), 100)
        uploader.destroy.assert_not_called()

    def test_filename_limit_reserves_unique_suffix_and_version(self):
        name = CloudinaryMediaStorage().get_available_name("catalog/products/123/images/" + "x" * 100 + ".webp", max_length=100)
        self.assertLessEqual(len(name), 84)
        self.assertTrue(name.endswith(".webp"))
        with self.assertRaises(SuspiciousFileOperation):
            CloudinaryMediaStorage().get_available_name("long/path/image.webp", max_length=30)

    def test_orphan_cleanup_cannot_delete_shared_assets(self):
        with patch("cloudinary.api.delete_resources") as delete:
            with self.assertRaisesMessage(CommandError, "shared Cloudinary"):
                call_command("audit_cloudinary_orphans", commit=True, stdout=StringIO())
            delete.assert_not_called()


@override_settings(**CLOUD_SETTINGS)
class ProductImageTransferTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Parts", slug="transfer-parts")
        self.source = Product.objects.create(sku="CM-source", slug="source", name="Source", category=category, price=99, stock_qty=8, status="published")
        ProductImage.objects.bulk_create([
            ProductImage(
                product=self.source, image_original="v1783414000/catalog/source/original.jpg",
                image_desktop="v1783414000/catalog/source/desktop.webp",
                image_tablet="v1783414000/catalog/source/tablet.webp",
                image_mobile="v1783414000/catalog/source/mobile.webp",
                image_ai_background="v1783414000/catalog/source/ai.webp",
                use_ai_background=True, is_primary=True, alt_text="Main lamp", sort_order=2,
                crop_x="0.10000", crop_y="0.20000", crop_width="0.70000", crop_height="0.60000",
                image_padding="14.00", replace_background_with_white=True,
            ),
            ProductImage(product=self.source, image_original="catalog/source/second.jpg", sort_order=4),
        ])
        self.target = Product.objects.create(sku="CM-target", slug="target", name="Target", category=category, price=77, stock_qty=19, status="draft")
        self.snapshot = export_snapshot()
        self.snapshot["products"] = {"CM-target": self.snapshot["products"]["CM-source"]}

    def test_dry_run_commit_and_repeat_preserve_metadata_without_file_io(self):
        with patch.object(CloudinaryMediaStorage, "_cloudinary_modules", side_effect=AssertionError("No cloud calls allowed")), patch.object(ProductImage, "save", side_effect=AssertionError("No processing allowed")):
            preview = import_snapshot(self.snapshot)
            self.assertEqual(preview["images_to_add"], 2)
            self.assertFalse(self.target.images.exists())
            import_snapshot(self.snapshot, commit=True)
            repeat = import_snapshot(self.snapshot, commit=True)
        self.assertEqual(repeat["images_to_add"], 0)
        self.assertEqual(repeat["unchanged_products"], 1)
        rows = export_snapshot()["products"]
        self.assertEqual(rows["CM-source"], rows["CM-target"])
        self.target.refresh_from_db()
        self.assertEqual((self.target.price, self.target.stock_qty, self.target.status), (77, 19, "draft"))

    def test_missing_skus_fail_before_writes_and_explicit_skip_is_supported(self):
        self.snapshot["products"]["CM-missing"] = self.snapshot["products"]["CM-target"]
        with self.assertRaisesMessage(ValueError, "CM-missing"):
            import_snapshot(self.snapshot, commit=True)
        self.assertFalse(self.target.images.exists())
        result = import_snapshot(self.snapshot, commit=True, skip_missing=True)
        self.assertEqual(result["missing_skus"], ["CM-missing"])
        self.assertEqual(self.target.images.count(), 2)

    def test_different_existing_gallery_aborts_entire_transfer(self):
        self.snapshot["products"]["CM-source"] = deepcopy(self.snapshot["products"]["CM-target"])
        self.snapshot["products"]["CM-source"][0]["alt_text"] = "Conflicting gallery"
        with self.assertRaisesMessage(ValueError, "different images"):
            import_snapshot(self.snapshot, commit=True)
        self.assertFalse(self.target.images.exists())
        self.assertEqual(self.source.images.count(), 2)

    def test_wrong_cloud_and_malformed_payload_rejected_without_writes(self):
        for modify in (
            lambda s: s.update(cloud_name="another-cloud"),
            lambda s: s["products"]["CM-target"][0].update(image_original="https://example.test/image.jpg"),
            lambda s: s["products"]["CM-target"][1].update(is_primary=True),
            lambda s: s["products"]["CM-target"][0].update(product_id=self.source.pk),
        ):
            snapshot = deepcopy(self.snapshot)
            modify(snapshot)
            with self.assertRaises(ValueError):
                import_snapshot(snapshot, commit=True)
        self.assertFalse(self.target.images.exists())

    def test_cloudinary_record_deletion_preserves_shared_files(self):
        import_snapshot(self.snapshot, commit=True)
        with patch.object(CloudinaryMediaStorage, "_cloudinary_modules", side_effect=AssertionError("Deletion must not contact cloud")):
            with self.captureOnCommitCallbacks(execute=True):
                self.source.images.all().delete()
        self.assertEqual(self.target.images.count(), 2)

    def test_recropping_imported_image_creates_new_variants_without_changing_source(self):
        import_snapshot(self.snapshot, commit=True)
        original_source_paths = export_snapshot()["products"]["CM-source"]
        target_image = self.target.images.get(is_primary=True)
        buffer = BytesIO()
        Image.new("RGB", (40, 30), "red").save(buffer, format="PNG")
        original_bytes = buffer.getvalue()
        uploader = Mock()
        uploaded = {}

        def upload(content, **kwargs):
            self.assertFalse(kwargs["overwrite"])
            uploaded[kwargs["public_id"]] = content.read()
            return {"public_id": kwargs["public_id"], "format": "webp", "version": 1783415000}

        uploader.upload.side_effect = upload
        with patch.object(CloudinaryMediaStorage, "_open", side_effect=lambda *a, **k: ContentFile(original_bytes)), patch.object(CloudinaryMediaStorage, "_cloudinary_modules", return_value=(Mock(), uploader, Mock())):
            target_image.image_padding = 20
            target_image.save()
        self.assertEqual(len(uploaded), 3)
        for contents in uploaded.values():
            with Image.open(BytesIO(contents)) as variant:
                self.assertEqual(variant.format, "WEBP")
        self.assertEqual(export_snapshot()["products"]["CM-source"], original_source_paths)
        target_image.refresh_from_db()
        self.assertNotEqual(target_image.image_desktop.name, original_source_paths[0]["image_desktop"])
        uploader.destroy.assert_not_called()

    def test_console_encoded_round_trip_and_cache_invalidation(self):
        output = StringIO()
        call_command("export_product_images", output="-", encoded=True, stdout=output, stderr=StringIO())
        snapshot = json.loads(gzip.decompress(base64.b64decode(output.getvalue())))
        snapshot["products"] = {"CM-target": snapshot["products"]["CM-source"]}
        encoded = base64.b64encode(gzip.compress(json.dumps(snapshot).encode())).decode()
        with patch("catalog.management.commands.import_product_images.sys.stdin", StringIO(encoded)), patch("catalog.product_image_transfer.invalidate_groups") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                call_command("import_product_images", input="-", encoded=True, commit=True, stdout=StringIO())
            invalidate.assert_called_once()
        self.assertEqual(self.target.images.count(), 2)

    @override_settings(USE_CLOUDINARY_MEDIA=False)
    def test_local_filesystem_export_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "USE_CLOUDINARY_MEDIA"):
            export_snapshot()
