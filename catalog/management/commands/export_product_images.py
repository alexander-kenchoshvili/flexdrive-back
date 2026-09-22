import base64
import gzip
import json
from pathlib import Path
from textwrap import fill

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from catalog.product_image_transfer import export_snapshot


class Command(BaseCommand):
    help = "Export product image references by SKU from shared Cloudinary. No credentials or image binaries."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True, help="Output file, or - for stdout.")
        parser.add_argument("--encoded", action="store_true", help="Compact gzip/base64 for console copy/paste.")

    def handle(self, *args, **options):
        try:
            snapshot = export_snapshot()
            payload = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False)
            if options["encoded"]:
                payload = fill(base64.b64encode(gzip.compress(payload.encode("utf-8"))).decode("ascii"), width=120)
            if options["output"] == "-":
                self.stdout.write(payload)
            else:
                # Never overwrite an existing export silently.
                with Path(options["output"]).open("x", encoding="utf-8") as stream:
                    stream.write(payload + "\n")
            self.stderr.write(
                f"Exported {len(snapshot['products'])} products / "
                f"{sum(len(rows) for rows in snapshot['products'].values())} images."
            )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
