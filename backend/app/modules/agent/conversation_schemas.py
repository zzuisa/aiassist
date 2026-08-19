"""Pydantic schemas for the conversational Agent REST boundary and the
structured LLM route decision.

``ConversationRoute`` mirrors ``contracts/schemas/conversation-route.v1.json``
field-for-field (same required fields, enums, and limits) so a
``model_json_schema()`` divergence test can catch drift; see
``tests/contract/test_conversation_schemas.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# -- REST boundary -----------------------------------------------------------


class ConversationStatus(StrEnum):
    active = "active"
    archived = "archived"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class MessageKind(StrEnum):
    text = "text"
    clarification = "clarification"
    result = "result"
    error = "error"


class TurnStatus(StrEnum):
    accepted = "accepted"
    routing = "routing"
    waiting_clarification = "waiting_clarification"
    executing = "executing"
    waiting_confirmation = "waiting_confirmation"
    success = "success"
    partial_success = "partial_success"
    failed = "failed"
    stalled = "stalled"
    cancelled = "cancelled"


class Conversation(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    id: uuid.UUID
    title: str | None = None
    status: ConversationStatus
    last_message_at: datetime | None = None
    created_at: datetime


class Turn(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    status: TurnStatus
    route_kind: str | None = None
    current_step: str | None = None
    agent_task_id: uuid.UUID | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ConversationDetail(Conversation):
    active_turns: list[Turn] = Field(default_factory=list)


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    id: uuid.UUID
    role: MessageRole
    kind: MessageKind
    content: dict[str, Any] = Field(validation_alias="content_json")
    turn_id: uuid.UUID | None = None
    created_at: datetime


class MessagePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Message]
    next_cursor: str | None = None


class TurnAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Message
    turn: Turn


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_message_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)


# -- Structured LLM route decision (conversation-route.v1) -------------------


class RouteKind(StrEnum):
    chat = "chat"
    capability_help = "capability_help"
    clarification = "clarification"
    task = "task"


class RouteOperationType(StrEnum):
    none = "none"
    query = "query"
    analyze = "analyze"
    create = "create"
    update = "update"
    delete = "delete"
    publish = "publish"
    rollback = "rollback"
    external_effect = "external_effect"


class TargetScopeSource(StrEnum):
    none = "none"
    current_message = "current_message"
    conversation_context = "conversation_context"
    refresh_required = "refresh_required"


class TargetScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: TargetScopeSource
    object_type: str | None = Field(default=None, max_length=80)
    object_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)

    @field_validator("object_ids")
    @classmethod
    def _unique_object_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("object_ids must be unique")
        return value


class ConversationToolCall(BaseModel):
    """One schema-constrained tool proposal produced by the routing model."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=160)]
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConversationRoute(BaseModel):
    """Structured, versioned routing fact. No chain-of-thought fields exist —
    only route kind, objective, scope, semantic args, and candidates."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["conversation-route.v1"] = "conversation-route.v1"
    route_kind: RouteKind
    objective: str = Field(max_length=500)
    operation_type: RouteOperationType
    target_scope: TargetScope
    semantic_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_call: ConversationToolCall | None = None
    candidate_tool_keys: list[Annotated[str, Field(max_length=160)]] = Field(
        default_factory=list, max_length=12
    )
    clarification_question: str | None = Field(default=None, max_length=500)
    requires_confirmation: bool
    confidence: float = Field(ge=0, le=1)

    @field_validator("candidate_tool_keys")
    @classmethod
    def _unique_candidate_tool_keys(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("candidate_tool_keys must be unique")
        return value
