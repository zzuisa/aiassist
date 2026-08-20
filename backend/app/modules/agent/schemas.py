"""Versioned API schemas for Agent tasks, runs, records, and tools."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_confirmation = "waiting_confirmation"
    success = "success"
    partial_success = "partial_success"
    failed = "failed"


class AgentRunStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_confirmation = "waiting_confirmation"
    success = "success"
    partial_success = "partial_success"
    failed = "failed"
    skipped = "skipped"


class OperationType(StrEnum):
    query = "query"
    analyze = "analyze"
    create = "create"
    update = "update"
    delete = "delete"
    publish = "publish"
    rollback = "rollback"


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: int = Field(ge=0)
    total: int = Field(ge=0)
    stage_label: str | None = Field(default=None, max_length=120)


class AgentTask(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    task_id: uuid.UUID = Field(validation_alias="id")
    job_id: uuid.UUID
    request_text: str
    intent_key: str
    status: TaskStatus
    result_summary: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class AgentRun(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    agent_id: uuid.UUID = Field(validation_alias="id")
    parent_agent_id: uuid.UUID | None = Field(default=None, validation_alias="parent_run_id")
    agent_key: str
    agent_version: str
    agent_name: str
    responsibility: str
    current_task: str
    status: AgentRunStatus
    current_tool: str | None = None
    allow_write: bool = False
    progress: Progress | None = None
    result_summary: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentTaskDetail(AgentTask):
    runs: list[AgentRun] = Field(default_factory=list)


class ExecutionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    step_id: str
    agent_id: uuid.UUID | None = Field(default=None, validation_alias="run_id")
    agent_name: str
    step_label: str
    tool_name: str
    operation_type: OperationType
    params_digest: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="params_digest_json",
    )
    result_summary: str | None = None
    status: Literal["success", "failed", "skipped"]
    error_reason: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None


class PendingWriteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    version: int | None = None


class PendingWrite(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)

    confirmation_id: uuid.UUID = Field(validation_alias="id")
    operation_type: OperationType
    target_type: str
    targets: list[PendingWriteTarget] = Field(validation_alias="targets_json")
    preview: dict[str, Any] = Field(validation_alias="preview_json")
    affected_count: int = Field(ge=0)
    reversible: bool
    high_risk: bool
    decision: Literal["pending", "approved", "rejected", "expired"]
    decided_at: datetime | None = None
    created_at: datetime


class ConfirmationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]


class ToolManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    type: Literal["read", "write"]
    responsibility: str = Field(min_length=1, max_length=500)
    required_permission: str | None = Field(default=None, max_length=120)
    available: bool
    unavailable_reason: str | None = Field(default=None, max_length=500)
    source: Literal["internal_api", "mcp"] = "internal_api"


class ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-tool-manifest.v1"] = "agent-tool-manifest.v1"
    tools: list[ToolManifestEntry] = Field(max_length=200)


class AgentTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_text: str = Field(min_length=1, max_length=4000)
    previous_task_id: uuid.UUID | None = None


class ContentAnalysisResult(BaseModel):
    """Strict provider output for one owned article analysis."""

    model_config = ConfigDict(extra="forbid")

    post_id: str
    tags: list[str] = Field(default_factory=list, max_length=30)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    summary: str = Field(max_length=2000)


class AgentTaskReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task-report.v1"] = "task-report.v1"
    report_id: uuid.UUID
    plan_id: uuid.UUID
    revision: int = Field(ge=1)
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    objective: str
    executed_steps: list[dict[str, Any]]
    totals: dict[str, int]
    verified_changes: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    unprocessed: list[dict[str, Any]]
    next_actions: list[str]
    results: list[dict[str, Any]] = Field(default_factory=list)
    markdown: str
    report_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    generation_method: Literal["deterministic", "llm_enhanced"]
    generated_at: datetime
