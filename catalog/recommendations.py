"""Stable, mixed merchandising order for browsing (never a search filter)."""

from django.db.models import Case, CharField, F, IntegerField, Q, Value, When, Window
from django.db.models.functions import Lower, MD5, RowNumber, Trim

from .models import CUSTOMER_STOCK_RESERVE_QTY


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


def recommended_products(queryset):
    """Round-robin part families within availability/priority tiers before paging.

    The caller supplies one row per product, with all requested filters applied.
    SKU hashes are stable between requests; there is no random() or mutable seed.
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
        merch_shuffle=MD5("sku"),
    ).annotate(
        merch_tier=Case(
            When(merch_family="small", then=Value(2)),
            When(merch_family="other", then=Value(1)),
            default=Value(0), output_field=IntegerField(),
        ),
    ).annotate(
        merch_round=Window(
            expression=RowNumber(),
            partition_by=[F("merch_stock"), F("merch_family")],
            order_by=[F("is_featured").desc(), F("merch_shuffle").asc(), F("pk").asc()],
        ),
    )
    return queryset.order_by("-merch_stock", "merch_tier", "merch_round", "merch_shuffle", "pk")
