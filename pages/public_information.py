"""The two legal documents readable before the storefront's public opening.

Return only the matching enabled legal component's text, not general CMS data.
The storefront uses this projection for a small, script-free public document.
"""

from django.db import DatabaseError
from django.http import JsonResponse
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from .models import Component
from .svg_safety import sanitize_editor_html


PUBLIC_LEGAL_PAGES = {
    "privacy-policy": ("PrivacyPolicy", "policy_section"),
    "terms": ("Terms", "terms_section"),
}


@require_http_methods(["GET", "HEAD"])
def public_legal_information(request, slug):
    specification = PUBLIC_LEGAL_PAGES.get(slug)
    if specification is None:
        return JsonResponse({"code": "not_found"}, status=404)
    component_type, item_type = specification
    try:
        components = list(
            Component.objects.filter(
                page__slug=slug, enabled=True, component_type__name=component_type,
            ).select_related("page", "content").order_by("position", "id")
        )
        sections = []
        for component in components:
            if component.content_id is None:
                continue
            for item in component.content.items.filter(content_type=item_type).order_by("position", "id"):
                html = sanitize_editor_html(item.editor) if item.editor else str(format_html("<p>{}</p>", item.description or ""))
                if html.strip():
                    sections.append({"title": item.title or "", "html": html})
        if not components or not sections:
            return JsonResponse({"code": "not_found"}, status=404)
        return JsonResponse({
            "slug": slug,
            "title": components[0].title or components[0].page.name,
            "intro": components[0].subtitle or "",
            "sections": sections,
        })
    except DatabaseError:
        return JsonResponse({"code": "information_unavailable"}, status=503)
