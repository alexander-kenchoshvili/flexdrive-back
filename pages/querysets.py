from django.db.models import Prefetch

from .models import Component, ContentItem, Page


def page_serialization_queryset():
    content_items = (
        ContentItem.objects
        .select_related("blog_post", "catalog_category")
        .order_by("position", "id")
    )
    enabled_components = (
        Component.objects
        .filter(enabled=True)
        .select_related("component_type", "content")
        .prefetch_related(
            Prefetch(
                "content__items",
                queryset=content_items,
                to_attr="prefetched_items",
            )
        )
        .order_by("position", "id")
    )

    return Page.objects.prefetch_related(
        Prefetch(
            "components",
            queryset=enabled_components,
            to_attr="enabled_components",
        )
    )
