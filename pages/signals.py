from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from common.cache_utils import (
    CACHE_GROUP_PAGES_BLOG_LIST,
    CACHE_GROUP_PAGES_CONTENT,
    CACHE_GROUP_PAGES_FOOTER,
    CACHE_GROUP_PAGES_MENU,
    CACHE_GROUP_PAGES_SITE_SETTINGS,
    invalidate_groups,
)

from .models import BlogPost, Component, Content, ContentItem, FooterSettings, Page, SiteSettings


def _is_blog_content_item(instance):
    content_name = (getattr(getattr(instance, "content", None), "name", "") or "").lower()
    return content_name == "bloglist"


@receiver([post_save, post_delete], sender=Page)
def invalidate_page_caches(**kwargs):
    invalidate_groups(
        CACHE_GROUP_PAGES_MENU,
        CACHE_GROUP_PAGES_FOOTER,
        CACHE_GROUP_PAGES_CONTENT,
    )


@receiver([post_save, post_delete], sender=FooterSettings)
def invalidate_footer_cache(**kwargs):
    invalidate_groups(CACHE_GROUP_PAGES_FOOTER)


@receiver([post_save, post_delete], sender=SiteSettings)
def invalidate_site_settings_cache(**kwargs):
    invalidate_groups(CACHE_GROUP_PAGES_SITE_SETTINGS)


@receiver([post_save, post_delete], sender=Component)
@receiver([post_save, post_delete], sender=Content)
def invalidate_page_content_cache(**kwargs):
    invalidate_groups(CACHE_GROUP_PAGES_CONTENT)


@receiver([post_save, post_delete], sender=ContentItem)
def invalidate_content_item_caches(sender, instance, **kwargs):
    groups = [CACHE_GROUP_PAGES_CONTENT]
    if _is_blog_content_item(instance):
        groups.append(CACHE_GROUP_PAGES_BLOG_LIST)

    invalidate_groups(*groups)


@receiver([post_save, post_delete], sender=BlogPost)
def invalidate_blog_caches(**kwargs):
    invalidate_groups(
        CACHE_GROUP_PAGES_CONTENT,
        CACHE_GROUP_PAGES_BLOG_LIST,
    )
