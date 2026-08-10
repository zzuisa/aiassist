"""Effective field policy and full/partial/rejected classification (US3, T066)."""

from __future__ import annotations

import pytest
from app.modules.posts import field_policy as fp

pytestmark = [pytest.mark.unit]


def test_unlisted_field_defaults_to_suggest_only_partial():
    assert fp.effective_policy({}, "title") in (
        "suggest_only",
        "require_confirmation",
        "allow_overwrite",
    )
    assert fp.classify_field({}, "summary") == "partial"


def test_markdown_can_never_auto_apply_even_if_skill_says_auto_fill():
    # A misconfigured Skill tries to auto_fill the body; the ceiling clamps it.
    policy = fp.effective_policy({"markdown": "auto_fill"}, "markdown")
    assert policy == "require_confirmation"
    assert fp.classify_field({"markdown": "auto_fill"}, "markdown") == "partial"


def test_forbid_is_rejected():
    assert fp.classify_field({"summary": "forbid"}, "summary") == "rejected"


def test_allow_overwrite_title_is_full():
    assert fp.classify_field({"title": "allow_overwrite"}, "title") == "full"


def test_non_applyable_path_is_rejected():
    assert fp.classify_field({}, "status") == "rejected"
    with pytest.raises(ValueError):
        fp.validate_path("id")


def test_structured_data_subkey_is_allowed_but_capped():
    assert fp.classify_field({"structured_data": "auto_fill"}, "structured_data.difficulty") in (
        "partial",
    )


def test_blocking_protected_change_forces_markdown_rejected():
    assert (
        fp.classify_field(
            {"markdown": "allow_overwrite"},
            "markdown",
            has_blocking_protected_change=True,
        )
        == "rejected"
    )


def test_classify_candidate_maps_every_field():
    result = fp.classify_candidate(
        {"title": "allow_overwrite", "summary": "forbid"},
        ["title", "summary", "markdown"],
    )
    assert result == {"title": "full", "summary": "rejected", "markdown": "partial"}
