"""Strict AI proposal and public view schemas for collaborative Agent plans."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanOperation(StrEnum):
    query = "query"
    analyze = "analyze"
    create = "create"
    update = "update"
    delete = "delete"
    publish = "publish"
    rollback = "rollback"
    external_effect = "external_effect"


class PlanInputSource(StrEnum):
    current_message = "current_message"
    conversation_context = "conversation_context"
    dependency = "dependency"


class PlanStepProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_key: str = Field(pattern=r"^step_[a-z0-9_]{1,48}$", max_length=64)
    title: str = Field(min_length=1, max_length=120)
    responsibility: str = Field(min_length=1, max_length=300)
    tool_name: str = Field(min_length=1, max_length=160)
    operation_type: PlanOperation
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=11)
    input_source: PlanInputSource
    expected_output: str = Field(min_length=1, max_length=300)
    requires_confirmation: bool

    @field_validator("depends_on")
    @classmethod
    def unique_dependencies(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("depends_on must be unique")
        return value


class AgentTaskPlanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-task-plan.v1"] = "agent-task-plan.v1"
    objective: str = Field(min_length=1, max_length=500)
    steps: list[PlanStepProposal] = Field(min_length=1, max_length=12)

    @field_validator("steps")
    @classmethod
    def unique_step_keys(cls, value: list[PlanStepProposal]) -> list[PlanStepProposal]:
        keys = [item.step_key for item in value]
        if len(set(keys)) != len(keys):
            raise ValueError("step_key must be unique")
        return value


class PlanProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: int = Field(ge=0)
    total: int = Field(ge=0)
    stage_label: str | None = None


class PlanAgentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str


class PlanErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    retryable: bool = False


class PlanStepView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: uuid.UUID
    step_key: str
    position: int
    title: str
    responsibility: str
    agent: PlanAgentView
    tool_name: str
    operation_type: str
    depends_on: list[str]
    status: str
    progress: PlanProgress | None = None
    attempt_count: int
    stage_label: str | None = None
    result_summary: str | None = None
    error: PlanErrorView | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class PlanCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    completed: int
    failed: int
    skipped: int


class AgentPlanView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["agent-plan-view.v1"] = "agent-plan-view.v1"
    plan_id: uuid.UUID
    turn_id: uuid.UUID | None = None
    task_id: uuid.UUID
    user_message_id: uuid.UUID | None = None
    objective: str
    status: str
    runtime_state: Literal["checkpointed", "running", "interrupted", "completed", "failed"]
    graph_run_id: str | None = None
    version: int
    counts: PlanCounts
    elapsed_ms: int | None = None
    result_summary: str | None = None
    error: PlanErrorView | None = None
    steps: list[PlanStepView]
    created_at: datetime
    finished_at: datetime | None = None


class PlanRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["failed_chain"] = "failed_chain"
