import re


UNSAFE_SVG_PATTERNS = (
    r"<\s*script\b",
    r"\son[a-z]+\s*=",
    r"javascript\s*:",
    r"<\s*(iframe|object|embed)\b",
)


def is_safe_svg_markup(value: str | None) -> bool:
    if not value:
        return True

    for pattern in UNSAFE_SVG_PATTERNS:
        if re.search(pattern, value, flags=re.IGNORECASE):
            return False
    return True
