from decimal import Decimal

from django.test import TestCase

from catalog.admin import CategoryAdmin
from catalog.models import (
    Brand,
    Category,
    Product,
    ProductFitment,
    ProductSpec,
    ProductStatus,
    VehicleEngine,
    VehicleMake,
    VehicleModel,
)
from catalog.supplier_sheet_import import (
    build_supplier_sheet_report,
    import_supplier_sheet_report,
)


class SupplierSheetImportReportTests(TestCase):
    def test_build_report_accepts_valid_rows_with_missing_trailing_optional_values(self):
        values = [
            [
                "sku",
                "supplier_sku",
                "name_ka",
                "name_en",
                "description_ka",
                "category",
                "part_brand",
                "price_gel",
                "stock_quantity",
                "condition",
                "vehicle_make",
                "vehicle_model",
                "year_from",
                "year_to",
                "engine",
                "compatibility_notes",
                "image_url",
                "supplier_name",
                "is_active",
                "currency",
            ],
            [
                "FD-0001",
                "SUP-1",
                "წინა ფარი",
                "Headlight",
                "აღწერა",
                "განათება",
                "TYC",
                77,
                12,
                "New",
                "Toyota",
                "Camry",
                2009,
                2013,
                "1.6L",
                "Fits Camry",
                "",
                "FlexDrive Test Supplier",
                True,
                "GEL",
            ],
            [
                "FD-0002",
                "SUP-2",
                "უკანა ფარი",
                "Tail Light",
                "აღწერა",
                "განათება",
                "Denso",
                114,
                19,
                "Aftermarket",
                "Honda",
                "Corolla",
                2010,
                2014,
                "1.8L",
                "Fits Corolla",
            ],
        ]

        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
            product_queryset=Product.objects.none(),
        )

        self.assertEqual(report.data_row_count, 2)
        self.assertEqual(report.valid_row_count, 2)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.create_count, 2)
        self.assertEqual(report.update_count, 0)
        self.assertEqual(report.active_counts(), (2, 0))
        self.assertEqual(report.rows[1].values["currency"], "GEL")

    def test_build_report_marks_existing_skus_as_updates(self):
        category = self._create_category()
        product = Product.objects.create(
            category=category,
            name="Existing",
            slug="existing",
            sku="FD-0001",
            price="10.00",
            stock_qty=1,
        )
        values = [
            ["sku", "name_ka", "category", "price_gel", "stock_quantity"],
            [product.sku, "Existing update", "განათება", 12, 5],
            ["FD-0002", "New product", "განათება", 20, 3],
        ]

        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
        )

        self.assertEqual(report.create_count, 1)
        self.assertEqual(report.update_count, 1)

    def test_build_report_returns_validation_errors_for_invalid_numeric_values(self):
        values = [
            ["sku", "name_ka", "category", "price_gel", "stock_quantity"],
            ["FD-0001", "წინა ფარი", "განათება", "bad-price", -1],
        ]

        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
            product_queryset=Product.objects.none(),
        )

        self.assertEqual(report.valid_row_count, 0)
        self.assertEqual(report.error_count, 2)
        self.assertIn("price_gel must be a decimal number.", report.rows[0].errors)
        self.assertIn(
            "stock_quantity must be greater than or equal to 0.",
            report.rows[0].errors,
        )

    def test_build_report_validates_fitment_year_range(self):
        values = [
            [
                "sku",
                "name_ka",
                "category",
                "price_gel",
                "stock_quantity",
                "year_from",
                "year_to",
            ],
            ["FD-0001", "წინა ფარი", "განათება", 77, 12, 2020, 2010],
        ]

        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
            product_queryset=Product.objects.none(),
        )

        self.assertEqual(report.valid_row_count, 0)
        self.assertIn("year_from cannot be greater than year_to.", report.rows[0].errors)

    def test_import_supplier_sheet_report_creates_catalog_records(self):
        values = [
            [
                "sku",
                "name_ka",
                "description_ka",
                "category",
                "part_brand",
                "price_gel",
                "stock_quantity",
                "condition",
                "vehicle_make",
                "vehicle_model",
                "year_from",
                "year_to",
                "engine",
                "compatibility_notes",
            ],
            [
                "FD-0001",
                "წინა ფარი",
                "წინა ფარი სატესტო აღწერა",
                "განათება",
                "TYC",
                77,
                12,
                "New",
                "Toyota",
                "Camry",
                2009,
                2013,
                "1.6L",
                "Fits Toyota Camry",
            ],
        ]
        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
            product_queryset=Product.objects.none(),
        )

        result = import_supplier_sheet_report(report)

        self.assertEqual(result.created_products, 1)
        self.assertEqual(result.created_categories, 1)
        self.assertEqual(result.created_brands, 1)
        self.assertEqual(result.created_vehicle_makes, 1)
        self.assertEqual(result.created_vehicle_models, 1)
        self.assertEqual(result.created_vehicle_engines, 1)
        self.assertEqual(result.created_fitments, 1)
        self.assertEqual(result.created_specs, 1)

        product = Product.objects.get(sku="FD-0001")
        self.assertEqual(product.name, "წინა ფარი")
        self.assertEqual(product.category.name, "განათება")
        self.assertEqual(product.brand.name, "TYC")
        self.assertEqual(product.supplier_price, 77)
        self.assertEqual(product.price, 77)
        self.assertEqual(product.stock_qty, 12)
        self.assertEqual(product.status, ProductStatus.PUBLISHED)

        self.assertEqual(Category.objects.filter(name="განათება").count(), 1)
        self.assertEqual(Brand.objects.filter(name="TYC").count(), 1)
        self.assertEqual(VehicleMake.objects.filter(name="Toyota").count(), 1)
        self.assertEqual(VehicleModel.objects.filter(name="Camry").count(), 1)
        self.assertEqual(VehicleEngine.objects.filter(name="1.6L").count(), 1)
        self.assertEqual(ProductFitment.objects.count(), 1)
        self.assertEqual(ProductSpec.objects.get(product=product).value, "ახალი")

    def test_import_supplier_sheet_report_updates_existing_product_idempotently(self):
        category = self._create_category()
        product = Product.objects.create(
            category=category,
            name="Old name",
            slug="old-name-fd-0001",
            sku="FD-0001",
            price="10.00",
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        values = [
            [
                "sku",
                "name_ka",
                "category",
                "part_brand",
                "price_gel",
                "stock_quantity",
                "condition",
                "vehicle_make",
                "vehicle_model",
                "year_from",
                "year_to",
            ],
            [
                "FD-0001",
                "Updated name",
                "განათება",
                "TYC",
                120,
                5,
                "Used - Good",
                "Toyota",
                "Camry",
                2012,
                2015,
            ],
        ]
        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
        )

        first_result = import_supplier_sheet_report(report)
        second_report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
        )
        second_result = import_supplier_sheet_report(second_report)

        product.refresh_from_db()
        self.assertEqual(product.name, "Updated name")
        self.assertEqual(product.slug, "old-name-fd-0001")
        self.assertEqual(product.supplier_price, 120)
        self.assertEqual(product.price, 120)
        self.assertEqual(product.stock_qty, 5)
        self.assertEqual(first_result.updated_products, 1)
        self.assertEqual(second_result.updated_products, 1)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(ProductFitment.objects.count(), 1)
        self.assertEqual(ProductSpec.objects.get(product=product).value, "მეორადი - კარგი")

    def test_import_supplier_sheet_report_calculates_price_from_category_markup(self):
        category = self._create_category(markup_percent=Decimal("30.00"))
        values = [
            ["sku", "name_ka", "category", "price_gel", "stock_quantity"],
            ["FD-0001", "წინა ფარი", category.name, 100, 12],
        ]
        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
            product_queryset=Product.objects.none(),
        )

        import_supplier_sheet_report(report)

        product = Product.objects.get(sku="FD-0001")
        self.assertEqual(product.supplier_price, Decimal("100.00"))
        self.assertEqual(product.effective_markup_percent, Decimal("30.00"))
        self.assertEqual(product.price, Decimal("130.00"))

    def test_import_supplier_sheet_report_uses_product_markup_override(self):
        category = self._create_category(markup_percent=Decimal("30.00"))
        product = Product.objects.create(
            category=category,
            name="Existing",
            slug="existing-fd-0001",
            sku="FD-0001",
            price="10.00",
            supplier_price="10.00",
            markup_percent_override="50.00",
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        values = [
            ["sku", "name_ka", "category", "price_gel", "stock_quantity"],
            ["FD-0001", "Existing", category.name, 100, 12],
        ]
        report = build_supplier_sheet_report(
            spreadsheet_id="spreadsheet-id",
            sheet_name="Products",
            values=values,
        )

        import_supplier_sheet_report(report)

        product.refresh_from_db()
        self.assertEqual(product.supplier_price, Decimal("100.00"))
        self.assertEqual(product.effective_markup_percent, Decimal("50.00"))
        self.assertEqual(product.price, Decimal("150.00"))

    def test_category_admin_recalculates_prices_for_products_without_override(self):
        category = self._create_category(markup_percent=Decimal("30.00"))
        product = Product.objects.create(
            category=category,
            name="Category priced",
            slug="category-priced",
            sku="FD-0001",
            price="1.00",
            supplier_price="100.00",
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )
        overridden = Product.objects.create(
            category=category,
            name="Override priced",
            slug="override-priced",
            sku="FD-0002",
            price="1.00",
            supplier_price="100.00",
            markup_percent_override="50.00",
            stock_qty=1,
            status=ProductStatus.PUBLISHED,
        )

        category.markup_percent = Decimal("35.00")
        category.save(update_fields=["markup_percent", "updated_at"])
        CategoryAdmin._recalculate_category_product_prices(category)

        product.refresh_from_db()
        overridden.refresh_from_db()
        self.assertEqual(product.price, Decimal("135.00"))
        self.assertEqual(overridden.price, Decimal("150.00"))

    def _create_category(self, *, markup_percent=Decimal("0.00")):
        return Category.objects.create(
            name="განათება",
            slug="ganateba",
            is_active=True,
            markup_percent=markup_percent,
        )
