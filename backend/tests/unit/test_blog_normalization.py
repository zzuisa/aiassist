"""Clipboard normalization corpus: HTML/Markdown/rich/code/URL-only (US1, T030).

Pure-function tests — no database — asserting visible-text preservation and safe
Markdown output across the supported ``detected_format`` values.
"""

from __future__ import annotations

import pytest

from app.modules.posts import normalization as nz

pytestmark = [pytest.mark.unit]


def test_plain_text_passthrough():
    r = nz.normalize_clipboard("just some words", "plain")
    assert r.normalized_markdown == "just some words"
    assert r.original_text == "just some words"
    assert r.warnings == []


def test_markdown_passthrough_preserved():
    md = "# Title\n\n- a\n- b\n\n**bold**"
    r = nz.normalize_clipboard(md, "markdown")
    assert r.normalized_markdown == md.strip()


def test_html_is_cleaned_and_converted():
    html = '<h1>Hi</h1><p>hello <b>world</b> <a href="https://x.io">link</a></p>'
    r = nz.normalize_clipboard(html, "html")
    assert "# Hi" in r.normalized_markdown
    assert "**world**" in r.normalized_markdown
    assert "[link](https://x.io)" in r.normalized_markdown
    # Visible words survive.
    for word in ("hello", "world", "link"):
        assert word in r.normalized_markdown


def test_html_script_is_stripped_but_text_kept():
    html = "<p>safe text</p><script>alert('x')</script>"
    r = nz.normalize_clipboard(html, "html")
    assert "safe text" in r.normalized_markdown
    assert "alert" not in r.normalized_markdown
    assert "<script" not in r.normalized_markdown


def test_javascript_href_is_neutralized():
    html = '<a href="javascript:alert(1)">click</a>'
    r = nz.normalize_clipboard(html, "html")
    assert "javascript:" not in r.normalized_markdown
    assert "click" in r.normalized_markdown  # visible text preserved


def test_code_is_fenced():
    code = "def f():\n    return 1"
    r = nz.normalize_clipboard(code, "code")
    assert r.normalized_markdown.startswith("```")
    assert r.normalized_markdown.rstrip().endswith("```")
    assert "def f()" in r.normalized_markdown


def test_url_only_capture():
    r = nz.normalize_clipboard("https://example.com/post", "url")
    assert "https://example.com/post" in r.normalized_markdown
    assert r.original_text == "https://example.com/post"


def test_invalid_format_raises():
    with pytest.raises(ValueError):
        nz.normalize_clipboard("x", "not-a-format")


def test_client_markdown_rejected_when_it_drops_content():
    html = "<p>alpha beta gamma delta</p>"
    # Client tries to submit a markdown that drops most visible tokens.
    r = nz.normalize_clipboard(html, "html", client_markdown="alpha")
    assert any("dropped content" in w for w in r.warnings)
    # Server version (full) is used instead.
    assert "beta" in r.normalized_markdown and "gamma" in r.normalized_markdown


def test_client_markdown_accepted_when_faithful():
    html = "<p>alpha beta</p>"
    r = nz.normalize_clipboard(html, "html", client_markdown="alpha beta")
    assert r.normalized_markdown == "alpha beta"
