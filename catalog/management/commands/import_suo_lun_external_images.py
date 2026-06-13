import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.suo_lun_image_import import (
    DEFAULT_TIMEOUT,
    build_external_suo_lun_image_report,
    get_suo_lun_products,
    import_external_suo_lun_images,
)


class Command(BaseCommand):
    help = (
        "Import external image candidates for Suo Lun products from a prepared "
        "JSON report. Defaults to dry-run; writes ProductImage rows only with --commit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--candidate-path",
            required=True,
            help="Path to the external image candidate JSON report.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Download and attach auto_import candidate images.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum auto-import products to process.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=DEFAULT_TIMEOUT,
            help=f"HTTP timeout in seconds for image requests (default: {DEFAULT_TIMEOUT}).",
        )
        parser.add_argument(
            "--max-images-per-product",
            type=int,
            default=5,
            help="Maximum images to attach per product (default: 5).",
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
                "Include products that already have images in matching output. "
                "Commit mode still never overwrites existing images."
            ),
        )

    def handle(self, *args, **options):
        if options["timeout"] <= 0:
            raise CommandError("--timeout must be positive.")
        if options["max_images_per_product"] <= 0:
            raise CommandError("--max-images-per-product must be positive.")
        if options.get("limit") is not None and options["limit"] <= 0:
            raise CommandError("--limit must be positive when provided.")

        candidate_path = Path(options["candidate_path"])
        if not candidate_path.exists():
            raise CommandError(f"Candidate report not found: {candidate_path}")

        try:
            products = tuple(get_suo_lun_products())
            report = build_external_suo_lun_image_report(
                candidate_path,
                products,
                skip_existing=not options["include_existing_images"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        result = None
        if options["commit"]:
            result = import_external_suo_lun_images(
                report.by_action("auto_import"),
                timeout=options["timeout"],
                limit=options.get("limit"),
                max_images_per_product=options["max_images_per_product"],
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
            self._write("Pass --commit to attach high-confidence external images.")

        if result and result.errors:
            raise CommandError("Some external image imports failed. See report output.")

    def _print_report(self, *, report, result, committed, sample_size):
        mode = "commit" if committed else "dry-run"
        self._write(f"Suo Lun external image {mode} completed.", style_func=self.style.SUCCESS)
        self._write("")
        self._write(f"External candidates loaded: {report.candidate_count}")
        self._write(f"Auto import: {report.auto_import_count}")
        self._write(f"Review: {report.review_count}")
        self._write(f"Missing product SKUs: {len(report.missing_product_skus)}")
        self._write(f"Existing image skipped: {len(report.existing_image_skus)}")
        self._write(f"Ignored rows: {report.ignored_count}")

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

        self._print_samples(report.by_action("auto_import"), "Auto-import sample", sample_size)
        self._print_samples(report.by_action("review"), "Review sample", sample_size)

    def _print_samples(self, matches, label, sample_size):
        if sample_size <= 0 or not matches:
            return

        self._write("")
        self._write(f"{label}:")
        for match in matches[:sample_size]:
            candidate = match.candidate
            self._write(
                "  "
                f"{match.product.sku} | {match.product.name} | "
                f"{candidate.source} | {candidate.source_title} | "
                f"{len(candidate.image_urls)} images | {match.reason}"
            )

    def _write_report_file(self, path, *, report, result, committed):
        payload = {
            "mode": "commit" if committed else "dry-run",
            "summary": {
                "candidate_count": report.candidate_count,
                "auto_import": report.auto_import_count,
                "review": report.review_count,
                "missing_product_skus": list(report.missing_product_skus),
                "existing_image_skus": list(report.existing_image_skus),
                "ignored_count": report.ignored_count,
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
            "action": match.action,
            "confidence": match.confidence,
            "reason": match.reason,
            "candidate": {
                "source": candidate.source,
                "source_url": candidate.source_url,
                "source_title": candidate.source_title,
                "image_urls": list(candidate.image_urls),
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
