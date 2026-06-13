import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.suo_lun_image_import import (
    DEFAULT_TIMEOUT,
    import_review_approved_suo_lun_images,
    load_review_approved_suo_lun_image_matches,
)


class Command(BaseCommand):
    help = (
        "Import manually approved Suo Lun review images from a review decisions "
        "export and review-data file. Defaults to dry-run; writes ProductImage "
        "rows only with --commit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--decisions-path",
            required=True,
            help="Path to the review decisions JSON exported from the review HTML.",
        )
        parser.add_argument(
            "--review-data-path",
            required=True,
            help="Path to the review data JS or JSON file used by the review HTML.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Download and attach approved review images.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum approved products to process.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=DEFAULT_TIMEOUT,
            help=f"HTTP timeout in seconds for image requests (default: {DEFAULT_TIMEOUT}).",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=12,
            help="Number of sample rows to print (default: 12).",
        )
        parser.add_argument(
            "--report-path",
            help="Optional path for a JSON dry-run/import report.",
        )
        parser.add_argument(
            "--include-existing-images",
            action="store_true",
            help=(
                "Include products that already have images in dry-run output. "
                "Commit mode still never overwrites existing images."
            ),
        )

    def handle(self, *args, **options):
        if options["timeout"] <= 0:
            raise CommandError("--timeout must be positive.")
        if options.get("limit") is not None and options["limit"] <= 0:
            raise CommandError("--limit must be positive when provided.")

        decisions_path = Path(options["decisions_path"])
        review_data_path = Path(options["review_data_path"])
        if not decisions_path.exists():
            raise CommandError(f"Decisions file not found: {decisions_path}")
        if not review_data_path.exists():
            raise CommandError(f"Review data file not found: {review_data_path}")

        try:
            report = load_review_approved_suo_lun_image_matches(
                decisions_path,
                review_data_path,
                skip_existing=not options["include_existing_images"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        result = None
        if options["commit"]:
            result = import_review_approved_suo_lun_images(
                report.matches,
                timeout=options["timeout"],
                limit=options.get("limit"),
            )

        self._print_report(
            report=report,
            result=result,
            committed=options["commit"],
            sample_size=options["sample_size"],
        )

        if options["report_path"]:
            self._write_report_file(
                options["report_path"],
                report=report,
                result=result,
                committed=options["commit"],
            )

        if not options["commit"]:
            self._write("")
            self._write("Dry-run only. No database changes were made.")
            self._write("Pass --commit to attach approved review images.")

        if result and result.errors:
            raise CommandError("Some review image imports failed. See report output.")

    def _print_report(self, *, report, result, committed, sample_size):
        mode = "commit" if committed else "dry-run"
        self._write(f"Suo Lun review image {mode} completed.", style_func=self.style.SUCCESS)
        self._write("")
        self._write(f"Approved decisions: {report.approved_decision_count}")
        self._write(f"Approved matches: {len(report.matches)}")
        self._write(f"Missing product SKUs: {len(report.missing_product_skus)}")
        self._write(f"Missing review-data SKUs: {len(report.missing_review_data_skus)}")
        self._write(f"Missing image URLs: {len(report.missing_image_url_skus)}")
        self._write(f"Existing image skipped: {len(report.existing_image_skus)}")

        if result:
            self._write("")
            self._write("Import result:")
            self._write(f"  Attempted: {result.attempted}")
            self._write(f"  Imported products: {result.imported}")
            self._write(f"  Skipped during import: {result.skipped}")
            self._write(f"  Errors: {len(result.errors)}")
            for error in result.errors[:20]:
                self._write(f"    {error}", style_func=self.style.ERROR)
            if len(result.errors) > 20:
                self._write(f"    +{len(result.errors) - 20} more errors")

        if sample_size > 0 and report.matches:
            self._write("")
            self._write("Approved sample:")
            for match in report.matches[:sample_size]:
                candidate = match.candidate
                self._write(
                    "  "
                    f"{match.product.sku} | {match.product.name} | "
                    f"{candidate.name} | {candidate.source_vehicle_label}"
                )

    def _write_report_file(self, path, *, report, result, committed):
        payload = {
            "mode": "commit" if committed else "dry-run",
            "summary": {
                "approved_decisions": report.approved_decision_count,
                "approved_matches": len(report.matches),
                "missing_product_skus": list(report.missing_product_skus),
                "missing_review_data_skus": list(report.missing_review_data_skus),
                "missing_image_url_skus": list(report.missing_image_url_skus),
                "existing_image_skus": list(report.existing_image_skus),
            },
            "import_result": (
                {
                    "attempted": result.attempted,
                    "imported": result.imported,
                    "skipped": result.skipped,
                    "errors": list(result.errors),
                }
                if result
                else None
            ),
            "matches": [self._serialize_match(match) for match in report.matches],
        }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write("")
        self._write(f"Report written: {target}")

    def _serialize_match(self, match):
        candidate = match.candidate
        return {
            "sku": match.product.sku,
            "product_id": match.product.id,
            "product_name": match.product.name,
            "manufacturer_part_number": match.product.manufacturer_part_number,
            "candidate": {
                "source_url": candidate.source_url,
                "image_url": candidate.image_url,
                "name": candidate.name,
                "manufacturer": candidate.manufacturer,
                "source_page_url": candidate.source_page_url,
                "source_vehicle_label": candidate.source_vehicle_label,
            },
        }

    def _write(self, message="", *, style_func=None):
        safe_message = _safe_console_text(str(message), self.stdout)
        if style_func:
            safe_message = style_func(safe_message)
        self.stdout.write(safe_message)


def _safe_console_text(message, output_wrapper):
    stream = getattr(output_wrapper, "_out", None)
    encoding = getattr(stream, "encoding", None) or getattr(output_wrapper, "encoding", None)
    if not encoding:
        return message
    return message.encode(encoding, errors="replace").decode(encoding)
