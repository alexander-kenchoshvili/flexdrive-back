import os

from django.core.management.base import BaseCommand, CommandError

from catalog.crossmotors_import import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    build_crossmotors_report,
    fetch_crossmotors_stock,
    import_crossmotors_report,
)


ENV_BASE_URL = "CROSSMOTORS_API_BASE_URL"
ENV_TOKEN = "CROSSMOTORS_API_TOKEN"
ENV_PAGE_SIZE = "CROSSMOTORS_API_PAGE_SIZE"
ENV_TIMEOUT = "CROSSMOTORS_API_TIMEOUT"


class Command(BaseCommand):
    help = (
        "Read products from the Cross Motors REST API. Defaults to a dry-run report; "
        "writes catalog data only when --commit is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            help=f"Cross Motors API base URL. If omitted, {ENV_BASE_URL} or {DEFAULT_BASE_URL} is used.",
        )
        parser.add_argument(
            "--token",
            help=f"Cross Motors API bearer token. If omitted, {ENV_TOKEN} is used.",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            help=f"API page size. If omitted, {ENV_PAGE_SIZE} or {DEFAULT_PAGE_SIZE} is used.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            help=f"API request timeout in seconds. If omitted, {ENV_TIMEOUT} or {DEFAULT_TIMEOUT} is used.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=DEFAULT_MAX_PAGES,
            help=f"Maximum API pages to read (default: {DEFAULT_MAX_PAGES}).",
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
            help="Create/update catalog products, brands, categories, fitments and specs.",
        )
        parser.add_argument(
            "--archive-missing",
            action="store_true",
            help=(
                "When used with --commit, archive existing CM-* products that are not present "
                "in the current supplier feed."
            ),
        )

    def handle(self, *args, **options):
        try:
            resolved_options = _resolve_import_options(options, os.environ)
            items, api_meta = fetch_crossmotors_stock(
                base_url=resolved_options["base_url"],
                token=resolved_options["token"],
                page_size=resolved_options["page_size"],
                timeout=resolved_options["timeout"],
                max_pages=options["max_pages"],
            )
            report = build_crossmotors_report(
                items,
                synced_at=api_meta.get("synced_at", ""),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self._print_report(
            report,
            page_sizes=api_meta.get("page_sizes") or [],
            sample_size=options["sample_size"],
            committed=options["commit"],
        )

        if report.error_count:
            raise CommandError(
                "Cross Motors data has validation errors. No database changes were made."
            )

        if not options["commit"]:
            self._write("")
            self._write("Dry-run only. No database changes were made.")
            self._write("Pass --commit to apply this import after reviewing the report.")
            return

        try:
            result = import_crossmotors_report(
                report,
                archive_missing=options["archive_missing"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self._print_import_result(result)

    def _print_report(self, report, *, page_sizes, sample_size, committed):
        mode_label = "commit" if committed else "dry-run"

        self._write(f"Cross Motors {mode_label} check completed.", style_func=self.style.SUCCESS)
        self._write("")
        self._write(f"Supplier sync timestamp: {report.synced_at or 'not provided'}")
        self._write(f"API page sizes: {', '.join(str(size) for size in page_sizes) or 'n/a'}")
        self._write("")
        self._write(f"API rows: {report.data_row_count}")
        self._write(f"Original rows excluded: {report.original_count}")
        self._write(f"Non-original rows: {report.importable_count}")
        self._write(f"Valid import rows: {report.valid_row_count}")
        self._write(f"Validation errors: {report.error_count}")
        self._write(f"Warnings: {report.warning_count}")
        self._write("")
        self._write("Database preview by SKU:")
        self._write(f"  Would create: {report.create_count}")
        self._write(f"  Would update: {report.update_count}")
        self._write("")
        self._write("Data quality:")
        self._write(f"  Missing prices: {report.missing_price_count}")
        self._write(f"  Missing prices but in stock: {report.missing_price_in_stock_count}")
        self._write(f"  Purchase-ready rows: {report.purchase_ready_count}")
        self._write(f"  Out of stock rows: {report.out_of_stock_count}")
        self._write(f"  Missing generation: {report.missing_generation_count}")
        self._write(f"  Unparsed generation: {report.unparsed_generation_count}")
        self._write(f"  Missing manufacturer: {report.missing_manufacturer_count}")
        self._write(f"  Unknown category fallback: {report.unknown_category_count}")
        self._write("")
        self._print_unique_values(report, "category", "Categories")
        self._print_unique_values(report, "part_manufacturer", "Part manufacturers")
        self._print_unique_values(report, "vehicle_make", "Vehicle makes")
        self._write("")
        self._print_issues(report)
        self._print_samples(report, sample_size=sample_size)

    def _print_import_result(self, result):
        self._write("")
        self._write("Cross Motors database import applied.", style_func=self.style.SUCCESS)
        self._write(f"Products created: {result.created_products}")
        self._write(f"Products updated: {result.updated_products}")
        self._write(f"Original products archived: {result.archived_original_products}")
        self._write(f"Missing feed products archived: {result.archived_missing_products}")
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
        self._write(f"Fitments created: {result.created_fitments}")
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
        rows_with_errors = [row for row in report.rows if row.errors and not row.excluded_reason]
        rows_with_warnings = [row for row in report.rows if row.warnings and not row.excluded_reason]

        if rows_with_errors:
            self._write("Validation errors:", style_func=self.style.ERROR)
            for row in rows_with_errors[:20]:
                self._write(f"  Row {row.row_number}: {'; '.join(row.errors)}")
            if len(rows_with_errors) > 20:
                self._write(f"  +{len(rows_with_errors) - 20} more rows with errors")
            self._write("")

        if rows_with_warnings:
            self._write("Warnings:", style_func=self.style.WARNING)
            for row in rows_with_warnings[:20]:
                self._write(f"  Row {row.row_number}: {'; '.join(row.warnings)}")
            if len(rows_with_warnings) > 20:
                self._write(f"  +{len(rows_with_warnings) - 20} more rows with warnings")
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
                )
                if part
            )
            supplier_price = values.get("supplier_price")
            price_label = f"{supplier_price} GEL" if supplier_price is not None else "0.00 GEL placeholder"
            self._write(
                "  "
                f"Row {row.row_number}: "
                f"{values.get('sku')} | {values.get('name')} | "
                f"{values.get('category')} | {values.get('part_manufacturer') or '-'} | "
                f"supplier {price_label} | stock {values.get('stock_qty')} | "
                f"{fitment}"
            )

    def _write(self, message="", *, style_func=None):
        safe_message = _safe_console_text(str(message), self.stdout)
        if style_func:
            safe_message = style_func(safe_message)
        self.stdout.write(safe_message)


def _resolve_import_options(options, environ):
    token = options.get("token") or environ.get(ENV_TOKEN)
    if not token:
        raise CommandError(f"Pass --token or set {ENV_TOKEN}.")

    return {
        "base_url": options.get("base_url") or environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL,
        "token": token,
        "page_size": (
            options.get("page_size")
            or _parse_positive_int(environ.get(ENV_PAGE_SIZE), DEFAULT_PAGE_SIZE)
        ),
        "timeout": (
            options.get("timeout")
            or _parse_positive_int(environ.get(ENV_TIMEOUT), DEFAULT_TIMEOUT)
        ),
    }


def _parse_positive_int(value, default):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CommandError("Environment integer option must be a positive integer.") from exc
    if parsed <= 0:
        raise CommandError("Environment integer option must be a positive integer.")
    return parsed


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
