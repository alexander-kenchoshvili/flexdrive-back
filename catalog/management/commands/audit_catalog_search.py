"""Read-only, repeatable checks against every public product in local SQLite."""
import json
from collections import defaultdict
from pathlib import Path
import re
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from catalog.models import Product, ProductStatus
from catalog.views import (
    SEARCH_QUERY_MAX_LENGTH, _apply_catalog_search, _build_search_context,
    _georgian_to_latin,
)


def search_cases(product):
    name = product.name
    words = re.findall(r"[^\W_]+(?:[-./][^\W_]+)*", name, re.UNICODE)
    yield "full_name", name
    yield "whitespace", "  " + "   ".join(name.split()) + "  "
    yield "punctuation", " ".join(words)
    yield "word_order", " ".join(reversed(words))
    yield "latin_name", _georgian_to_latin(name)
    if product.internal_sku:
        yield "company_sku", product.internal_sku.lower()
        if re.fullmatch(r"FD-\d{2}-\d+", product.internal_sku):
            yield "company_sku_compact", product.internal_sku.lower().replace("-", "")
    if product.manufacturer_part_number:
        yield "part_number", product.manufacturer_part_number
    for fitment in product.fitments.all():
        vehicle = f"{fitment.vehicle_model.make.name} {fitment.vehicle_model.name}"
        yield "vehicle_name", f"{vehicle} {name}"
        yield "name_vehicle", f"{name} {vehicle}"
        yield "vehicle_year_name", f"{vehicle} {fitment.year_from} {name}"
        yield "name_vehicle_year", f"{name} {vehicle} {fitment.year_from}"
        if fitment.year_to != fitment.year_from:
            yield "vehicle_end_year_name", f"{vehicle} {fitment.year_to} {name}"


class Command(BaseCommand):
    help = "Audit public catalog search without changing data (local SQLite only)."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Write detailed JSON report to this path.")
        parser.add_argument("--limit", type=int, help="Limit products for a quick diagnostic run.")
        parser.add_argument("--fail-on-missing", action="store_true", help="Exit unsuccessfully if any expected product is missing.")

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("This local audit only permits SQLite; remote databases are not queried.")
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit must be a positive integer.")
        started = perf_counter()
        public = Product.objects.filter(status=ProductStatus.PUBLISHED, category__is_active=True)
        products = public.prefetch_related("fitments__vehicle_model__make").order_by("pk")
        if options["limit"]:
            products = products[:options["limit"]]
        products = list(products)
        cases = defaultdict(lambda: defaultdict(dict))
        skipped = defaultdict(int)
        for product in products:
            for kind, raw_query in search_cases(product):
                query = raw_query.strip()
                if not 2 <= len(query) <= SEARCH_QUERY_MAX_LENGTH:
                    skipped[kind] += 1
                    continue
                cases[kind][query][product.pk] = product.name
        summary = {}
        failures = []
        contexts = {}
        matches = {}
        for kind, queries in cases.items():
            checks = 0
            failed = 0
            for query, expected in queries.items():
                if query not in contexts:
                    contexts[query] = _build_search_context(query)
                if query not in matches:
                    matches[query] = set(_apply_catalog_search(public, contexts[query]).values_list("pk", flat=True))
                missing = expected.keys() - matches[query]
                checks += len(expected)
                failed += len(missing)
                if missing:
                    failures.append({
                        "kind": kind, "query": query,
                        "missing": [{"id": pk, "name": expected[pk]} for pk in sorted(missing)],
                        "search_parts": contexts[query]["search_parts"],
                    })
            summary[kind] = {"checks": checks, "failed": failed, "skipped_length": skipped[kind]}
            self.stdout.write(f"{kind}: {checks - failed}/{checks} passed; {failed} failed")
        report = {
            "database": "local SQLite", "products": len(products), "summary": summary,
            "checks": sum(suite["checks"] for suite in summary.values()),
            "failed_checks": sum(suite["failed"] for suite in summary.values()),
            "unique_queries": len(matches), "elapsed_seconds": round(perf_counter() - started, 2),
            "failures": failures,
        }
        if options["output"]:
            path = Path(options["output"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(f"Products: {len(products)}; unique queries: {len(matches)}; seconds: {report['elapsed_seconds']}")
        if options["fail_on_missing"] and failures:
            raise CommandError(f"{report['failed_checks']} expected product matches are missing.")
