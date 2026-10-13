"""Automatic product titles derived from current catalog data, never persisted."""
import re
import unicodedata


_SIDE_MARKER = re.compile(r"\(\s*(LH|RH)\s*\)", re.IGNORECASE)
_SIDE_LABELS = {"left": "მარცხენა", "right": "მარჯვენა", "both": "ორივე", "center": "ცენტრი"}
_GEORGIAN_LETTERS = {
    "a": "ა", "b": "ბ", "c": "ც", "d": "დ", "e": "ე", "f": "ფ",
    "g": "გ", "h": "ჰ", "i": "ი", "j": "ჯ", "k": "[კქ]", "l": "ლ",
    "m": "მ", "n": "ნ", "o": "ო", "p": "პ", "q": "ქ", "r": "რ",
    "s": "ს", "t": "ტ", "u": "უ", "v": "ვ", "w": "[წჭ]", "x": "ხ",
    "y": "ყ", "z": "ზ",
}
_GEORGIAN_PAIRS = {"ch": "ჩ", "dz": "ძ", "gh": "ღ", "kh": "ხ", "sh": "შ", "ts": "ც", "zh": "ჟ"}
_MAKE_ALIASES = {
    "bmw": ("ბმვ",), "mercedes": ("მერსედეს", "მერსედესი"),
    "mitsubishi": ("მიცუბიში",), "toyota": ("ტოიოტა",),
    "volkswagen": ("ფოლკსვაგენი", "ფოლკსვაგენ"),
}


def _text(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _contains_label(text, label):
    label = _text(label).casefold()
    if not label:
        return True
    tokens = re.findall(r"[^\W_]+", label)
    if not tokens:
        return False
    # Permit punctuation in model codes, e.g. CX-5 vs CX5, but not X5 vs X50.
    literal = r"[\W_]*".join(r"[\W_]*".join(re.escape(c) for c in token) for token in tokens)
    patterns = [literal, *(re.escape(alias) for alias in _MAKE_ALIASES.get(label, ()))]
    if re.fullmatch(r"[a-z]{3,}(?:\s+[a-z]+)*", label):
        georgian = []
        index = 0
        while index < len(label):
            pair = label[index:index + 2]
            if pair in _GEORGIAN_PAIRS:
                georgian.append(_GEORGIAN_PAIRS[pair])
                index += 2
            else:
                georgian.append(_GEORGIAN_LETTERS.get(label[index], r"[\W_]+"))
                index += 1
        patterns.append("".join(georgian) + r"(?:ი|ის|ს)?")
    return any(re.search(rf"(?<!\w)(?:{pattern})(?!\w)", text, re.IGNORECASE) for pattern in patterns)


def active_seo_fitment_queryset():
    from django.db.models import Q
    from .models import ProductFitment

    return ProductFitment.objects.filter(
        vehicle_model__is_active=True,
        vehicle_model__make__is_active=True,
    ).filter(Q(engine__isnull=True) | Q(engine__is_active=True)).select_related(
        "vehicle_model__make", "engine",
    )


def _fitments(product):
    if not product.pk:
        return []
    prefetched = getattr(product, "_prefetched_objects_cache", {}).get("fitments")
    if prefetched is None:
        return list(active_seo_fitment_queryset().filter(product_id=product.pk))
    return [fitment for fitment in prefetched if (
        fitment.vehicle_model.is_active and fitment.vehicle_model.make.is_active
        and (fitment.engine_id is None or fitment.engine.is_active)
    )]


def automatic_product_seo_title(product):
    name = _SIDE_MARKER.sub(
        lambda match: "მარცხენა" if match[1].upper() == "LH" else "მარჯვენა",
        _text(product.name),
    )
    name = re.sub(
        r"\b(LH|RH)\b",
        lambda match: "მარცხენა" if match[1].upper() == "LH" else "მარჯვენა",
        name, flags=re.IGNORECASE,
    )
    side_label = _SIDE_LABELS.get(product.side)
    has_side = any(_contains_label(name, side) for side in _SIDE_LABELS.values()) or re.search(
        r"\b(left|right|both|center)\b", name, re.IGNORECASE,
    )
    if side_label and not has_side:
        name = f"{name} {side_label}".strip()

    fitments = _fitments(product)
    if not fitments or product.is_universal_fitment:
        return _with_manufacturer(name, product)

    # A title uses one real range; never merge disconnected ranges into a claim
    # that the part fits the intervening years. Prefer a model already in the name.
    fitment = min(fitments, key=lambda item: (
        not _contains_label(name, item.vehicle_model.name),
        item.vehicle_model.make.name.casefold(), item.vehicle_model.name.casefold(),
        item.year_from, item.year_to, item.pk or 0,
    ))
    prefix = []
    for label in (fitment.vehicle_model.make.name, fitment.vehicle_model.name):
        if not _contains_label(name, label):
            prefix.append(label)
    years = str(fitment.year_from) if fitment.year_from == fitment.year_to else f"{fitment.year_from}–{fitment.year_to}"
    if not _contains_label(name, years):
        prefix.append(years)
    title = f"{' '.join(prefix)} — {name}" if prefix else name
    return _with_manufacturer(title, product)


def _with_manufacturer(title, product):
    brand = getattr(product, "brand", None)
    label = _text(brand.name) if brand else ""
    return f"{title} — {label}" if label and not _contains_label(title, label) else title


def product_seo_title(product):
    return str(product.seo_title or "").strip() or automatic_product_seo_title(product)


def is_legacy_imported_title(product):
    """Only the exact old importer formula is eligible for one-time conversion."""
    if product.supplier_source != "cross_motors" or product.preserve_manual_fitment_content:
        return False
    name = str(product.name or "").strip()
    clean_name = re.sub(r"\s+", " ", _SIDE_MARKER.sub("", name)).strip()
    return product.seo_title == f"{clean_name or name} | FlexDrive"
