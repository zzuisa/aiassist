"""Clipboard normalization: type validation, HTML cleaning, Markdown output (T035).

Given raw clipboard content and a client-declared ``detected_format``, produce a
safe canonical Markdown string plus a plain ``original_text`` while *preserving
visible text*.  HTML is sanitized with nh3 (ammonia) to a conservative allow-list
before conversion; the reverse check ensures no visible words silently vanish.

Nothing here performs network I/O — clipboard capture is fully local so it works
when everything else is down.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import nh3

# Formats the client may declare (mirrors ClipboardCapture.detected_format).
DETECTED_FORMATS = ("plain", "markdown", "html", "rich", "url", "code", "image", "mixed")

# nh3 allow-list for cleaning pasted HTML before markdown conversion.
_HTML_TAGS = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "b",
    "em",
    "i",
    "del",
    "s",
    "u",
    "blockquote",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "span",
    "div",
}
_HTML_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
}
_URL_RE = re.compile(r"^\s*https?://[^\s]+\s*$", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NormalizationResult:
    detected_format: str
    original_text: str
    normalized_markdown: str
    warnings: list[str]


def validate_detected_format(fmt: str) -> None:
    if fmt not in DETECTED_FORMATS:
        raise ValueError(
            f"detected_format '{fmt}' invalid; expected one of {', '.join(DETECTED_FORMATS)}"
        )


def _visible_words(text: str) -> set[str]:
    """Rough visible-token set used to detect content loss during cleaning."""
    stripped = _TAG_RE.sub(" ", text)
    return {w for w in re.split(r"\s+", stripped) if len(w) >= 2}


def clean_html(raw: str) -> str:
    """Sanitize pasted HTML to the conservative allow-list."""
    return nh3.clean(
        raw,
        tags=_HTML_TAGS,
        attributes=_HTML_ATTRS,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )


def _html_to_markdown(clean: str) -> str:
    """Minimal, dependency-free HTML→Markdown for common block/inline tags.

    This intentionally handles only the tags in the allow-list; anything else is
    stripped to its text so visible content survives.
    """
    s = clean
    # Block-level normalization
    s = re.sub(
        r"(?is)<h([1-6])[^>]*>(.*?)</h\1>",
        lambda m: "\n" + "#" * int(m.group(1)) + " " + m.group(2).strip() + "\n",
        s,
    )
    s = re.sub(
        r"(?is)<blockquote[^>]*>(.*?)</blockquote>", lambda m: "\n> " + m.group(1).strip() + "\n", s
    )
    s = re.sub(
        r"(?is)<pre[^>]*>(.*?)</pre>", lambda m: "\n```\n" + m.group(1).strip() + "\n```\n", s
    )
    s = re.sub(r"(?is)<li[^>]*>(.*?)</li>", lambda m: "- " + m.group(1).strip() + "\n", s)
    s = re.sub(r"(?is)</?(ul|ol)[^>]*>", "\n", s)
    s = re.sub(r"(?is)<(strong|b)[^>]*>(.*?)</\1>", lambda m: "**" + m.group(2) + "**", s)
    s = re.sub(r"(?is)<(em|i)[^>]*>(.*?)</\1>", lambda m: "*" + m.group(2) + "*", s)
    s = re.sub(r"(?is)<code[^>]*>(.*?)</code>", lambda m: "`" + m.group(1) + "`", s)
    s = re.sub(
        r'(?is)<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        lambda m: f"[{m.group(2).strip()}]({m.group(1)})",
        s,
    )
    s = re.sub(
        r'(?is)<img[^>]*alt="([^"]*)"[^>]*src="([^"]*)"[^>]*>',
        lambda m: f"![{m.group(1)}]({m.group(2)})",
        s,
    )
    s = re.sub(r'(?is)<img[^>]*src="([^"]*)"[^>]*>', lambda m: f"![]({m.group(1)})", s)
    s = re.sub(r"(?is)</p>", "\n\n", s)
    s = re.sub(r"(?is)<br[^>]*>", "\n", s)
    # Strip any remaining tags to their text (visible content preserved).
    s = _TAG_RE.sub("", s)
    # Collapse excess blank lines / trailing spaces.
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _plain_text_from_html(clean: str) -> str:
    return re.sub(r"\s+\n", "\n", _TAG_RE.sub("", clean)).strip()


def normalize_clipboard(
    raw_content: str,
    detected_format: str,
    client_markdown: str | None = None,
) -> NormalizationResult:
    """Normalize *raw_content* into safe Markdown, preserving visible text.

    ``client_markdown`` (optional) is a client-supplied normalization that we
    accept only when it does not drop visible words relative to the raw content.
    """
    validate_detected_format(detected_format)
    warnings: list[str] = []
    fmt = detected_format

    if fmt in ("html", "rich", "mixed"):
        cleaned = clean_html(raw_content)
        original_text = _plain_text_from_html(cleaned)
        markdown = _html_to_markdown(cleaned)
        # Visible-text preservation check.
        lost = _visible_words(raw_content) - _visible_words(markdown)
        if lost:
            warnings.append(f"{len(lost)} visible token(s) not represented after HTML cleaning")
    elif fmt == "code":
        original_text = raw_content
        markdown = "```\n" + raw_content.rstrip("\n") + "\n```"
    elif fmt == "url":
        original_text = raw_content.strip()
        markdown = original_text if _URL_RE.match(raw_content) else f"<{original_text}>"
    else:  # plain, markdown, image
        original_text = raw_content
        markdown = raw_content

    # Accept a client-provided markdown only if it preserves visible tokens.
    if client_markdown is not None:
        lost = _visible_words(original_text) - _visible_words(client_markdown)
        if lost:
            warnings.append("client normalized_markdown dropped content; using server version")
        else:
            markdown = client_markdown

    return NormalizationResult(
        detected_format=fmt,
        original_text=original_text,
        normalized_markdown=markdown.strip(),
        warnings=warnings,
    )
