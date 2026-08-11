"""conversation-route.v1 remains strict and policy-friendly."""

from __future__ import annotations

import uuid

import pytest
from app.modules.agent.conversation_schemas import ConversationRoute
from pydantic import ValidationError

pytestmark = [pytest.mark.contract]


def _route(**overrides):
    payload = {
        "schema_version": "conversation-route.v1",
        "route_kind": "task",
        "objective": "查询最近文章",
        "operation_type": "query",
        "target_scope": {"source": "current_message", "object_type": "post", "object_ids": []},
        "semantic_arguments": {"limit": 10},
        "candidate_tool_keys": ["posts.list_recent"],
        "clarification_question": None,
        "requires_confirmation": False,
        "confidence": 0.95,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("kind", ["chat", "capability_help", "clarification", "task"])
def test_every_route_kind_is_accepted(kind: str) -> None:
    assert ConversationRoute.model_validate(_route(route_kind=kind)).route_kind == kind


@pytest.mark.parametrize(
    "operation",
    [
        "none",
        "query",
        "analyze",
        "create",
        "update",
        "delete",
        "publish",
        "rollback",
        "external_effect",
    ],
)
def test_every_operation_type_is_accepted(operation: str) -> None:
    assert (
        ConversationRoute.model_validate(_route(operation_type=operation)).operation_type
        == operation
    )


@pytest.mark.parametrize(
    "source", ["none", "current_message", "conversation_context", "refresh_required"]
)
def test_every_scope_source_is_accepted(source: str) -> None:
    route = ConversationRoute.model_validate(
        _route(target_scope={"source": source, "object_type": None, "object_ids": []})
    )
    assert route.target_scope.source == source


def test_candidate_limit_unique_ids_and_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ConversationRoute.model_validate(
            _route(candidate_tool_keys=[f"tool.{i}" for i in range(13)])
        )
    duplicate = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        ConversationRoute.model_validate(
            _route(
                target_scope={
                    "source": "current_message",
                    "object_type": "post",
                    "object_ids": [duplicate, duplicate],
                }
            )
        )
    with pytest.raises(ValidationError):
        ConversationRoute.model_validate({**_route(), "hidden_reasoning": "never persist this"})
