import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from catalog.suo_lun_gallery_backup_import import (
    build_gallery_backup_report,
    import_gallery_backup_matches,
)


class Command(BaseCommand):
    help = (
        "Import the locally retained images for schema-v6 Approved Suo Lun review "
        "cards. Defaults to a dry-run and refuses non-local databases."
    )

    def add_arguments(self, parser):
        parser.add_argument("--backup-path", required=True)
        parser.add_argument("--html-path", required=True)
        parser.add_argument("--assets-dir", required=True)
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Attach retained local images to products without existing images.",
        )
        parser.add_argument("--limit", type=int)
        parser.add_argument("--report-path")
        parser.add_argument("--sample-size", type=int, default=12)

    def handle(self, *args, **options):
        if options.get("limit") is not None and options["limit"] <= 0:
            raise CommandError("--limit must be positive when provided.")
        if options["sample_size"] < 0:
            raise CommandError("--sample-size cannot be negative.")

        self._assert_local_environment()

        try:
            report = build_gallery_backup_report(
                options["backup_path"],
                options["html_path"],
                options["assets_dir"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self._print_report(report, options["sample_size"])
        if options["report_path"]:
            self._write_report(options["report_path"], report, result=None)

        if report.has_blockers:
            raise CommandError(
                "Dry-run found blocking inconsistencies. No images were imported."
            )

        if not options["commit"]:
            self.stdout.write("")
            self.stdout.write("Dry-run only. No database or media changes were made.")
            self.stdout.write("Pass --commit to import the reported images.")
            return

        result = import_gallery_backup_matches(
            report.matches,
            limit=options.get("limit"),
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Local import completed."))
        self.stdout.write(f"Attempted products: {result.attempted_products}")
        self.stdout.write(f"Imported products: {result.imported_products}")
        self.stdout.write(f"Imported images: {result.imported_images}")
        self.stdout.write(f"Skipped during import: {result.skipped_products}")
        self.stdout.write(f"Errors: {len(result.errors)}")
        for error in result.errors[:20]:
            self.stdout.write(self.style.ERROR(f"  {error}"))

        if options["report_path"]:
            self._write_report(options["report_path"], report, result=result)
        if result.errors:
            raise CommandError("Some local Approved-image imports failed.")

    def _assert_local_environment(self):
        if connection.vendor != "sqlite":
            raise CommandError(
                "Safety stop: this command only runs against the local SQLite database."
            )

        expected_database = (Path(settings.BASE_DIR) / "db.sqlite3").resolve()
        configured_database = Path(connection.settings_dict["NAME"]).resolve()
        if configured_database != expected_database:
            raise CommandError(
                "Safety stop: configured SQLite database is not the project-local "
                f"database ({expected_database})."
            )

        if bool(getattr(settings, "USE_CLOUDINARY_MEDIA", False)):
            raise CommandError(
                "Safety stop: Cloudinary media is enabled; local filesystem media "
                "is required."
            )

    def _print_report(self, report, sample_size):
        self.stdout.write(self.style.SUCCESS("Approved gallery backup dry-run completed."))
        self.stdout.write("")
        self.stdout.write(f"Backup schema: {report.schema_version}")
        self.stdout.write(f"Approved cards: {report.approved_count}")
        self.stdout.write(f"Approved retained images: {report.approved_image_count}")
        self.stdout.write(f"Ready products: {report.ready_product_count}")
        self.stdout.write(f"Ready images: {report.ready_image_count}")
        self.stdout.write(
            f"Existing-image products skipped: {len(report.existing_image_skus)}"
        )
        self.stdout.write(f"Missing products: {len(report.missing_product_skus)}")
        self.stdout.write(f"Missing HTML cards: {len(report.missing_html_skus)}")
        self.stdout.write(f"Approved cards without images: {len(report.no_image_skus)}")
        self.stdout.write(f"Missing local files: {len(report.missing_file_entries)}")
        self.stdout.write(f"Invalid local paths: {len(report.invalid_path_entries)}")
        self.stdout.write(f"Invalid image files: {len(report.invalid_image_entries)}")
        self.stdout.write(
            f"Ignored remote source URLs: {len(report.ignored_remote_entries)}"
        )
        self.stdout.write(
            f"Inconsistent Main selections: {len(report.inconsistent_main_skus)}"
        )

        if sample_size and report.matches:
            self.stdout.write("")
            self.stdout.write("Ready sample:")
            for match in report.matches[:sample_size]:
                main = next(
                    (image.path.name for image in match.images if image.is_main),
                    match.images[0].path.name,
                )
                self.stdout.write(
                    f"  {match.product.sku} | {len(match.images)} images | primary {main}"
                )

        self._print_entries("Missing products", report.missing_product_skus)
        self._print_entries("Missing HTML cards", report.missing_html_skus)
        self._print_entries("Cards without images", report.no_image_skus)
        self._print_entries("Missing files", report.missing_file_entries)
        self._print_entries("Invalid paths", report.invalid_path_entries)
        self._print_entries("Invalid images", report.invalid_image_entries)
        self._print_entries(
            "Inconsistent Main selections", report.inconsistent_main_skus
        )

    def _print_entries(self, label, entries):
        if not entries:
            return
        self.stdout.write("")
        self.stdout.write(self.style.ERROR(f"{label}:"))
        for entry in entries[:20]:
            self.stdout.write(self.style.ERROR(f"  {entry}"))
        if len(entries) > 20:
            self.stdout.write(self.style.ERROR(f"  +{len(entries) - 20} more"))

    def _write_report(self, path, report, result):
        payload = {
            "mode": "commit" if result else "dry-run",
            "summary": {
                "schema_version": report.schema_version,
                "approved_cards": report.approved_count,
                "approved_retained_images": report.approved_image_count,
                "ready_products": report.ready_product_count,
                "ready_images": report.ready_image_count,
                "existing_image_skus": list(report.existing_image_skus),
                "missing_product_skus": list(report.missing_product_skus),
                "missing_html_skus": list(report.missing_html_skus),
                "no_image_skus": list(report.no_image_skus),
                "missing_file_entries": list(report.missing_file_entries),
                "invalid_path_entries": list(report.invalid_path_entries),
                "invalid_image_entries": list(report.invalid_image_entries),
                "ignored_remote_entries": list(report.ignored_remote_entries),
                "inconsistent_main_skus": list(report.inconsistent_main_skus),
            },
            "ready": [
                {
                    "sku": match.product.sku,
                    "product_id": match.product.id,
                    "images": [
                        {
                            "path": str(image.path),
                            "reference": image.reference,
                            "is_primary": index == 0,
                        }
                        for index, image in enumerate(match.images)
                    ],
                }
                for match in report.matches
            ],
            "import_result": (
                {
                    "attempted_products": result.attempted_products,
                    "imported_products": result.imported_products,
                    "imported_images": result.imported_images,
                    "skipped_products": result.skipped_products,
                    "errors": list(result.errors),
                }
                if result
                else None
            ),
        }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.stdout.write(f"Report written: {target}")
