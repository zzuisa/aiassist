from __future__ import annotations

import pytest
from app.modules.agent.capability_selector import validate_route
from app.modules.agent.conversation_schemas import ConversationRoute

pytestmark = [pytest.mark.unit]


def _manifest(*, available=True, tool_type="read"):
    return {
        "schema_version": "safe-tool-manifest.v2",
        "tools": [
            {
                "key": "posts.list_recent",
                "source": "internal_api",
                "type": tool_type,
                "responsibility": "最近文章",
                "input_schema": {"type": "object"},
                "risk": {},
                "required_permission": "posts:read",
                "available": available,
                "unavailable_reason": None,
            }
        ],
    }


def _route(**updates):
    values = {
        "schema_version": "conversation-route.v1",
        "route_kind": "task",
        "objective": "最近文章",
        "operation_type": "query",
        "target_scope": {"source": "current_message", "object_type": "post", "object_ids": []},
        "semantic_arguments": {},
        "candidate_tool_keys": ["posts.list_recent"],
        "clarification_question": None,
        "requires_confirmation": False,
        "confidence": 0.9,
    }
    values.update(updates)
    return ConversationRoute.model_validate(values)


def test_accepts_available_candidate_and_selects_it() -> None:
    result = validate_route(_route(), _manifest(), allowed_candidates=["posts.list_recent"])
    assert result.valid is True
    assert result.selected_tool == "posts.list_recent"


@pytest.mark.parametrize(
    ("route", "manifest", "allowed", "code"),
    [
        (
            _route(candidate_tool_keys=["missing.tool"]),
            _manifest(),
            ["posts.list_recent"],
            "candidate_not_allowed",
        ),
        (_route(), _manifest(available=False), ["posts.list_recent"], "tool_unavailable"),
        (
            _route(operation_type="query"),
            _manifest(tool_type="write"),
            ["posts.list_recent"],
            "operation_type_mismatch",
        ),
        (_route(confidence=0.2), _manifest(), ["posts.list_recent"], "confidence_too_low"),
    ],
)
def test_policy_rejects_unsafe_or_uncertain_selection(route, manifest, allowed, code) -> None:
    result = validate_route(route, manifest, allowed_candidates=allowed)
    assert result.valid is False
    assert code in result.errors
    assert result.clarification_question
