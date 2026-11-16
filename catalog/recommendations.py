"""Stable, mixed merchandising order for browsing (never a search filter)."""

import re
from collections import defaultdict

from django.db.models import BooleanField, Case, CharField, F, IntegerField, Q, Value, When, Window
from django.db.models.functions import Cast, DenseRank, Lower, MD5, Trim

from .models import CUSTOMER_STOCK_RESERVE_QTY, ProductFitment, ProductSide


# Match whole part nouns, not their Georgian possessive accessory forms:
# "ფარი" is a lamp; "ფარის სამაგრი" is a lamp bracket.
PART_FAMILIES = (
    ("hood", r"^(?:წინა\s+)?კაპოტი(?:\s|$|[(-])"),
    ("lamp", r"^(?:(?:წინა|უკანა|სანისლე|საბარგულის|ლედ)\s+)?(?:ფარი|სტოპი|ტუმანიკი)(?:\s|$|[(-])"),
    ("bumper", r"^(?:(?:წინა|უკანა)\s+)?ბამპერი(?:\s|$|[(-])"),
    ("fender", r"^(?:(?:წინა|უკანა)\s+)?კრილო(?:\s|$|[(-])"),
    ("door", r"^(?:(?:წინა|უკანა|საბარგულის|ბაგაჟის)\s+)?(?:კარი|კარები)(?:\s|$|[(-])"),
    ("mirror", r"^სარკე(?:\s|$|[(-])"),
    ("radiator", r"^(?:(?:წყლის|კონდინციონერის|კონდიციონერის|ძრავის)\s+)?რადიატორი(?:\s|$|[(-])"),
    ("grille", r"^(?:(?:ზედა|ქვედა|წინა)\s+)?ცხაურა(?:\s|$|[(-])"),
    ("reinforcement", r"^(?:(?:წინა|უკანა|ზედა|ქვედა)\s+)*(?:ბალკა|ეკრანი)(?:\s|$|[(-])"),
)
SMALL_PART_PATTERN = r"(?:^|\s)(?:ბოლტი|ბოლტები|კლიპსი|კლიპსები|სამაგრი|სამაგრები|სალასკა|ხუფი|პეტლი|რეზინა|ჩაშკა|საბუქსირე|ემბლემა)(?:\s|$|[(-])"

SIDE_TOKENS = {
    "lh": ProductSide.LEFT, "left": ProductSide.LEFT, "მარცხენა": ProductSide.LEFT,
    "rh": ProductSide.RIGHT, "right": ProductSide.RIGHT, "მარჯვენა": ProductSide.RIGHT,
}
SIDE_PATTERN = re.compile(
    r"(?<!\w)(?:lh|rh|left|right|მარცხენა|მარჯვენა)(?!\w)(?!\s+(?:hand\b|საჭ|რულ))",
    re.IGNORECASE,
)


def _side_neutral_text(text):
    text = SIDE_PATTERN.sub(" ", text.casefold())
    text = re.sub(r"\(\s*\)|\[\s*\]", " ", text)
    return " ".join(text.split()).strip(" -–—,;")


def _paired_groups(queryset):
    """Recognize unambiguous opposites using full fitments, never just a model.

    Read only lightweight metadata in two queries, not product images/details.
    Missing compatibility, conflicting sides and multiple candidates stay solo.
    """
    candidates = {}
    for row in queryset.order_by().values(
        "pk", "name", "side", "placement", "brand_id", "category_id",
        "is_universal_fitment", "is_featured", "merch_stock", "merch_family",
    ):
        named_sides = {SIDE_TOKENS[match.group().casefold()] for match in SIDE_PATTERN.finditer(row["name"])}
        if row["side"] not in ("", ProductSide.LEFT, ProductSide.RIGHT) or len(named_sides) > 1:
            continue
        side = row["side"] or next(iter(named_sides), "")
        if not side or (named_sides and side not in named_sides):
            continue
        name = _side_neutral_text(row["name"])
        if name:
            candidates[row["pk"]] = (row, name, side)

    fitments = defaultdict(set)
    if candidates:
        for pk, model, engine, start, end, notes in ProductFitment.objects.filter(
            product_id__in=candidates,
        ).order_by().values_list("product_id", "vehicle_model_id", "engine_id", "year_from", "year_to", "notes"):
            # Fitment notes can describe steering/trim variants, so retain side
            # words here; only the product's side label is interchangeable.
            fitments[pk].add((model, engine, start, end, " ".join(notes.casefold().split())))

    groups = defaultdict(lambda: defaultdict(list))
    for pk, (row, name, side) in candidates.items():
        if not fitments[pk] and not row["is_universal_fitment"]:
            continue
        key = (
            name, row["category_id"], row["brand_id"], row["placement"],
            row["is_universal_fitment"], frozenset(fitments[pk]),
            row["merch_stock"], row["merch_family"],
        )
        groups[key][side].append(row)

    pairs = []
    for sides in groups.values():
        if len(sides[ProductSide.LEFT]) == len(sides[ProductSide.RIGHT]) == 1:
            left, right = sides[ProductSide.LEFT][0], sides[ProductSide.RIGHT][0]
            pairs.append((min(left["pk"], right["pk"]), max(left["pk"], right["pk"]),
                          left["is_featured"] or right["is_featured"]))
    return pairs


def recommended_products(queryset):
    """Round-robin part groups within availability/priority tiers before paging.

    The caller supplies one row per product, with all requested filters applied.
    ID hashes are stable between requests; there is no random() or mutable seed.
    """
    queryset = queryset.annotate(merch_name=Lower(Trim("name"))).annotate(
        merch_stock=Case(
            When(Q(owned_stock_qty__gt=0) | Q(stock_qty__gt=CUSTOMER_STOCK_RESERVE_QTY), then=Value(1)),
            default=Value(0), output_field=IntegerField(),
        ),
        merch_family=Case(
            When(merch_name__regex=SMALL_PART_PATTERN, then=Value("small")),
            *(When(merch_name__regex=pattern, then=Value(family)) for family, pattern in PART_FAMILIES),
            default=Value("other"), output_field=CharField(),
        ),
    ).annotate(
        merch_tier=Case(
            When(merch_family="small", then=Value(2)),
            When(merch_family="other", then=Value(1)),
            default=Value(0), output_field=IntegerField(),
        ),
    )
    pairs = _paired_groups(queryset)
    featured_ids = [pk for first, second, featured in pairs if featured for pk in (first, second)]
    queryset = queryset.annotate(
        merch_group=Case(
            *(When(pk=second, then=Value(first)) for first, second, _ in pairs),
            default=F("pk"), output_field=IntegerField(),
        ),
        merch_featured=Case(
            When(pk__in=featured_ids, then=Value(True)),
            default=F("is_featured"), output_field=BooleanField(),
        ),
    ).annotate(merch_shuffle=MD5(Cast("merch_group", CharField()))).annotate(
        merch_round=Window(
            expression=DenseRank(),
            partition_by=[F("merch_stock"), F("merch_family")],
            order_by=[F("merch_featured").desc(), F("merch_shuffle").asc(), F("merch_group").asc()],
        ),
    )
    return queryset.order_by("-merch_stock", "merch_tier", "merch_round", "merch_shuffle", "merch_group", "pk")
