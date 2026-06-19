import re
import xml.etree.ElementTree as etree

import bleach
from defusedxml.ElementTree import fromstring


RICH_TEXT_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s",
    "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "hr", "a", "img",
    "figure", "figcaption", "table", "thead", "tbody", "tr",
    "th", "td", "pre", "code", "span",
}
RICH_TEXT_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
    "span": ["class"],
    "code": ["class"],
}

SVG_TAG_ATTRIBUTES = {
    "svg": {
        "xmlns", "viewBox", "width", "height", "fill", "stroke", "role",
        "aria-hidden", "focusable", "preserveAspectRatio",
    },
    "g": {"fill", "stroke", "stroke-width", "transform", "opacity"},
    "path": {
        "d", "fill", "fill-rule", "clip-rule", "stroke", "stroke-width",
        "stroke-linecap", "stroke-linejoin", "opacity", "transform",
    },
    "circle": {"cx", "cy", "r", "fill", "stroke", "stroke-width", "opacity"},
    "ellipse": {"cx", "cy", "rx", "ry", "fill", "stroke", "stroke-width", "opacity"},
    "rect": {
        "x", "y", "width", "height", "rx", "ry", "fill", "stroke",
        "stroke-width", "opacity",
    },
    "line": {
        "x1", "y1", "x2", "y2", "stroke", "stroke-width",
        "stroke-linecap", "opacity",
    },
    "polyline": {
        "points", "fill", "stroke", "stroke-width", "stroke-linecap",
        "stroke-linejoin", "opacity",
    },
    "polygon": {
        "points", "fill", "stroke", "stroke-width", "stroke-linejoin", "opacity",
    },
    "title": set(),
    "desc": set(),
    "defs": set(),
    "linearGradient": {
        "id", "x1", "y1", "x2", "y2", "gradientUnits", "gradientTransform",
    },
    "radialGradient": {
        "id", "cx", "cy", "r", "fx", "fy", "gradientUnits", "gradientTransform",
    },
    "stop": {"offset", "stop-color", "stop-opacity"},
    "clipPath": {"id", "clipPathUnits", "transform"},
    "mask": {
        "id", "x", "y", "width", "height", "maskUnits", "maskContentUnits",
    },
}
LOCAL_URL_PATTERN = re.compile(r"^url\(\s*#[A-Za-z_][\w:.-]*\s*\)$")


def sanitize_editor_html(value: str | None) -> str:
    return bleach.clean(
        str(value or "").strip(),
        tags=RICH_TEXT_TAGS,
        attributes=RICH_TEXT_ATTRIBUTES,
        protocols={"http", "https", "mailto", "tel"},
        strip=True,
        strip_comments=True,
    )


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _safe_svg_attribute(name: str, value: str) -> bool:
    normalized = value.strip()
    if name in {"fill", "stroke", "clip-path", "mask"} and "url(" in normalized.lower():
        return bool(LOCAL_URL_PATTERN.fullmatch(normalized))
    return not re.search(r"javascript\s*:|data\s*:|https?\s*:", normalized, re.IGNORECASE)


def sanitize_svg_markup(value: str | None) -> str:
    raw_value = str(value or "").strip()
    if not raw_value or len(raw_value) > 100_000:
        return ""

    try:
        source_root = fromstring(raw_value)
    except (ValueError, etree.ParseError):
        return ""

    if _local_name(source_root.tag) != "svg":
        return ""

    def sanitize_element(source):
        tag = _local_name(source.tag)
        allowed_attributes = SVG_TAG_ATTRIBUTES.get(tag)
        if allowed_attributes is None:
            return None

        target = etree.Element(tag)
        for raw_name, raw_value in source.attrib.items():
            name = _local_name(raw_name)
            if name in allowed_attributes and _safe_svg_attribute(name, raw_value):
                target.set(name, raw_value.strip())

        if tag in {"title", "desc"} and source.text:
            target.text = source.text

        for child in source:
            sanitized_child = sanitize_element(child)
            if sanitized_child is not None:
                target.append(sanitized_child)

        return target

    sanitized_root = sanitize_element(source_root)
    if sanitized_root is None:
        return ""

    sanitized_root.set("xmlns", "http://www.w3.org/2000/svg")
    return etree.tostring(sanitized_root, encoding="unicode", short_empty_elements=True)


def is_safe_svg_markup(value: str | None) -> bool:
    return not value or bool(sanitize_svg_markup(value))
