import base64
import gzip
import json
from pathlib import Path
import sys

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from catalog.product_image_transfer import import_snapshot


class Command(BaseCommand):
    help = "Import Cloudinary product image references by SKU into empty galleries. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="Snapshot file, or - for stdin.")
        parser.add_argument("--encoded", action="store_true", help="Read gzip/base64 console export.")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--skip-missing", action="store_true", help="Explicitly skip source SKUs absent in destination.")

    def handle(self, *args, **options):
        try:
            payload = sys.stdin.read() if options["input"] == "-" else Path(options["input"]).read_text(encoding="utf-8")
            if options["encoded"]:
                payload = gzip.decompress(base64.b64decode("".join(payload.split()), validate=True)).decode("utf-8")
            result = import_snapshot(json.loads(payload), commit=options["commit"], skip_missing=options["skip_missing"])
        except (ValueError, OSError, EOFError, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=True))
        self.stdout.write("Image references imported." if options["commit"] else "Dry-run only. No changes made.")
