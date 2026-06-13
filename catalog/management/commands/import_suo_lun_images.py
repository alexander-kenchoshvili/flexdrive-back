import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.suo_lun_image_import import (
    DEFAULT_TIMEOUT,
    build_suo_lun_image_report,
    fetch_crossmotors_source_products,
    get_suo_lun_products,
    import_suo_lun_images,
)


class Command(BaseCommand):
    help = (
        "Find and optionally import images for Suo Lun products. Defaults to a "
        "dry-run report; writes ProductImage records only when --commit is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Download matched images and attach them to matching Suo Lun products.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum auto-import matches to process. Useful for first small batches.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=DEFAULT_TIMEOUT,
            help=f"HTTP timeout in seconds for source and image requests (default: {DEFAULT_TIMEOUT}).",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=12,
            help="Number of sample rows to print per action group (default: 12).",
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
        timeout = options["timeout"]
        if timeout <= 0:
            raise CommandError("--timeout must be positive.")

        if options.get("limit") is not None and options["limit"] <= 0:
            raise CommandError("--limit must be positive when provided.")

        try:
            products = tuple(get_suo_lun_products())
            candidates = fetch_crossmotors_source_products(timeout=timeout)
            report = build_suo_lun_image_report(
                products,
                candidates,
                skip_existing=not options["include_existing_images"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        result = None
        if options["commit"]:
            result = import_suo_lun_images(
                report.by_action("auto_import"),
                timeout=timeout,
                limit=options.get("limit"),
            )

        self._print_report(
            products=products,
            candidates=candidates,
            report=report,
            result=result,
            committed=options["commit"],
            sample_size=options["sample_size"],
        )

        if options["report_path"]:
            self._write_report_file(
                options["report_path"],
                products=products,
                candidates=candidates,
                report=report,
                result=result,
                committed=options["commit"],
            )

        if not options["commit"]:
            self._write("")
            self._write("Dry-run only. No database changes were made.")
            self._write("Pass --commit to attach high-confidence images.")

        if result and result.errors:
            raise CommandError("Some image imports failed. See report output for details.")

    def _print_report(self, *, products, candidates, report, result, committed, sample_size):
        mode = "commit" if committed else "dry-run"
        self._write(f"Suo Lun image {mode} completed.", style_func=self.style.SUCCESS)
        self._write("")
        self._write(f"Suo Lun products: {len(products)}")
        self._write(f"CrossMotors SL-China candidates: {len(candidates)}")
        self._write("")
        self._write("Match actions:")
        self._write(f"  Auto import: {report.auto_import_count}")
        self._write(f"  Review: {report.review_count}")
        self._write(f"  Skipped: {report.skipped_count}")
        self._write(f"  No candidate: {report.no_candidate_count}")
        self._write(f"  Existing image skipped: {report.existing_image_count}")

        if result:
            self._write("")
            self._write("Import result:")
            self._write(f"  Attempted: {result.attempted}")
            self._write(f"  Imported: {result.imported}")
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
            if candidate is None:
                continue
            self._write(
                "  "
                f"{match.product.sku} | {match.product.name} | "
                f"{candidate.name} | {candidate.source_vehicle_label} | "
                f"{match.confidence} | {match.reason} | score {match.score:.2f}"
            )

    def _write_report_file(self, path, *, products, candidates, report, result, committed):
        payload = {
            "mode": "commit" if committed else "dry-run",
            "suo_lun_products": len(products),
            "crossmotors_sl_china_candidates": len(candidates),
            "summary": {
                "auto_import": report.auto_import_count,
                "review": report.review_count,
                "skipped": report.skipped_count,
                "no_candidate": report.no_candidate_count,
                "existing_image": report.existing_image_count,
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
            "score": round(match.score, 4),
            "ambiguity_count": match.ambiguity_count,
            "candidate": (
                {
                    "source_url": candidate.source_url,
                    "image_url": candidate.image_url,
                    "name": candidate.name,
                    "manufacturer": candidate.manufacturer,
                    "source_page_url": candidate.source_page_url,
                    "source_vehicle_label": candidate.source_vehicle_label,
                }
                if candidate
                else None
            ),
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
