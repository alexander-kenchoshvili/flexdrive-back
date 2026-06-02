from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase

from catalog.crossmotors_import import (
    build_crossmotors_report,
    fetch_crossmotors_stock,
    import_crossmotors_report,
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
        self.assertEqual(values["category"], "განათება")

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
        self.assertEqual(report.rows[0].values["year_to"], 2027)

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
                    "qty": 1,
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
        self.assertEqual(product.category.name, "განათება")
        self.assertEqual(product.supplier_price, Decimal("250.00"))
        self.assertEqual(product.price, Decimal("250.00"))
        self.assertEqual(product.stock_qty, 1)
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
        self.assertEqual(product.supplier_price, None)
        self.assertEqual(product.price, Decimal("0.00"))
        self.assertEqual(product.stock_qty, 3)
        self.assertEqual(product.status, ProductStatus.PUBLISHED)
        self.assertFalse(product.price_available)
        self.assertFalse(product.purchasable)

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
