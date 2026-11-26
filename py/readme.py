"""Hub README fetching, sanitizing and front-matter merging.

The Civitai searcher builds the notes (the model description) out of the
API's model/version payloads, so the model card's Description tab worked for
Civitai out of the box. The Hugging Face and ModelScope searchers had no
such payload and wrote "No description about this model" into the notes
instead — even though every hub repository ships a ``README.md``. This module
fetches that README and folds it into the notes.

Security contract — the notes are persisted to disk and rendered as HTML by
the frontend (markdown-it with ``html: true``), so the README is treated as
untrusted input at every step:

* the body is passed through an **allowlist HTML sanitizer** (a small
  ``html.parser`` filter, not a regex) — ``<script>``/``<style>``/``<iframe>``/
  ``<object>``/``<embed>``/``<svg>``/``<math>`` and their contents are dropped
  outright, every other tag outside the allowlist is unwrapped (its text
  children survive), and all attributes outside the per-tag allowlist are
  dropped, which removes every ``on*`` handler and ``javascript:`` URL;
* ``href`` keeps only ``http(s)``/``mailto``/fragments, ``src`` only
  ``http(s)`` — everything else is removed; remote images and links have
  their scheme forced lowercase and relative URLs are resolved against the
  repository's raw base;
* markdown links/images with relative targets are absolutized against the
  same base (the stock ComfyUI origin cannot resolve them);
* the response is **size-capped** while streaming (a hostile or misbehaving
  CDN object cannot balloon memory) and decoded as UTF-8 with replacement.

The README's own YAML front-matter (``license``, ``language``, ``tags`` ...)
is parsed and merged into the notes' front-matter as *additional information
rows*: scalars and short scalar lists only, depth 1, a handful of keys —
enough for the Information tab to show the card's license and friends without
letting a pathological card inflate the notes file. Values the notes already
define (``website``, ``modelPage``, ``author``, ``preview`` ...) are never
overwritten.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from . import http_client

#: A README is documentation, not a data blob: 1 MiB is generous (the largest
#: model-card README observed in the wild is ~200 KiB) and the cap is enforced
#: while streaming, before anything is decoded.
MAX_README_BYTES = 1024 * 1024

#: Absolute floor/ceiling for the rendered body after decoding (UTF-8 is at
#: most 4 bytes/char, so anything past this is a decode artefact, not real
#: content).
_MAX_BODY_CHARS = 400_000

#: How many extra front-matter keys a card may contribute to the Information
#: tab, and how large each value may be. Generous for real cards, tight enough
#: that a card with a 50-entry example-prompt list cannot bloat the notes.
_MAX_MERGE_KEYS = 20
_MAX_SCALAR_CHARS = 500
_MAX_LIST_ITEMS = 8
_MAX_LIST_ITEM_CHARS = 120

# ---------------------------------------------------------------------------
# YAML front-matter split
# ---------------------------------------------------------------------------
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a leading ``---\\n...\\n---`` YAML block from ``text``.

    Returns ``(front_matter, body)``. Any failure shape (no block, unparseable
    YAML, non-mapping YAML) yields ``({}, text)`` or ``({}, body)`` with the
    original text preserved — the README body is never lost.
    """
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, text[match.end() :]
    if not isinstance(data, dict):
        return {}, text[match.end() :]
    return data, text[match.end() :]


# ---------------------------------------------------------------------------
# Card front-matter -> notes front-matter merge
# ---------------------------------------------------------------------------
def _clean_card_value(value: Any) -> Any | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned[:_MAX_SCALAR_CHARS]
    if isinstance(value, (list, tuple)):
        items: list[Any] = []
        for item in value[:_MAX_LIST_ITEMS]:
            if isinstance(item, bool) or isinstance(item, (int, float)):
                items.append(item)
            elif isinstance(item, str):
                cleaned = item.strip()[:_MAX_LIST_ITEM_CHARS]
                if cleaned:
                    items.append(cleaned)
            # deeper structures are dropped item-by-item
        return items or None
    # mappings / anything else: not a scalar row, drop
    return None


