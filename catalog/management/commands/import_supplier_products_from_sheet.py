from django.core.management.base import BaseCommand, CommandError

from catalog.supplier_sheet_import import (
    build_supplier_sheet_report,
    fetch_sheet_values,
    import_supplier_sheet_report,
)


class Command(BaseCommand):
    help = (
        "Read supplier products from a Google Sheet. Defaults to a dry-run report; "
        "writes catalog data only when --commit is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--credentials-file",
            required=True,
            help="Path to the Google service account JSON key file.",
        )
        parser.add_argument(
            "--spreadsheet-id",
            required=True,
            help="Google Sheets spreadsheet ID.",
        )
        parser.add_argument(
            "--sheet-name",
            default="Products",
            help="Sheet tab name containing product rows (default: Products).",
        )
        parser.add_argument(
            "--range",
            default="A:T",
            dest="cell_range",
            help="A1 cell range without the sheet name (default: A:T).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Google Sheets API request timeout in seconds (default: 30).",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=5,
            help="Number of mapped valid rows to show in the report (default: 5).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Create/update catalog products, categories, brands, fitments and specs.",
        )

    def handle(self, *args, **options):
        try:
            values = fetch_sheet_values(
                credentials_file=options["credentials_file"],
                spreadsheet_id=options["spreadsheet_id"],
                sheet_name=options["sheet_name"],
                cell_range=options["cell_range"],
                timeout=options["timeout"],
            )
            report = build_supplier_sheet_report(
                spreadsheet_id=options["spreadsheet_id"],
                sheet_name=options["sheet_name"],
                values=values,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self._print_report(
            report,
            sample_size=options["sample_size"],
            committed=options["commit"],
        )

        if report.error_count:
            raise CommandError(
                "Supplier sheet has validation errors. No database changes were made."
            )

        if not options["commit"]:
            self._write("")
            self._write("Dry-run only. No database changes were made.")
            self._write("Pass --commit to apply this import after reviewing the report.")
            return

        try:
            result = import_supplier_sheet_report(report)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self._print_import_result(result)

    def _print_report(self, report, *, sample_size, committed):
        active_count, inactive_count = report.active_counts()
        mode_label = "commit" if committed else "dry-run"

        self._write(f"Supplier sheet {mode_label} check completed.", style_func=self.style.SUCCESS)
        self._write("")
        self._write(f"Spreadsheet: {report.spreadsheet_id}")
        self._write(f"Sheet: {report.sheet_name}")
        self._write(f"Headers: {', '.join(report.headers)}")
        self._write("")
        self._write(f"Data rows: {report.data_row_count}")
        self._write(f"Valid rows: {report.valid_row_count}")
        self._write(f"Validation errors: {report.error_count}")
        self._write(f"Warnings: {report.warning_count}")
        self._write(f"Active rows: {active_count}")
        self._write(f"Inactive rows: {inactive_count}")
        self._write("")
        self._write("Database preview by SKU:")
        self._write(f"  Would create: {report.create_count}")
        self._write(f"  Would update: {report.update_count}")
        self._write("")
        self._print_unique_values(report, "category", "Categories")
        self._print_unique_values(report, "brand", "Brands")
        self._print_unique_values(report, "vehicle_make", "Vehicle makes")
        self._print_unique_values(report, "condition", "Conditions")
        self._write("")
        self._print_issues(report)
        self._print_samples(report, sample_size=sample_size)

    def _print_import_result(self, result):
        self._write("")
        self._write("Database import applied.", style_func=self.style.SUCCESS)
        self._write(f"Products created: {result.created_products}")
        self._write(f"Products updated: {result.updated_products}")
        self._write(f"Categories created/existing: {result.created_categories}/{result.updated_categories}")
        self._write(f"Brands created/existing: {result.created_brands}/{result.updated_brands}")
        self._write(
            "Vehicle makes created/existing: "
            f"{result.created_vehicle_makes}/{result.updated_vehicle_makes}"
        )
        self._write(
            "Vehicle models created/existing: "
            f"{result.created_vehicle_models}/{result.updated_vehicle_models}"
        )
        self._write(
            "Vehicle engines created/existing: "
            f"{result.created_vehicle_engines}/{result.updated_vehicle_engines}"
        )
        self._write(f"Fitments created/updated: {result.created_fitments}/{result.updated_fitments}")
        self._write(f"Specs created/updated: {result.created_specs}/{result.updated_specs}")

    def _print_unique_values(self, report, key, label):
        values = report.unique_values(key)
        preview = ", ".join(values[:15])
        if len(values) > 15:
            preview = f"{preview}, +{len(values) - 15} more"
        self._write(f"{label}: {len(values)}")
        if preview:
            self._write(f"  {preview}")

    def _print_issues(self, report):
        rows_with_errors = [row for row in report.rows if row.errors]
        rows_with_warnings = [row for row in report.rows if row.warnings]

        if rows_with_errors:
            self._write("Validation errors:", style_func=self.style.ERROR)
            for row in rows_with_errors[:20]:
                self._write(f"  Row {row.row_number}: {'; '.join(row.errors)}")
            if len(rows_with_errors) > 20:
                self._write(f"  +{len(rows_with_errors) - 20} more rows with errors")
            self._write("")

        if rows_with_warnings:
            self._write("Warnings:", style_func=self.style.WARNING)
            for row in rows_with_warnings[:10]:
                self._write(f"  Row {row.row_number}: {'; '.join(row.warnings)}")
            if len(rows_with_warnings) > 10:
                self._write(f"  +{len(rows_with_warnings) - 10} more rows with warnings")
            self._write("")

    def _print_samples(self, report, *, sample_size):
        valid_rows = [row for row in report.rows if row.is_valid]
        if not valid_rows or sample_size <= 0:
            return

        self._write("Mapped sample rows:")
        for row in valid_rows[:sample_size]:
            values = row.values
            fitment = " ".join(
                str(part)
                for part in (
                    values.get("vehicle_make"),
                    values.get("vehicle_model"),
                    _format_year_range(values.get("year_from"), values.get("year_to")),
                    values.get("engine"),
                )
                if part
            )
            self._write(
                "  "
                f"Row {row.row_number}: "
                f"{values.get('sku')} | {values.get('name')} | "
                f"{values.get('category')} | {values.get('brand')} | "
                f"supplier {values.get('supplier_price')} GEL | stock {values.get('stock_qty')} | "
                f"{fitment}"
            )

    def _write(self, message="", *, style_func=None):
        safe_message = _safe_console_text(str(message), self.stdout)
        if style_func:
            safe_message = style_func(safe_message)
        self.stdout.write(safe_message)


def _format_year_range(year_from, year_to):
    if not year_from and not year_to:
        return ""
    if year_from == year_to:
        return str(year_from)
    return f"{year_from}-{year_to}"


def _safe_console_text(message, output_wrapper):
    stream = getattr(output_wrapper, "_out", None)
    encoding = getattr(stream, "encoding", None) or getattr(output_wrapper, "encoding", None)
    if not encoding:
        return message

    try:
        message.encode(encoding)
    except UnicodeEncodeError:
        return message.encode(encoding, errors="backslashreplace").decode(encoding)

    return message
