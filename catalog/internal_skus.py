"""Read SKU pairs without importing workbook prices or executing formulas."""

import posixpath
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError

from common.cache_utils import CACHE_GROUP_CATALOG_CATEGORIES, invalidate_groups
from .models import Product, SkuSequence


def category_sequence(category):
    """Resolve the main category's group; reject cyclic category trees."""
    seen = set()
    while category is not None:
        if category.pk in seen:
            raise ValidationError("კატეგორიების იერარქიაში წრიული კავშირია.")
        seen.add(category.pk)
        if category.parent_id is None:
            return category.sku_sequence_id
        category = category.parent
    return None


def _highest_number(code):
    numbers = [0]
    for value in Product.objects.filter(internal_sku__startswith=f"FD-{code}-").values_list("internal_sku", flat=True):
        match = re.fullmatch(r"FD-\d{2}-(\d+)", value)
        if match:
            numbers.append(int(match[1]))
    return max(numbers)


@transaction.atomic
def assign_admin_sku(product):
    """Called only by the admin save path, never supplier importers."""
    if product.pk:
        saved = Product.objects.select_for_update().get(pk=product.pk)
        if saved.internal_sku:
            product.internal_sku = saved.internal_sku
            return product.internal_sku
        product.internal_sku = None
    elif product.internal_sku:
        return product.internal_sku
    code = category_sequence(product.category)
    if not code:
        return None
    # UPDATE takes a write lock on SQLite as well as a row lock on PostgreSQL.
    # Its lock lasts through the product write/outer admin transaction.
    SkuSequence.objects.filter(pk=code).update(last_number=F("last_number") + 1)
    sequence = SkuSequence.objects.get(pk=code)
    number = max(sequence.last_number, _highest_number(code) + 1)
    sequence.last_number = number
    sequence.save(update_fields=["last_number"])
    product.internal_sku = f"FD-{code}-{number:04d}"
    if product.pk:
        Product.objects.filter(pk=product.pk, internal_sku__isnull=True).update(internal_sku=product.internal_sku)
        Product.objects.filter(pk=product.pk, internal_sku="").update(internal_sku=product.internal_sku)
    return product.internal_sku


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def read_sku_pairs(path):
    pairs = {}
    internal_codes = {}
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [
                "".join(text.text or "" for text in node.findall(".//s:t", NS))
                for node in ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ]
        relationships = {
            node.attrib["Id"]: node.attrib["Target"]
            for node in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        sheets = ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", NS)
        for sheet in sheets:
            target = relationships[sheet.attrib[f"{{{REL_NS}}}id"]]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            rows = ET.fromstring(archive.read(member)).findall("s:sheetData/s:row", NS)
            columns = None
            for row in rows:
                cells = {re.sub(r"\d", "", cell.attrib["r"]): cell for cell in row}
                values = {col: _cell_text(cell, shared) for col, cell in cells.items()}
                if columns is None:
                    if "SKU / კოდი" in values.values() and "ჩვენი კოდი" in values.values():
                        columns = tuple(
                            next(col for col, value in values.items() if value == header)
                            for header in ("SKU / კოდი", "ჩვენი კოდი")
                        )
                    continue
                supplier, internal = (values.get(col, "") for col in columns)
                if not supplier and not internal:
                    continue
                location = f"{sheet.attrib['name']}!{row.attrib['r']}"
                for col, value in zip(columns, (supplier, internal)):
                    cell = cells.get(col)
                    if (
                        not value or len(value) > 64 or cell is None
                        or cell.find("s:f", NS) is not None
                        or cell.attrib.get("t") not in {"s", "inlineStr"}
                    ):
                        raise ValueError(f"{location}: SKU must be literal text, non-empty and at most 64 characters.")
                if supplier in pairs:
                    raise ValueError(f"{location}: duplicate supplier SKU {supplier}.")
                if internal.casefold() in internal_codes:
                    raise ValueError(f"{location}: duplicate FlexDrive SKU {internal}.")
                pairs[supplier] = internal
                internal_codes[internal.casefold()] = supplier
            if columns is None:
                raise ValueError(f"{sheet.attrib['name']}: missing SKU column headers.")
    if not pairs:
        raise ValueError("Workbook has no SKU pairs.")
    return pairs


def _cell_text(cell, shared):
    value = cell.findtext("s:v", default="", namespaces=NS)
    if cell.attrib.get("t") == "s":
        return shared[int(value)].strip()
    if cell.attrib.get("t") == "inlineStr":
        return "".join(text.text or "" for text in cell.findall("s:is//s:t", NS)).strip()
    return value.strip()


@transaction.atomic
def import_sku_pairs(pairs, *, commit=False):
    """Fill previously unassigned codes atomically; never replace existing assignments."""
    if not pairs:
        raise ValueError("No SKU pairs supplied.")
    products = list(Product.objects.select_for_update().order_by("pk"))
    by_sku = {product.sku: product for product in products}
    owners = {}
    for product in products:
        for code in (product.sku, product.internal_sku):
            if code:
                owners.setdefault(code.casefold(), set()).add(product.pk)
    missing = sorted(set(pairs) - set(by_sku))
    if missing:
        raise ValueError("Unknown supplier SKUs; nothing changed: " + ", ".join(missing))
    changes = []
    seen = set()
    field = Product._meta.get_field("internal_sku")
    for supplier, internal in pairs.items():
        product = by_sku[supplier]
        if not isinstance(internal, str) or not internal:
            raise ValueError(f"{supplier}: empty or invalid FlexDrive SKU.")
        field.run_validators(internal)
        key = internal.casefold()
        if key in seen:
            raise ValueError(f"Duplicate FlexDrive SKU: {internal}.")
        seen.add(key)
        if owners.get(key, set()) - {product.pk}:
            raise ValueError(f"{internal}: code belongs to another product.")
        if product.internal_sku and product.internal_sku != internal:
            raise ValueError(f"{supplier}: already has a different FlexDrive SKU; nothing changed.")
        if product.internal_sku != internal:
            product.internal_sku = internal
            changes.append(product)
    if commit and changes:
        # Only this field is written: no pricing hooks, stock, slugs, or timestamps.
        Product.objects.bulk_update(changes, ["internal_sku"], batch_size=200)
        for sequence in SkuSequence.objects.select_for_update().order_by("code"):
            highest = _highest_number(sequence.code)
            if highest > sequence.last_number:
                sequence.last_number = highest
                sequence.save(update_fields=["last_number"])
        transaction.on_commit(lambda: invalidate_groups(CACHE_GROUP_CATALOG_CATEGORIES))
    return {
        "matched": len(pairs),
        "updated" if commit else "would_update": len(changes),
        "unchanged": len(pairs) - len(changes),
    }
