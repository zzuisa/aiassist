"""JSON Schema validation for the route, SSE event, and safe manifest v2 contracts."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import jsonschema
import pytest

pytestmark = [pytest.mark.contract]

_SCHEMA_DIR = (
    Path(__file__).resolve().parents[3]
    / "specs"
    / "008-conversational-agent-mcp"
    / "contracts"
    / "schemas"
)


def _schema(name: str) -> dict:
    return json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))


ROUTE_SCHEMA = _schema("conversation-route.v1.json")
EVENT_SCHEMA = _schema("conversation-event.v1.json")
MANIFEST_SCHEMA = _schema("safe-tool-manifest.v2.json")


# -- conversation-route.v1 ----------------------------------------------------


def _valid_route(**overrides: object) -> dict:
    base = {
        "schema_version": "conversation-route.v1",
        "route_kind": "task",
        "objective": "列出最近的文章",
        "operation_type": "query",
        "target_scope": {
            "source": "current_message",
            "object_type": "post",
            "object_ids": [],
        },
        "semantic_arguments": {"limit": 10},
        "candidate_tool_keys": ["posts.list_recent"],
        "requires_confirmation": False,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_conversation_route_schema_accepts_the_pydantic_model_output() -> None:
    from app.modules.agent.conversation_schemas import ConversationRoute

    route = ConversationRoute.model_validate(_valid_route())
    jsonschema.validate(json.loads(route.model_dump_json()), ROUTE_SCHEMA)


def test_conversation_route_schema_rejects_extra_fields() -> None:
    payload = _valid_route(unexpected="nope")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, ROUTE_SCHEMA)


def test_conversation_route_schema_rejects_missing_required_field() -> None:
    payload = _valid_route()
    del payload["confidence"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, ROUTE_SCHEMA)


def test_conversation_route_schema_rejects_too_many_candidates() -> None:
    payload = _valid_route(candidate_tool_keys=[f"tool.{i}" for i in range(13)])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, ROUTE_SCHEMA)


@pytest.mark.parametrize("route_kind", ["chat", "capability_help", "clarification", "task"])
def test_conversation_route_schema_accepts_every_route_kind(route_kind: str) -> None:
    jsonschema.validate(_valid_route(route_kind=route_kind), ROUTE_SCHEMA)


def test_conversation_route_schema_rejects_unknown_route_kind() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_valid_route(route_kind="unknown"), ROUTE_SCHEMA)


# -- conversation-event.v1 -----------------------------------------------------


def test_conversation_event_schema_accepts_status_builder_output() -> None:
    from app.models.agent_conversation import AgentTurn

    turn = AgentTurn(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        status="accepted",
        current_step=None,
    )
    from app.modules.agent.status import build_conversation_event_payload

    payload = build_conversation_event_payload(
        turn,
        event_type="conversation.turn_updated",
        stage_label="路由中",
    )
    jsonschema.validate(payload, EVENT_SCHEMA)


def test_conversation_event_schema_rejects_unknown_status() -> None:
    payload = {
        "schema_version": "conversation-event.v1",
        "event_type": "conversation.turn_updated",
        "conversation_id": str(uuid.uuid4()),
        "turn_id": str(uuid.uuid4()),
        "status": "not_a_real_status",
        "timestamp": "2026-08-10T00:00:00+00:00",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, EVENT_SCHEMA)


def test_conversation_event_schema_rejects_extra_fields() -> None:
    payload = {
        "schema_version": "conversation-event.v1",
        "event_type": "conversation.message_created",
        "conversation_id": str(uuid.uuid4()),
        "turn_id": str(uuid.uuid4()),
        "status": "accepted",
        "timestamp": "2026-08-10T00:00:00+00:00",
        "endpoint": "https://leak.example.com",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, EVENT_SCHEMA)


# -- safe-tool-manifest.v2 -----------------------------------------------------


def test_safe_manifest_v2_schema_accepts_registry_output() -> None:
    from app.modules.agent.registry import tool_registry

    payload = tool_registry.safe_manifest_v2()
    jsonschema.validate(payload, MANIFEST_SCHEMA)


def test_safe_manifest_v2_schema_rejects_missing_required_tool_field() -> None:
    payload = {
        "schema_version": "safe-tool-manifest.v2",
        "tools": [
            {
                "key": "posts.list_recent",
                "source": "internal_api",
                "type": "read",
                "responsibility": "list posts",
                "input_schema": {"type": "object"},
                "risk": {},
                "required_permission": None,
                # "available" intentionally omitted
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, MANIFEST_SCHEMA)


def test_safe_manifest_v2_schema_rejects_more_than_100_tools() -> None:
    entry = {
        "key": "x",
        "source": "internal_api",
        "type": "read",
        "responsibility": "x",
        "input_schema": {"type": "object"},
        "risk": {},
        "required_permission": None,
        "available": True,
        "unavailable_reason": None,
    }
    payload = {"schema_version": "safe-tool-manifest.v2", "tools": [entry] * 101}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, MANIFEST_SCHEMA)