def merge_card_metadata(ours: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    """Merge card front-matter into ours (ours wins, scalars/short lists only)."""
    merged = dict(ours)
    added = 0
    for key, value in card.items():
        if added >= _MAX_MERGE_KEYS:
            break
        key_text = str(key).strip()
        # keep YAML-safe, renderer-friendly keys only
        if not key_text or not re.fullmatch(r"[A-Za-z0-9_. -]{1,60}", key_text):
            continue
        if key_text in merged:
            continue
        cleaned = _clean_card_value(value)
        if cleaned is None:
            continue
        merged[key_text] = cleaned
        added += 1
    return merged


# ---------------------------------------------------------------------------
# HTML sanitizer (allowlist, html.parser based)
# ---------------------------------------------------------------------------
# Tags that are dropped together with their *contents* (never worth showing).
_DROP_WITH_CONTENT = frozenset(
    {"script", "style", "iframe", "object", "embed", "applet", "form", "svg", "math", "noscript", "template", "title"}
)
# Tags that are re-emitted with filtered attributes.
_ALLOWED_TAGS = frozenset(
    {
        "a",
        "p",
        "br",
        "hr",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "del",
        "ins",
        "code",
        "pre",
        "blockquote",
        "q",
        "cite",
        "sup",
        "sub",
        "kbd",
        "samp",
        "var",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "colgroup",
        "col",
        "img",
        "figure",
        "figcaption",
        "details",
        "summary",
        "span",
        "div",
        "section",
        "article",
        "aside",
        "header",
        "footer",
        "main",
    }
)
# Per-tag attribute allowlist.
_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "title", "width", "height"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
    "ol": frozenset({"start"}),
    "li": frozenset({"value"}),
    "details": frozenset({"open"}),
}
_NUMERIC_ATTRS = frozenset({"width", "height", "colspan", "rowspan", "span", "start", "value"})

_ATTR_NAME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9-]{0,40}\Z")

_SCHEME_RE = re.compile(r"\A([a-zA-Z][a-zA-Z0-9+.-]*):")


def _clean_url(value: str, base_url: str | None, *, allow_fragment: bool, allow_mailto: bool) -> str | None:
    raw = value.strip()
    if not raw or len(raw) > 2000:
        return None
    if raw.startswith("#"):
        return raw if allow_fragment else None
    if raw.startswith("//"):
        raw = f"https:{raw}"
    match = _SCHEME_RE.match(raw)
    if match:
        scheme = match.group(1).lower()
        if scheme in ("http", "https"):
            return raw
        if scheme == "mailto" and allow_mailto:
            return raw
        return None
    # relative URL: only meaningful against a base (the repo's raw root)
    if base_url:
        return urljoin(base_url, raw)
    return None


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape_text(text).replace('"', "&quot;")


