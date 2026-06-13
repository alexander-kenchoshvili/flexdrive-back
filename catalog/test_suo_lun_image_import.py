from decimal import Decimal
from io import BytesIO
import json
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from django.core.files.base import ContentFile
from django.test import TestCase
from PIL import Image

from catalog.models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductImage,
    ProductPlacement,
    ProductSide,
    ProductStatus,
    VehicleMake,
    VehicleModel,
)
from catalog.suo_lun_image_import import (
    CROSSMOTORS_STOREFRONT_PAGE_SIZE,
    CROSSMOTORS_STORES_APP_ID,
    CrossMotorsSourceProduct,
    attach_product_image,
    attach_product_images,
    build_external_suo_lun_image_report,
    build_suo_lun_image_report,
    download_candidate_image,
    fetch_crossmotors_storefront_access_token,
    fetch_crossmotors_storefront_products,
    import_review_approved_suo_lun_images,
    import_external_suo_lun_images,
    load_review_approved_suo_lun_image_matches,
    parse_crossmotors_page_products,
    parse_crossmotors_pages_sitemap,
    parse_crossmotors_product_sitemap,
    parse_crossmotors_storefront_collection_id,
    parse_crossmotors_storefront_products,
)


def _image_bytes(filename="product.jpg", *, color=(12, 34, 56), size=(1200, 800)):
    output = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(output, format="JPEG")
    output.seek(0)
    return ContentFile(output.read(), name=filename)


class SuoLunImageImportTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Body", slug="body")
        self.brand = Brand.objects.create(name="Suo Lun", slug="suo-lun")
        self.make = VehicleMake.objects.create(name="Subaru", slug="subaru")
        self.model = VehicleModel.objects.create(
            make=self.make,
            name="WRX",
            slug="wrx",
        )

    def _product(
        self,
        *,
        sku="CM-TEST",
        name="ცხაურა",
        side="",
        year_from=2022,
        year_to=2027,
    ):
        product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name=name,
            slug=sku.lower(),
            sku=sku,
            manufacturer_part_number="TEST-OEM",
            short_description=f"{name} - Subaru WRX - {year_from}-{year_to}",
            description=name,
            price=Decimal("25.00"),
            placement=ProductPlacement.FRONT,
            side=side,
            stock_qty=3,
            status=ProductStatus.PUBLISHED,
        )
        ProductFitment.objects.create(
            product=product,
            vehicle_model=self.model,
            year_from=year_from,
            year_to=year_to,
        )
        return product

    def _candidate(self, *, name="ცხაურა", vehicle="wrx 22", source_url_suffix="tskhara"):
        return CrossMotorsSourceProduct(
            source_url=f"https://www.crossmotors.ge/product-page/{source_url_suffix}",
            image_url="https://static.wixstatic.com/media/test.jpg/v1/fit/w_400,h_400/file.jpg",
            name=name,
            manufacturer="SL - China",
            source_page_url=f"https://www.crossmotors.ge/{vehicle.replace(' ', '-')}",
            source_vehicle_label=vehicle,
            source_year_from=2022,
            source_year_to=2027,
            source_model_tokens=("wrx",),
        )

    def test_exact_name_and_vehicle_context_auto_imports(self):
        product = self._product(name="ცხაურა")
        report = build_suo_lun_image_report([product], [self._candidate(name="ცხაურა")])

        match = report.matches[0]
        self.assertEqual(match.action, "auto_import")
        self.assertEqual(match.confidence, "high")
        self.assertEqual(match.reason, "exact_name_vehicle_context")

    def test_side_missing_requires_review(self):
        product = self._product(
            name="სანისლე ბუდე RH",
            side=ProductSide.RIGHT,
        )
        report = build_suo_lun_image_report([product], [self._candidate(name="სანისლე ბუდე")])

        match = report.matches[0]
        self.assertEqual(match.action, "review")
        self.assertEqual(match.reason, "needs_manual_review")

    def test_existing_image_is_skipped_by_default(self):
        product = self._product(name="ცხაურა")
        ProductImage.objects.create(
            product=product,
            image_original=_image_bytes(),
            is_primary=True,
            alt_text="Existing image",
        )
        product = Product.objects.prefetch_related("images", "fitments").get(pk=product.pk)

        report = build_suo_lun_image_report([product], [self._candidate(name="ცხაურა")])

        match = report.matches[0]
        self.assertEqual(match.action, "skip")
        self.assertEqual(match.reason, "existing_image")

    def test_attach_product_image_creates_primary_image(self):
        product = self._product(name="ცხაურა")

        with TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                image = attach_product_image(
                    product,
                    _image_bytes().read(),
                    "source-product.jpg",
                )

        self.assertIsNotNone(image)
        self.assertEqual(ProductImage.objects.filter(product=product).count(), 1)
        image.refresh_from_db()
        self.assertTrue(image.is_primary)
        self.assertTrue(image.image_desktop.name.endswith(".webp"))
        self.assertTrue(image.image_tablet.name.endswith(".webp"))
        self.assertTrue(image.image_mobile.name.endswith(".webp"))

    def test_attach_product_images_creates_primary_and_gallery_images(self):
        product = self._product(name="ცხაურა")

        with TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                images = attach_product_images(
                    product,
                    [
                        (_image_bytes("front.jpg").read(), "front.jpg"),
                        (_image_bytes("angle.jpg").read(), "angle.jpg"),
                    ],
                )

        self.assertEqual(len(images), 2)
        stored_images = list(ProductImage.objects.filter(product=product))
        self.assertEqual(len(stored_images), 2)
        self.assertTrue(stored_images[0].is_primary)
        self.assertFalse(stored_images[1].is_primary)
        self.assertEqual([image.sort_order for image in stored_images], [1, 2])

    def test_build_external_suo_lun_image_report_loads_auto_candidates(self):
        product = self._product(sku="CM-EXT", name="ტუმანიკის სამაგრი")
        payload = {
            "auto_import": [
                {
                    "sku": "CM-EXT",
                    "source": "subarupartsdeal",
                    "source_url": "https://example.test/part",
                    "source_title": "Subaru TEST-OEM Bracket",
                    "image_urls": [
                        "https://example.test/one.jpg",
                        "https://example.test/two.jpg",
                    ],
                    "action": "auto_import",
                    "confidence": "high",
                    "reason": "exact_oem_part_number_with_real_photos",
                }
            ],
            "review": [
                {
                    "sku": "CM-EXT",
                    "source": "topsmade",
                    "source_url": "https://example.test/review",
                    "source_title": "Review candidate",
                    "image_urls": ["https://example.test/review.jpg"],
                    "action": "review",
                    "confidence": "medium",
                    "reason": "needs_review",
                }
            ],
        }

        with TemporaryDirectory() as directory:
            candidate_path = f"{directory}/candidates.json"
            with open(candidate_path, "w", encoding="utf-8") as candidate_file:
                json.dump(payload, candidate_file)
            report = build_external_suo_lun_image_report(
                candidate_path,
                [product],
            )

        self.assertEqual(report.candidate_count, 2)
        self.assertEqual(report.auto_import_count, 1)
        self.assertEqual(report.review_count, 1)
        self.assertEqual(report.by_action("auto_import")[0].candidate.image_urls[1], "https://example.test/two.jpg")

    def test_load_review_approved_suo_lun_image_matches_uses_only_approved(self):
        approved_product = self._product(sku="CM-APPROVED", name="წინა ფარი")
        rejected_product = self._product(sku="CM-REJECTED", name="უკანა ფარი")
        decisions = {
            "decisions": {
                "CM-APPROVED": {"status": "approved"},
                "CM-REJECTED": {"status": "rejected"},
                "CM-MISSING": {"status": "approved"},
            }
        }
        review_items = [
            {
                "sku": "CM-APPROVED",
                "score": 1,
                "ambiguity_count": 1,
                "candidate": {
                    "source_url": "https://www.crossmotors.ge/product-page/headlight",
                    "image_url": "https://static.wixstatic.com/media/headlight.jpg",
                    "name": "წინა ფარი",
                    "manufacturer": "SL - China",
                    "source_page_url": "https://www.crossmotors.ge/wrx-22",
                    "source_vehicle_label": "wrx 22",
                },
            },
            {
                "sku": "CM-REJECTED",
                "candidate": {
                    "image_url": "https://static.wixstatic.com/media/rejected.jpg",
                },
            },
            {
                "sku": "CM-MISSING",
                "candidate": {
                    "image_url": "https://static.wixstatic.com/media/missing.jpg",
                },
            },
        ]

        with TemporaryDirectory() as directory:
            decisions_path = f"{directory}/decisions.json"
            review_data_path = f"{directory}/review-data.js"
            with open(decisions_path, "w", encoding="utf-8") as decisions_file:
                json.dump(decisions, decisions_file)
            with open(review_data_path, "w", encoding="utf-8") as review_file:
                review_file.write(
                    "window.SUO_LUN_REVIEW_ITEMS = "
                    + json.dumps(review_items, ensure_ascii=False)
                    + ";"
                )
            report = load_review_approved_suo_lun_image_matches(
                decisions_path,
                review_data_path,
                products=[approved_product, rejected_product],
            )

        self.assertEqual(report.approved_decision_count, 2)
        self.assertEqual(len(report.matches), 1)
        self.assertEqual(report.matches[0].product.sku, "CM-APPROVED")
        self.assertEqual(report.matches[0].action, "auto_import")
        self.assertEqual(report.matches[0].reason, "manual_review_approved")
        self.assertEqual(report.missing_product_skus, ("CM-MISSING",))

    def test_load_review_approved_suo_lun_image_matches_skips_existing_images(self):
        product = self._product(sku="CM-EXISTS", name="წინა ფარი")
        ProductImage.objects.create(
            product=product,
            image_original=_image_bytes(),
            is_primary=True,
            alt_text="Existing image",
        )
        decisions = {"decisions": {"CM-EXISTS": {"status": "approved"}}}
        review_items = [
            {
                "sku": "CM-EXISTS",
                "candidate": {
                    "image_url": "https://static.wixstatic.com/media/headlight.jpg",
                },
            }
        ]

        with TemporaryDirectory() as directory:
            decisions_path = f"{directory}/decisions.json"
            review_data_path = f"{directory}/review-data.json"
            with open(decisions_path, "w", encoding="utf-8") as decisions_file:
                json.dump(decisions, decisions_file)
            with open(review_data_path, "w", encoding="utf-8") as review_file:
                json.dump(review_items, review_file)
            report = load_review_approved_suo_lun_image_matches(
                decisions_path,
                review_data_path,
                products=[product],
            )

        self.assertEqual(report.matches, ())
        self.assertEqual(report.existing_image_skus, ("CM-EXISTS",))

    def test_import_review_approved_suo_lun_images_imports_single_image(self):
        product = self._product(sku="CM-APPROVED", name="წინა ფარი")
        decisions = {"decisions": {"CM-APPROVED": {"status": "approved"}}}
        review_items = [
            {
                "sku": "CM-APPROVED",
                "candidate": {
                    "source_url": "https://www.crossmotors.ge/product-page/headlight",
                    "image_url": "https://static.wixstatic.com/media/headlight.jpg",
                    "name": "წინა ფარი",
                    "manufacturer": "SL - China",
                    "source_page_url": "https://www.crossmotors.ge/wrx-22",
                    "source_vehicle_label": "wrx 22",
                },
            }
        ]
        response = Mock()
        response.content = _image_bytes("headlight.jpg").read()
        response.headers = {"Content-Type": "image/jpeg"}
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response

        with TemporaryDirectory() as directory:
            decisions_path = f"{directory}/decisions.json"
            review_data_path = f"{directory}/review-data.json"
            with open(decisions_path, "w", encoding="utf-8") as decisions_file:
                json.dump(decisions, decisions_file)
            with open(review_data_path, "w", encoding="utf-8") as review_file:
                json.dump(review_items, review_file)
            report = load_review_approved_suo_lun_image_matches(
                decisions_path,
                review_data_path,
                products=[product],
            )
            with self.settings(MEDIA_ROOT=directory):
                result = import_review_approved_suo_lun_images(
                    report.matches,
                    session=session,
                )

        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.errors, ())
        self.assertEqual(ProductImage.objects.filter(product=product).count(), 1)

    def test_import_external_suo_lun_images_imports_multiple_images(self):
        product = self._product(sku="CM-EXT", name="ტუმანიკის სამაგრი")
        payload = {
            "auto_import": [
                {
                    "sku": "CM-EXT",
                    "source": "subarupartsdeal",
                    "source_url": "https://example.test/part",
                    "source_title": "Subaru TEST-OEM Bracket",
                    "image_urls": [
                        "https://example.test/one.jpg",
                        "https://example.test/two.jpg",
                    ],
                    "action": "auto_import",
                    "confidence": "high",
                    "reason": "exact_oem_part_number_with_real_photos",
                }
            ]
        }
        first_response = Mock()
        first_response.content = _image_bytes("one.jpg").read()
        first_response.headers = {"Content-Type": "image/jpeg"}
        first_response.raise_for_status.return_value = None
        second_response = Mock()
        second_response.content = _image_bytes("two.jpg", color=(80, 90, 100)).read()
        second_response.headers = {"Content-Type": "image/jpeg"}
        second_response.raise_for_status.return_value = None
        session = Mock()
        session.get.side_effect = [first_response, second_response]

        with TemporaryDirectory() as directory:
            candidate_path = f"{directory}/candidates.json"
            with open(candidate_path, "w", encoding="utf-8") as candidate_file:
                json.dump(payload, candidate_file)
            report = build_external_suo_lun_image_report(
                candidate_path,
                [product],
            )
            with self.settings(MEDIA_ROOT=directory):
                result = import_external_suo_lun_images(
                    report.by_action("auto_import"),
                    session=session,
                )

        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.errors, ())
        self.assertEqual(ProductImage.objects.filter(product=product).count(), 2)

    def test_parse_crossmotors_sitemaps_and_page_cards(self):
        product_sitemap = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
          xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
          <url>
            <loc>https://www.crossmotors.ge/product-page/ცხაურა</loc>
            <image:image>
              <image:loc>https://static.wixstatic.com/media/grille.jpg</image:loc>
            </image:image>
          </url>
        </urlset>
        """
        pages_sitemap = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://www.crossmotors.ge/wrx-22</loc></url>
        </urlset>
        """
        page_html = """
        <li data-hook="product-list-grid-item">
          <div data-slug="ცხაურა" aria-label="ცხაურა. SL - China gallery"
               data-hook="product-item-root">
            <a href="https://www.crossmotors.ge/product-page/ცხაურა"></a>
          </div>
        </li>
        """

        image_by_url = parse_crossmotors_product_sitemap(product_sitemap)
        page_urls = parse_crossmotors_pages_sitemap(pages_sitemap)
        candidates = parse_crossmotors_page_products(
            page_urls[0],
            page_html,
            image_by_url=image_by_url,
        )

        self.assertEqual(image_by_url["https://www.crossmotors.ge/product-page/ცხაურა"], "https://static.wixstatic.com/media/grille.jpg")
        self.assertEqual(page_urls, ("https://www.crossmotors.ge/wrx-22",))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "ცხაურა")
        self.assertEqual(candidates[0].manufacturer, "SL - China")
        self.assertEqual(candidates[0].source_model_tokens, ("wrx",))

    def test_parse_crossmotors_storefront_collection_id(self):
        page_html = """
        <script>
          window.viewerModel = {"catalog":{"isCatalogV3":false,"category":{"id":"eff0c4c5-a0a1-e01e-7c38-0f8019686fd9","name":"Outback 2020-2021","visible":true,"productsWithMetaData":{"list":[]}}}};
        </script>
        """

        collection_id = parse_crossmotors_storefront_collection_id(page_html)

        self.assertEqual(collection_id, "eff0c4c5-a0a1-e01e-7c38-0f8019686fd9")

    def test_parse_crossmotors_storefront_products(self):
        candidates = parse_crossmotors_storefront_products(
            "https://www.crossmotors.ge/outback-2020-2021",
            [
                {
                    "ribbon": "SL - China",
                    "name": "ცხაურა",
                    "urlPart": "ცხაურა-1",
                    "media": [
                        {
                            "fullUrl": "https://static.wixstatic.com/media/grille.jpg",
                        }
                    ],
                },
                {
                    "ribbon": "TYG - TW",
                    "name": "კაპოტი",
                    "urlPart": "კაპოტი",
                    "media": [
                        {
                            "fullUrl": "https://static.wixstatic.com/media/hood.jpg",
                        }
                    ],
                },
            ],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "ცხაურა")
        self.assertEqual(candidates[0].manufacturer, "SL - China")
        self.assertEqual(candidates[0].image_url, "https://static.wixstatic.com/media/grille.jpg")
        self.assertEqual(
            candidates[0].source_url,
            "https://www.crossmotors.ge/product-page/ცხაურა-1",
        )
        self.assertEqual(candidates[0].source_year_from, 2020)
        self.assertEqual(candidates[0].source_year_to, 2021)
        self.assertEqual(candidates[0].source_model_tokens, ("outback",))

    def test_fetch_crossmotors_storefront_access_token(self):
        response = Mock()
        response.json.return_value = {
            "apps": {
                CROSSMOTORS_STORES_APP_ID: {
                    "accessToken": "storefront-token",
                }
            }
        }
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response

        token = fetch_crossmotors_storefront_access_token(
            session,
            timeout=30,
            headers={"User-Agent": "test"},
        )

        self.assertEqual(token, "storefront-token")

    def test_fetch_crossmotors_storefront_products_paginates(self):
        first_page_products = [
            {
                "ribbon": "SL - China",
                "name": f"ცხაურა {index}",
                "urlPart": f"ცხაურა-{index}",
                "media": [
                    {
                        "fullUrl": f"https://static.wixstatic.com/media/grille-{index}.jpg",
                    }
                ],
            }
            for index in range(CROSSMOTORS_STOREFRONT_PAGE_SIZE)
        ]
        second_page_products = [
            {
                "ribbon": "SL - China",
                "name": "ბოლო ნაწილი",
                "urlPart": "ბოლო-ნაწილი",
                "media": [
                    {
                        "fullUrl": "https://static.wixstatic.com/media/last.jpg",
                    }
                ],
            }
        ]
        first_response = Mock()
        first_response.json.return_value = {
            "data": {
                "catalog": {
                    "category": {
                        "productsWithMetaData": {
                            "totalCount": CROSSMOTORS_STOREFRONT_PAGE_SIZE + 1,
                            "list": first_page_products,
                        }
                    }
                }
            }
        }
        first_response.raise_for_status.return_value = None
        second_response = Mock()
        second_response.json.return_value = {
            "data": {
                "catalog": {
                    "category": {
                        "productsWithMetaData": {
                            "totalCount": CROSSMOTORS_STOREFRONT_PAGE_SIZE + 1,
                            "list": second_page_products,
                        }
                    }
                }
            }
        }
        second_response.raise_for_status.return_value = None
        session = Mock()
        session.post.side_effect = [first_response, second_response]

        candidates = fetch_crossmotors_storefront_products(
            session,
            "https://www.crossmotors.ge/outback-2020-2021",
            "eff0c4c5-a0a1-e01e-7c38-0f8019686fd9",
            "storefront-token",
            timeout=30,
            headers={"User-Agent": "test"},
        )

        self.assertEqual(len(candidates), CROSSMOTORS_STOREFRONT_PAGE_SIZE + 1)
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(candidates[-1].name, "ბოლო ნაწილი")

    def test_download_candidate_image_rejects_invalid_content(self):
        response = Mock()
        response.content = b"not an image"
        response.headers = {"Content-Type": "text/plain"}
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response

        with self.assertRaises(ValueError):
            download_candidate_image("https://example.test/not-image.txt", session=session)
