"""Task request/response schemas mirroring contracts/openapi.yaml."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.tasks import Task

TaskType = Literal["task", "fixed_event", "habit_task", "reminder", "note"]
TaskStatus = Literal["todo", "in_progress", "completed", "cancelled"]
EnergyLevel = Literal["low", "medium", "high"]


class ReminderCreate(BaseModel):
    model_config = {"extra": "forbid"}
    channel: Literal["in_app", "email"]
    trigger_at: datetime | None = None
    offset_minutes: int | None = None
    is_critical: bool = False


class TaskCreate(BaseModel):
    model_config = {"extra": "forbid"}
    type: TaskType = "task"
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    status: TaskStatus = "todo"
    priority: int = Field(default=0, ge=0, le=4)
    importance: int = Field(default=0, ge=0, le=4)
    start_at: datetime | None = None
    due_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=0)
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    is_fixed: bool = False
    is_ai_adjustable: bool = True
    is_splittable: bool = False
    energy_level: EnergyLevel | None = None
    recurrence_rule: str | None = None
    reminders: list[ReminderCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fixed_not_ai(self) -> TaskCreate:
        if self.is_fixed:
            self.is_ai_adjustable = False
        if self.due_at and self.start_at and self.due_at < self.start_at:
            raise ValueError("due_at must be >= start_at")
        return self


class TaskPatch(BaseModel):
    model_config = {"extra": "forbid"}
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=0, le=4)
    importance: int | None = Field(default=None, ge=0, le=4)
    start_at: datetime | None = None
    due_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=0)
    actual_minutes: int | None = Field(default=None, ge=0)
    is_fixed: bool | None = None
    is_ai_adjustable: bool | None = None
    is_splittable: bool | None = None
    energy_level: EnergyLevel | None = None
    tag_ids: list[uuid.UUID] | None = None


class TaskComplete(BaseModel):
    model_config = {"extra": "forbid"}
    version: int
    actual_minutes: int | None = Field(default=None, ge=0)


class TaskOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    description: str | None = None
    status: str
    priority: int
    importance: int
    start_at: datetime | None = None
    due_at: datetime | None = None
    estimated_minutes: int | None = None
    actual_minutes: int | None = None
    category_id: uuid.UUID | None = None
    is_fixed: bool
    is_ai_adjustable: bool
    is_splittable: bool
    energy_level: str | None = None
    recurrence_rule: str | None = None
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    version: int
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, task: Task, tag_ids: list[uuid.UUID] | None = None) -> TaskOut:
        data = {
            c: getattr(task, c)
            for c in (
                "id",
                "type",
                "title",
                "description",
                "status",
                "priority",
                "importance",
                "start_at",
                "due_at",
                "estimated_minutes",
                "actual_minutes",
                "category_id",
                "is_fixed",
                "is_ai_adjustable",
                "is_splittable",
                "energy_level",
                "recurrence_rule",
                "source_type",
                "source_id",
                "version",
                "completed_at",
                "created_at",
                "updated_at",
            )
        }
        return cls(**data, tag_ids=tag_ids or [])


class TaskPage(BaseModel):
    items: list[TaskOut]
    next_cursor: str | None = None
