from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase

from catalog.crossmotors_import import (
    build_crossmotors_report,
    fetch_crossmotors_stock,
    import_crossmotors_report,
    import_crossmotors_report_bulk,
)
from catalog.models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductPlacement,
    ProductSide,
    ProductSpec,
    ProductStatus,
    SupplierProductBlock,
    VehicleMake,
    VehicleModel,
)


class CrossMotorsImportTests(TestCase):
    @patch("catalog.crossmotors_import.requests.get")
    def test_fetch_stock_omits_in_stock_only_by_default(self, mock_get):
        response = Mock(status_code=200)
        response.json.return_value = {"items": [], "synced_at": "2026-06-01 12:10:19"}
        mock_get.return_value = response

        items, meta = fetch_crossmotors_stock(
            base_url="https://example.test",
            token="token",
        )

        self.assertEqual(items, [])
        self.assertEqual(meta["synced_at"], "2026-06-01 12:10:19")
        self.assertNotIn("in_stock_only", mock_get.call_args.kwargs["params"])

    @patch("catalog.crossmotors_import.requests.get")
    def test_fetch_stock_keeps_explicit_in_stock_only_filter(self, mock_get):
        response = Mock(status_code=200)
        response.json.return_value = {"items": [], "synced_at": "2026-06-01 12:10:19"}
        mock_get.return_value = response

        fetch_crossmotors_stock(
            base_url="https://example.test",
            token="token",
            in_stock_only=False,
        )

        self.assertEqual(mock_get.call_args.kwargs["params"]["in_stock_only"], "false")

    def test_build_report_normalizes_non_original_item(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 1,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
            open_ended_year_to=2027,
        )

        self.assertEqual(report.data_row_count, 1)
        self.assertEqual(report.original_count, 0)
        self.assertEqual(report.valid_row_count, 1)

        values = report.rows[0].values
        self.assertEqual(values["sku"], "CM-000015")
        self.assertEqual(values["clean_name"], "წინა ფარი შავი")
        self.assertEqual(values["part_manufacturer"], "Suo Lun")
        self.assertEqual(values["vehicle_make"], "Subaru")
        self.assertEqual(values["vehicle_model"], "XV")
        self.assertEqual(values["year_from"], 2012)
        self.assertEqual(values["year_to"], 2017)
        self.assertEqual(values["placement"], ProductPlacement.FRONT)
        self.assertEqual(values["side"], ProductSide.RIGHT)
        self.assertEqual(values["category"], "ფარები და განათება")

    def test_build_report_excludes_original_items(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "001480",
                    "oem": "",
                    "name": "კაპოტი",
                    "brand": "Subaru - Original",
                    "model": "Subaru - Original",
                    "generation": "XV 13-17",
                    "manufacturer": "Subaru Original",
                    "qty": 0,
                    "dealer_price": None,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
        )

        self.assertEqual(report.original_count, 1)
        self.assertEqual(report.importable_count, 0)
        self.assertFalse(report.rows[0].is_valid)

    def test_build_report_keeps_aftermarket_original_analogs(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "003637",
                    "oem": "17a941035f",
                    "name": "წინა ფარი (Original) LH",
                    "brand": "Volkswagen",
                    "model": "Jetta",
                    "generation": "VW Jetta 19-",
                    "manufacturer": "Suo Lun",
                    "qty": 0,
                    "dealer_price": 240.0,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
            open_ended_year_to=2027,
        )

        self.assertEqual(report.original_count, 0)
        self.assertEqual(report.importable_count, 1)
        self.assertEqual(report.valid_row_count, 1)
        self.assertEqual(report.rows[0].values["sku"], "CM-003637")
        self.assertEqual(report.rows[0].values["part_manufacturer"], "Suo Lun")

    def test_build_report_flags_missing_price_without_rejecting_staging_rows(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "000020",
                    "oem": "",
                    "name": "სარკე (LH)",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 18-",
                    "manufacturer": "TYG",
                    "qty": 3,
                    "dealer_price": None,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
            open_ended_year_to=2027,
        )

        self.assertEqual(report.valid_row_count, 1)
        self.assertEqual(report.missing_price_count, 1)
        self.assertEqual(report.missing_price_in_stock_count, 1)
        self.assertIn("dealer_price is empty", report.rows[0].warnings[0])
        self.assertEqual(report.rows[0].values["year_from"], 2018)
        self.assertEqual(report.rows[0].values["year_to"], 2018)
        self.assertEqual(report.rows[0].values["short_description"], "სარკე - Subaru XV - 2018")

    def test_import_report_creates_catalog_records(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 6,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
        )

        result = import_crossmotors_report(report)

        self.assertEqual(result.created_products, 1)
        self.assertEqual(result.created_categories, 1)
        self.assertEqual(result.created_brands, 1)
        self.assertEqual(result.created_vehicle_makes, 1)
        self.assertEqual(result.created_vehicle_models, 1)
        self.assertEqual(result.created_fitments, 1)

        product = Product.objects.get(sku="CM-000015")
        self.assertEqual(product.name, "წინა ფარი (RH) შავი")
        self.assertEqual(product.manufacturer_part_number, "84001FJ090BK")
        self.assertEqual(product.brand.name, "Suo Lun")
        self.assertEqual(product.category.name, "ახალი")
        self.assertEqual(product.supplier_price, Decimal("250.00"))
        self.assertEqual(product.price, Decimal("250.00"))
        self.assertEqual(product.stock_qty, 6)
        self.assertEqual(product.placement, ProductPlacement.FRONT)
        self.assertEqual(product.side, ProductSide.RIGHT)
        self.assertEqual(product.status, ProductStatus.PUBLISHED)
        self.assertTrue(product.price_available)
        self.assertTrue(product.purchasable)

        fitment = ProductFitment.objects.get(product=product)
        self.assertEqual(fitment.vehicle_model.make.name, "Subaru")
        self.assertEqual(fitment.vehicle_model.name, "XV")
        self.assertEqual(fitment.year_from, 2012)
        self.assertEqual(fitment.year_to, 2017)
        self.assertEqual(fitment.notes, "XV 12-17")
        self.assertTrue(ProductSpec.objects.filter(product=product, key="მხარე", value="მარჯვენა").exists())

    def test_import_report_routes_new_products_to_new_category(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 6,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                },
                {
                    "code": "000016",
                    "oem": "",
                    "name": "ბამპერი წინა",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 1,
                    "dealer_price": 100.0,
                    "currency": "GEL",
                },
                {
                    "code": "000017",
                    "oem": "",
                    "name": "ზეთის ფილტრი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 1,
                    "dealer_price": 20.0,
                    "currency": "GEL",
                },
            ],
            product_queryset=Product.objects.none(),
        )

        result = import_crossmotors_report(report)

        new_category = Category.objects.get(name="ახალი")
        self.assertEqual(result.created_categories, 1)
        self.assertEqual(result.updated_categories, 0)
        self.assertEqual(Product.objects.get(sku="CM-000015").category, new_category)
        self.assertEqual(Product.objects.get(sku="CM-000016").category, new_category)
        self.assertEqual(Product.objects.get(sku="CM-000017").category, new_category)
        self.assertFalse(Category.objects.filter(name="ფარები და განათება").exists())
        self.assertFalse(Category.objects.filter(name="ვიზუალის ნაწილები").exists())
        self.assertFalse(Category.objects.filter(name="ძრავები და ფილტრები").exists())
        self.assertFalse(Category.objects.filter(name="განათება").exists())
        self.assertFalse(Category.objects.filter(name="ბამპერები და ცხაურები").exists())
        self.assertFalse(Category.objects.filter(name="ძრავი, ზეთები და ფილტრები").exists())

    def test_import_report_publishes_missing_price_with_zero_placeholder(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "000020",
                    "oem": "",
                    "name": "სარკე (LH)",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 18-",
                    "manufacturer": "TYG",
                    "qty": 3,
                    "dealer_price": None,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
            open_ended_year_to=2027,
        )

        import_crossmotors_report(report)

        product = Product.objects.get(sku="CM-000020")
        self.assertEqual(product.category.name, "ახალი")
        self.assertEqual(product.supplier_price, None)
        self.assertEqual(product.price, Decimal("0.00"))
        self.assertEqual(product.stock_qty, 3)
        self.assertEqual(product.status, ProductStatus.PUBLISHED)
        self.assertFalse(product.price_available)
        self.assertFalse(product.purchasable)

    def test_import_report_preserves_existing_product_category(self):
        manual_category = Category.objects.create(
            name="ხელით დალაგებული",
            slug="khelit-dalagebuli",
        )
        Product.objects.create(
            category=manual_category,
            name="Existing manually categorized",
            slug="existing-manually-categorized",
            sku="CM-000015",
            price=Decimal("10.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 7,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.all(),
        )

        result = import_crossmotors_report(report)

        product = Product.objects.get(sku="CM-000015")
        self.assertEqual(result.updated_products, 1)
        self.assertEqual(product.category, manual_category)
        self.assertEqual(product.supplier_price, Decimal("250.00"))
        self.assertEqual(product.price, Decimal("250.00"))
        self.assertEqual(product.stock_qty, 7)

    def test_import_report_archives_existing_original_product(self):
        category = Category.objects.create(name="Original", slug="original")
        brand = Brand.objects.create(name="Subaru Original", slug="subaru-original")
        Product.objects.create(
            category=category,
            brand=brand,
            name="Existing original",
            slug="existing-original",
            sku="CM-001480",
            price=Decimal("10.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        report = build_crossmotors_report(
            [
                {
                    "code": "001480",
                    "oem": "",
                    "name": "კაპოტი",
                    "brand": "Subaru - Original",
                    "model": "Subaru - Original",
                    "generation": "XV 13-17",
                    "manufacturer": "Subaru Original",
                    "qty": 0,
                    "dealer_price": None,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.all(),
        )

        result = import_crossmotors_report(report)

        self.assertEqual(result.archived_original_products, 1)
        self.assertEqual(Product.objects.get(sku="CM-001480").status, ProductStatus.ARCHIVED)

    def test_import_report_updates_idempotently(self):
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 1,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.none(),
        )

        import_crossmotors_report(report)
        second_report = build_crossmotors_report(
            [report.rows[0].raw],
            product_queryset=Product.objects.all(),
        )
        result = import_crossmotors_report(second_report)

        self.assertEqual(result.updated_products, 1)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(ProductFitment.objects.count(), 1)
        self.assertEqual(VehicleMake.objects.count(), 1)
        self.assertEqual(VehicleModel.objects.count(), 1)

    def test_import_report_skips_blocked_supplier_product(self):
        category = Category.objects.create(name="Lighting", slug="blocked-lighting")
        Product.objects.create(
            category=category,
            name="Archived supplier product",
            slug="archived-supplier-product",
            sku="CM-000015",
            price=Decimal("10.00"),
            stock_qty=1,
            status=ProductStatus.ARCHIVED,
        )
        SupplierProductBlock.objects.create(
            source_name="Cross Motors",
            supplier_sku="CM-000015",
        )
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 7,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                }
            ],
            product_queryset=Product.objects.all(),
        )

        result = import_crossmotors_report(report)

        product = Product.objects.get(sku="CM-000015")
        self.assertEqual(report.blocked_count, 1)
        self.assertEqual(report.update_count, 0)
        self.assertEqual(result.updated_products, 0)
        self.assertEqual(product.name, "Archived supplier product")
        self.assertEqual(product.price, Decimal("10.00"))
        self.assertEqual(product.stock_qty, 1)
        self.assertEqual(product.status, ProductStatus.ARCHIVED)

    def test_bulk_import_report_matches_core_import_behavior(self):
        manual_category = Category.objects.create(
            name="ხელით დალაგებული",
            slug="khelit-dalagebuli",
            markup_percent=Decimal("10.00"),
        )
        Product.objects.create(
            category=manual_category,
            name="Existing manually categorized",
            slug="existing-manually-categorized",
            sku="CM-000015",
            price=Decimal("10.00"),
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        report = build_crossmotors_report(
            [
                {
                    "code": "000015",
                    "oem": "84001FJ090BK",
                    "name": "წინა ფარი (RH) შავი",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 12-17",
                    "manufacturer": "Suo Lun",
                    "qty": 7,
                    "dealer_price": 250.0,
                    "currency": "GEL",
                },
                {
                    "code": "000020",
                    "oem": "",
                    "name": "სარკე (LH)",
                    "brand": "Subaru",
                    "model": "XV",
                    "generation": "XV 18-",
                    "manufacturer": "TYG",
                    "qty": 3,
                    "dealer_price": None,
                    "currency": "GEL",
                },
            ],
            product_queryset=Product.objects.all(),
            open_ended_year_to=2027,
        )

        result = import_crossmotors_report_bulk(report)

        self.assertEqual(result.created_products, 1)
        self.assertEqual(result.updated_products, 1)
        self.assertEqual(result.created_fitments, 2)

        existing = Product.objects.get(sku="CM-000015")
        self.assertEqual(existing.category, manual_category)
        self.assertEqual(existing.price, Decimal("275.00"))
        self.assertEqual(existing.stock_qty, 7)

        created = Product.objects.get(sku="CM-000020")
        self.assertEqual(created.category.name, "ახალი")
        self.assertEqual(created.supplier_price, None)
        self.assertEqual(created.price, Decimal("0.00"))
        self.assertEqual(created.brand.name, "TYG")
        self.assertTrue(
            ProductSpec.objects.filter(
                product=created,
                key="მხარე",
                value="მარცხენა",
            ).exists()
        )
