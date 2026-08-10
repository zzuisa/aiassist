"""Conversation scope excludes objects whose steps already succeeded."""

from __future__ import annotations

from app.modules.agent.service import remaining_scope_object_ids


def test_completed_objects_are_not_repeated_but_failed_objects_can_retry() -> None:
    scope = {
        "object_ids": ["a", "b", "c", "d"],
        "completed_object_ids": ["a", "c", "outside"],
        "failed_object_ids": ["b"],
    }

    assert remaining_scope_object_ids(scope) == ["b", "d"]


def test_duplicate_and_invalid_scope_values_are_not_reexecuted() -> None:
    scope = {
        "object_ids": ["a", "a", "", None, "b"],
        "completed_object_ids": ["a"],
    }

    assert remaining_scope_object_ids(scope) == ["b"]
