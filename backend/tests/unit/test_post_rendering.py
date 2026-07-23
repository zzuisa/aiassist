"""Markdown sanitization, unsafe link/image handling, RSS escaping."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.modules.posts import rendering

pytestmark = [pytest.mark.unit]


def test_script_tags_are_stripped():
    html = rendering.render_markdown("正文\n\n<script>alert(1)</script>")
    assert "<script>" not in html
    assert "alert(1)" not in html or "<script>" not in html


def test_javascript_url_is_removed():
    html = rendering.render_markdown("[点击](javascript:alert(1))")
    # The dangerous scheme must never become a real, clickable link.
    assert 'href="javascript:' not in html
    assert "<a " not in html or "javascript:" not in html.split("<a ", 1)[-1].split(">", 1)[0]


def test_safe_links_get_rel_and_are_kept():
    html = rendering.render_markdown("[官网](https://example.com)")
    assert 'href="https://example.com"' in html
    assert "nofollow" in html or "noopener" in html


def test_basic_formatting_preserved():
    html = rendering.render_markdown("# 标题\n\n**粗体** 和 *斜体*")
    assert "<h1>" in html
    assert "<strong>" in html
    assert "<em>" in html


def test_rss_escapes_special_characters():
    feed = rendering.render_rss(
        [
            {
                "slug": "a",
                "title": "标题 & <危险>",
                "excerpt": '引号"和<标签>',
                "published_at": datetime(2026, 7, 24, tzinfo=UTC),
            }
        ],
        "https://llm.roguelife.de",
    )
    assert "<危险>" not in feed
    assert "&amp;" in feed
    assert "&lt;" in feed


def test_rss_is_wellformed_xml():
    from xml.etree import ElementTree

    feed = rendering.render_rss(
        [{"slug": "a", "title": "标题", "excerpt": "", "published_at": None}],
        "https://llm.roguelife.de",
    )
    # Raises if not well-formed. Our own generated feed is trusted content.
    ElementTree.fromstring(feed)  # noqa: S314
