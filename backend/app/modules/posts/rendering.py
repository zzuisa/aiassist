"""Markdown-to-HTML rendering with strict sanitization + RSS generation.

Public HTML is produced by rendering Markdown then sanitizing with nh3 (ammonia),
allowing only a safe tag/attribute allowlist and safe URL schemes. RSS output is
XML-escaped. Public derivatives never reference private asset keys.
"""

from __future__ import annotations

from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

import nh3
from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"linkify": True, "html": False})

_ALLOWED_TAGS = {
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
    "em",
    "del",
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
}
_ALLOWED_ATTRS = {
    # nh3 manages the <a rel> attribute itself via link_rel; do not list it here.
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "td": {"align"},
    "th": {"align"},
}
_ALLOWED_SCHEMES = {"http", "https", "mailto"}


def render_markdown(markdown: str) -> str:
    """Render Markdown to sanitized HTML safe for public display."""
    raw_html = _md.render(markdown or "")
    return nh3.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_ALLOWED_SCHEMES,
        link_rel="noopener nofollow noreferrer",
    )


def build_excerpt(markdown: str, limit: int = 200) -> str:
    text = " ".join((markdown or "").split())
    return text[:limit]


def render_rss(posts: list[dict], site_url: str, title: str = "AI Assist Blog") -> str:
    """Render a minimal, XML-escaped RSS 2.0 feed of published posts."""
    items = []
    for p in posts:
        link = f"{site_url.rstrip('/')}/blog/{p['slug']}"
        pub = p.get("published_at")
        pub_str = pub.strftime("%a, %d %b %Y %H:%M:%S GMT") if isinstance(pub, datetime) else ""
        items.append(
            "<item>"
            f"<title>{xml_escape(p['title'])}</title>"
            f"<link>{xml_escape(link)}</link>"
            f"<guid>{xml_escape(link)}</guid>"
            f"<pubDate>{xml_escape(pub_str)}</pubDate>"
            f"<description>{xml_escape(p.get('excerpt') or '')}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        f"<title>{xml_escape(title)}</title>"
        f"<link>{xml_escape(site_url)}</link>"
        f"<description>{xml_escape(title)}</description>" + "".join(items) + "</channel></rss>"
    )
