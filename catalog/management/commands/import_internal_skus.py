import json
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from catalog.internal_skus import import_sku_pairs, read_sku_pairs


class Command(BaseCommand):
    help = "Assign FlexDrive SKUs from paired XLSX columns. Dry-run by default; prices are never imported."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        try:
            pairs = read_sku_pairs(options["input"])
            result = import_sku_pairs(pairs, commit=options["commit"])
        except (ValueError, OSError, BadZipFile, ParseError, KeyError, IndexError,
                ValidationError, IntegrityError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
        self.stdout.write("FlexDrive SKUs imported." if options["commit"] else "Dry-run only. No changes made.")
