"""Protected-token extraction and comparison (spec 005, US3, T065)."""

from __future__ import annotations

import pytest

from app.modules.posts import protected_content as pc

pytestmark = [pytest.mark.unit]


def test_extracts_each_category():
    md = (
        "# Title\n\n"
        "Use `pip install x` inline.\n\n"
        "```\n$ ls -la\n```\n\n"
        "See https://example.com/a for 42 items on 2026-07-29.\n\n"
        "> a wise quotation\n"
    )
    tokens = pc.extract_tokens(md)
    assert any("ls -la" in c for c in tokens["code"])
    assert "pip install x" in tokens["code"]
    assert "ls -la" in tokens["command"]
    assert "https://example.com/a" in tokens["url"]
    assert "42" in tokens["number"]
    assert "2026-07-29" in tokens["date"]
    assert "a wise quotation" in tokens["quote"]


def test_identical_text_has_no_changes():
    md = "Value 100 at https://x.io on 2026-01-01\n> keep"
    assert pc.compare(md, md) == []
    assert pc.token_hash(md) == pc.token_hash(md)


def test_changed_code_is_blocking():
    base = "```\nprint(1)\n```"
    cand = "```\nprint(2)\n```"
    changes = pc.compare(base, cand)
    assert len(changes) == 1
    assert changes[0].category == "code"
    assert changes[0].severity == "blocking"
    assert pc.has_blocking_change(changes)


def test_changed_url_is_warning_not_blocking():
    base = "see https://a.io"
    cand = "see https://b.io"
    changes = pc.compare(base, cand)
    assert changes[0].category == "url"
    assert changes[0].severity == "warning"
    assert not pc.has_blocking_change(changes)


def test_changed_number_and_date_are_warnings():
    base = "42 items on 2026-07-29"
    cand = "43 items on 2026-07-30"
    cats = {ch.category: ch.severity for ch in pc.compare(base, cand)}
    assert cats["number"] == "warning"
    assert cats["date"] == "warning"


def test_removed_quote_is_blocking():
    base = "> original source line\n\ntext"
    cand = "text only"
    changes = pc.compare(base, cand)
    assert any(ch.category == "quote" and ch.severity == "blocking" for ch in changes)


def test_token_hash_is_order_independent_within_category():
    a = "`x` and `y`"
    b = "`y` and `x`"
    assert pc.token_hash(a) == pc.token_hash(b)


def test_reordering_prose_around_stable_tokens_is_no_change():
    base = "Install with `npm i`. Visit https://x.io."
    cand = "Visit https://x.io. Install with `npm i`."
    assert pc.compare(base, cand) == []
