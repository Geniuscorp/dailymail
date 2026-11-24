"""Sanitising inbound email HTML while keeping its layout.

Email is table-and-inline-style markup: the borders, header colours, column
widths and ``<font>`` tags are what make an invoice or an appointment notice
readable. Stripping them leaves a wall of unaligned text, so they are kept, and
everything that can run or fetch something is not.

Layers, outermost first: this allow-list (no scripts, forms, frames, remote or
``javascript:`` URLs, no CSS that can load a resource or lay out over the page),
the frontend's sandboxed iframe without ``allow-scripts``, and its CSP, which
blocks every network request. Remote images are therefore never fetched (no
tracking pixels); only embedded ``data:`` images are shown.
"""
import re
from typing import Optional

import nh3

ALLOWED_TAGS = {
    "a", "abbr", "address", "b", "blockquote", "br", "caption", "center", "cite",
    "code", "col", "colgroup", "dd", "del", "div", "dl", "dt", "em", "figcaption",
    "figure", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
    "li", "mark", "ol", "p", "pre", "q", "s", "section", "small", "span", "strike",
    "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
    "u", "ul",
}

_CELL_ATTRIBUTES = {"colspan", "rowspan", "nowrap", "headers", "scope"}

ALLOWED_ATTRIBUTES = {
    "*": {"style", "align", "valign", "bgcolor", "width", "height", "dir", "lang", "title"},
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height", "align"},
    "table": {"border", "cellpadding", "cellspacing", "summary"},
    "td": _CELL_ATTRIBUTES,
    "th": _CELL_ATTRIBUTES,
    "col": {"span"},
    "colgroup": {"span"},
    "font": {"color", "size", "face"},
    "ol": {"start", "type"},
}

# Visual properties only: nothing that positions content over the page, loads
# a resource (background-image, list-style-image, cursor, content) or hides
# behaviour in a value.
_BOX_SIDES = ("", "-top", "-right", "-bottom", "-left")
ALLOWED_CSS_PROPERTIES = {
    "background", "background-color", "color", "direction", "display", "font", "font-family",
    "font-size", "font-style", "font-variant", "font-weight", "height", "letter-spacing",
    "line-height", "list-style", "list-style-type", "max-height", "max-width", "min-height",
    "min-width", "table-layout", "text-align", "text-decoration", "text-indent",
    "text-transform", "vertical-align", "white-space", "width", "word-break", "word-spacing",
    "overflow-wrap", "word-wrap", "border-collapse", "border-spacing", "border-radius",
    "box-sizing",
}
for _side in _BOX_SIDES:
    for _base in ("margin", "padding", "border"):
        ALLOWED_CSS_PROPERTIES.add(f"{_base}{_side}")
    for _suffix in ("color", "style", "width"):
        ALLOWED_CSS_PROPERTIES.add(f"border{_side}-{_suffix}")

_FORBIDDEN_IN_CSS_VALUE = ("url(", "expression", "javascript:", "@import", "\\", "<", ">", "behavior")
_DATA_IMAGE = re.compile(r"^data:image/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.IGNORECASE)
_UNSAFE_HREF = re.compile(r"^\s*(?:data|javascript|vbscript):", re.IGNORECASE)


def clean_style(value: str) -> Optional[str]:
    """Keep only the safe declarations of an inline ``style`` attribute."""
    kept = []
    for declaration in value.split(";"):
        name, separator, raw = declaration.partition(":")
        name, raw = name.strip().lower(), raw.strip()
        if not separator or name not in ALLOWED_CSS_PROPERTIES or not raw:
            continue
        lowered = raw.lower()
        if any(token in lowered for token in _FORBIDDEN_IN_CSS_VALUE):
            continue
        kept.append(f"{name}:{raw}")
    return ";".join(kept) or None


def _filter_attribute(tag: str, attribute: str, value: str) -> Optional[str]:
    if attribute == "style":
        return clean_style(value)
    if attribute == "src":
        # Remote images are never loaded (CSP), so only embedded images are worth keeping.
        return value if tag == "img" and _DATA_IMAGE.match(value) else None
    if attribute == "href" and _UNSAFE_HREF.match(value):
        return None
    return value


def sanitize_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=_filter_attribute,
        link_rel="noopener noreferrer nofollow",
        # "data" is let through the scheme check only so embedded images survive;
        # _filter_attribute removes it from everything except <img src>.
        url_schemes={"http", "https", "mailto", "data"},
    )
