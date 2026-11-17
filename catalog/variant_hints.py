"""Version mentions are merchandising hints, never proof of part fitment.

Read existing names and matching-fitment notes; do not mutate/import data or
infer that an unlabelled part fits every version. Composite names stay distinct.
"""
import re
from collections import defaultdict

from django.db.models import Case, IntegerField, Value, When


# Longer/composite variants precede their component words. No LED/HID, engine
# displacement, colour or body-style guesses from these text mentions.
VARIANTS = (
    ("m_sport", "M Sport", r"m[\s-]+sport"),
    ("r_line", "R-Line", r"r[\s-]+line"),
    ("st_line", "ST-Line", r"st[\s-]+line"),
    ("ex_v6", "EX-V6", r"ex[\s-]+v6"),
    ("ex_l", "EX-L", r"ex[\s-]+l"),
    ("gli", "GLI", r"gli"),
    ("gti", "GTI", r"gti"),
    ("gte", "GTE", r"gte"),
    ("gtd", "GTD", r"gtd"),
    ("amg", "AMG", r"amg"),
    ("sport", "Sport", r"sport|სპორტი(?:ს)?|სპორტული"),
    ("limited", "Limited", r"limited|ლიმიტედი"),
    ("hybrid", "Hybrid", r"hybrid|ჰიბრიდ(?:ი(?:ს)?|ული|ის)?"),
    ("premium", "Premium", r"premium"),
    ("touring", "Touring", r"touring"),
    ("xle", "XLE", r"xle"),
    ("xse", "XSE", r"xse"),
    ("sel", "SEL", r"sel"),
    ("se", "SE", r"se"),
    ("le", "LE", r"le"),
    ("lx", "LX", r"lx"),
    ("ex", "EX", r"ex"),
)
LABELS = {key: label for key, label, _ in VARIANTS}
PATTERNS = [(key, re.compile(r"(?<!\w)(?:" + pattern + r")(?!\w)", re.I)) for key, _, pattern in VARIANTS]
NEGATIVE_BEFORE = re.compile(r"(?:\bnon|\bnot|\bexcept|\bexcluding|\bwithout|არა|გარდა)\s*[-:(]?\s*$", re.I)
NEGATIVE_AFTER = re.compile(
    r"^\s*(?:[-–]\s*)?(?:(?:ს|ის)\s+)?(?:გარდა|გარეშე|არ\s+(?:ერგება|მიდის|თავსდება)|excluded|not\s+(?:compatible|supported))(?!\w)",
    re.I,
)


def extract_mentions(*texts):
    positive, negative = set(), set()
    for text in texts:
        if not isinstance(text, str):
            continue
        occupied = set()
        for key, pattern in PATTERNS:
            for match in pattern.finditer(text):
                span = set(range(match.start(), match.end()))
                if span & occupied:
                    continue
                occupied.update(span)
                before, after = text[max(0, match.start() - 32):match.start()], text[match.end():match.end() + 32]
                if key == "sport" and re.match(r"\s+utility(?!\w)", after, re.I):
                    continue
                if NEGATIVE_BEFORE.search(before) or NEGATIVE_AFTER.search(after):
                    negative.add(key)
                else:
                    positive.add(key)
    # Conflicting text is not a positive hint.
    return positive - negative, negative


def variant_keys(*texts):
    positive, _ = extract_mentions(*texts)
    return [key for key in LABELS if key in positive][:4]


def parse_variant_query(value):
    if not value:
        return ()
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError("invalid variant")
    keys = tuple(dict.fromkeys(value.split(",")))
    if len(keys) > 4 or any(key not in LABELS and key != "unspecified" for key in keys):
        raise ValueError("invalid variant")
    if "unspecified" in keys and len(keys) != 1:
        raise ValueError("invalid variant")
    return keys


def variant_hint(requested, name, notes=()):
    positive, negative = extract_mentions(name, *notes)
    targets = set(requested) - {"unspecified"}
    mentioned = targets & positive
    # Multiple decoded labels can contain alternatives. If any requested label
    # is explicitly negated, avoid promoting the product as a positive hint.
    if targets & negative:
        mentioned = set()
    return {
        "status": "mentioned" if mentioned else "unverified",
        "labels": [LABELS[key] for key in LABELS if key in mentioned],
    }


def annotate_variant_priority(queryset, requested, matching_fitments):
    """At most two lightweight reads across the filtered result, no N+1.

    No products excluded. Called only for recommended order; exact identifiers,
    price/name/date ordering, availability and pagination retain their semantics.
    """
    if not set(requested) - {"unspecified"}:
        return queryset.annotate(variant_priority=Value(0, output_field=IntegerField()))
    names = dict(queryset.order_by().values_list("pk", "name").distinct())
    notes = defaultdict(list)
    for pk, note in matching_fitments.filter(product_id__in=names).values_list("product_id", "notes"):
        notes[pk].append(note)
    ids = [pk for pk, name in names.items() if variant_hint(requested, name, notes[pk])["status"] == "mentioned"]
    return queryset.annotate(variant_priority=Case(
        When(pk__in=ids, then=Value(1)), default=Value(0), output_field=IntegerField(),
    ))
