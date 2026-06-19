import hashlib
import ipaddress
import json
from dataclasses import asdict, dataclass

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException

from pages.models import Page
from pages.querysets import page_serialization_queryset


class TermsDocumentUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "წესებისა და პირობების მიმდინარე ვერსია დროებით მიუწვდომელია. "
        "გთხოვთ, სცადოთ მოგვიანებით."
    )
    default_code = "terms_document_unavailable"


@dataclass(frozen=True)
class TermsAcceptanceSnapshot:
    accepted_at: object
    version: str
    content_hash: str
    content_snapshot: dict
    url: str
    ip_address: str | None
    user_agent: str

    def to_order_fields(self):
        data = asdict(self)
        return {
            "terms_accepted_at": data["accepted_at"],
            "terms_version": data["version"],
            "terms_content_hash": data["content_hash"],
            "terms_content_snapshot": data["content_snapshot"],
            "terms_url": data["url"],
            "terms_ip_address": data["ip_address"],
            "terms_user_agent": data["user_agent"],
        }


def build_terms_acceptance_snapshot(*, request, accepted_at):
    content_snapshot = _build_terms_content_snapshot()
    canonical_content = json.dumps(
        content_snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    content_hash = hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()
    configured_version = str(
        getattr(settings, "TERMS_DOCUMENT_VERSION", "")
    ).strip()

    return TermsAcceptanceSnapshot(
        accepted_at=accepted_at,
        version=configured_version or f"sha256:{content_hash[:16]}",
        content_hash=content_hash,
        content_snapshot=content_snapshot,
        url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/terms",
        ip_address=_get_client_ip(request),
        user_agent=str(request.META.get("HTTP_USER_AGENT", "")).strip()[:1000],
    )


def _build_terms_content_snapshot():
    page = (
        page_serialization_queryset()
        .filter(slug="terms")
        .first()
    )
    if page is None:
        raise TermsDocumentUnavailable()

    components = []
    for component in page.enabled_components:
        content = component.content
        items = []
        if content is not None:
            prefetched_items = getattr(content, "prefetched_items", None)
            content_items = prefetched_items if prefetched_items is not None else content.items.all()
            for item in sorted(
                content_items,
                key=lambda item: (item.position, item.pk),
            ):
                items.append(
                    {
                        "position": item.position,
                        "title": str(item.title or ""),
                        "description": str(item.description or ""),
                        "editor": str(item.editor or ""),
                        "slug": str(item.slug or ""),
                        "content_type": str(item.content_type or ""),
                    }
                )

        components.append(
            {
                "position": component.position,
                "component_type": str(component.component_type.name),
                "title": str(component.title or ""),
                "subtitle": str(component.subtitle or ""),
                "button_text": str(component.button_text or ""),
                "content_name": str(content.name) if content is not None else "",
                "items": items,
            }
        )

    if not components:
        raise TermsDocumentUnavailable()

    return {
        "page": {
            "slug": page.slug,
            "name": page.name,
        },
        "components": components,
    }


def _get_client_ip(request):
    forwarded_for = [
        value.strip()
        for value in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if value.strip()
    ]
    num_proxies = max(
        int(settings.REST_FRAMEWORK.get("NUM_PROXIES", 0) or 0),
        0,
    )
    if forwarded_for and num_proxies:
        candidate = forwarded_for[-min(num_proxies, len(forwarded_for))]
    else:
        candidate = str(request.META.get("REMOTE_ADDR", "")).strip()

    if not candidate:
        return None

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None