class _Sanitizer(HTMLParser):
    """Allowlist HTML filter. Unwraps unknown tags, drops dangerous ones.

    ``html.parser`` never executes anything, so the only obligation here is
    not to emit dangerous markup: every emitted tag is in ``_ALLOWED_TAGS``,
    every attribute is per-tag allowlisted with scheme-checked URLs, and text
    is entity-escaped on the way out.
    """

    def __init__(self, base_url: str | None):
        super().__init__(convert_charrefs=True)
        self._base = base_url
        self._out: list[str] = []
        self._drop_depth = 0

    def get_html(self) -> str:
        return "".join(self._out)

    # -- tag emission ------------------------------------------------------
    def _clean_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
        allowed = _ALLOWED_ATTRS.get(tag, frozenset())
        cleaned: list[tuple[str, str]] = []
        for name, value in attrs:
            if value is None:
                continue
            name_lower = name.lower()
            if name_lower not in allowed or not _ATTR_NAME_RE.match(name_lower):
                continue
            if name_lower in _NUMERIC_ATTRS:
                if re.fullmatch(r"\d{1,3}", value.strip()):
                    cleaned.append((name_lower, value.strip()))
                continue
            if name_lower == "href":
                url = _clean_url(value, self._base, allow_fragment=True, allow_mailto=True)
                if url is not None:
                    cleaned.append((name_lower, url))
                continue
            if name_lower == "src":
                url = _clean_url(value, self._base, allow_fragment=False, allow_mailto=False)
                if url is not None and _SCHEME_RE.match(url) and _SCHEME_RE.match(url).group(1).lower() in ("http", "https"):
                    cleaned.append((name_lower, url))
                continue
            if name_lower == "open":
                cleaned.append((name_lower, ""))
                continue
            cleaned.append((name_lower, value.strip()[:2000]))
        return cleaned

    def _emit_start(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        cleaned = self._clean_attrs(tag, attrs)
        if tag == "a":
            cleaned.append(("target", "_blank"))
            cleaned.append(("rel", "noopener noreferrer"))
        attr_text = "".join(f' {name}="{_escape_attr(value)}"' if value else f" {name}" for name, value in cleaned)
        self._out.append(f"<{tag}{attr_text}>")
        if self_closing:
            self._out.append(f"</{tag}>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self._drop_depth += 1
            return
        if self._drop_depth:
            return
        if tag not in _ALLOWED_TAGS:
            return  # unwrap: children still processed
        self._emit_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            return
        if self._drop_depth:
            return
        if tag not in _ALLOWED_TAGS:
            return
        if tag in ("br", "hr", "img", "col"):
            self._emit_start(tag, attrs, self_closing=False)
        else:
            self._emit_start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if self._drop_depth:
            return
        if tag not in _ALLOWED_TAGS:
            return
        if tag in ("br", "hr", "img"):
            return  # void elements have no closing tag
        self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        self._out.append(_escape_text(data))


def sanitize_readme_html(text: str, base_url: str | None) -> str:
    parser = _Sanitizer(base_url)
    parser.feed(text)
    parser.close()
    return parser.get_html()


# ---------------------------------------------------------------------------
# markdown-relative URL absolutizer
# ---------------------------------------------------------------------------
_SCHEME_OR_FRAGMENT_RE = re.compile(r"\A(#|[a-zA-Z][a-zA-Z0-9+.-]*:)")
_MD_TARGET_RE = re.compile(r"(\!?\[[^\]\n]*\]\()\s*(<[^>]+>|[^)\s]+)((?:\s+\"[^\"]*\")?\s*\))")


def absolutize_markdown_urls(text: str, base_url: str | None) -> str:
    """Rewrite relative markdown link/image targets to absolute URLs."""
    if not base_url:
        return text

    def _replace(match: re.Match[str]) -> str:
        open_part, target, close_part = match.group(1), match.group(2), match.group(3)
        inner = target[1:-1] if target.startswith("<") and target.endswith(">") else target
        if _SCHEME_OR_FRAGMENT_RE.match(inner):
            return match.group(0)
        url = urljoin(base_url, inner)
        # A destination with a space or parenthesis is only valid inside
        # angle brackets in markdown - re-wrap or markdown-it truncates the URL.
        if any(ch in url for ch in " ()"):
            return f"{open_part}<{url}>{close_part}"
        return f"{open_part}{url}{close_part}"

    return _MD_TARGET_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# top-level helpers
# ---------------------------------------------------------------------------
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def process_readme(text: str, base_url: str) -> tuple[dict[str, Any], str]:
    """Split + sanitize a hub README.

    Returns ``(card_front_matter, markdown_body)`` — the body is safe to embed
    in the notes (untrusted HTML handled) with URLs resolved against
    ``base_url``.
    """
    card, body = split_front_matter(text)
    body = sanitize_readme_html(body, base_url)
    body = absolutize_markdown_urls(body, base_url)
    body = _BLANK_RUN_RE.sub("\n\n", body).strip()
    return card, body[:_MAX_BODY_CHARS]


async def fetch_hub_readme(url: str, *, headers: dict[str, str] | None) -> str | None:
    """GET a README (size-capped while streaming); ``None`` on any failure."""
    raw = await http_client.fetch_bytes_capped(url, headers=headers, timeout=http_client.HUB_TIMEOUT, max_bytes=MAX_README_BYTES)
    if not raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")
