"""Strict Pydantic models for structured LLM outputs (extra='forbid').

These mirror contracts/schemas/*.json and are the implementation source of truth
for validation. A schema-drift test compares emitted JSON Schema to the checked-in
contracts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class VoiceReminder(BaseModel):
    model_config = _STRICT
    channel: Literal["in_app", "email"]
    offset_minutes: int = Field(ge=0, le=525600)


class VoiceTaskV1(BaseModel):
    """voice-task.v1: transcription-to-confirmation-card candidate."""

    # All fields are required (the contract lists them in `required`), but many
    # are nullable so the model can express "unknown" without inventing data.
    model_config = _STRICT
    title: str = Field(min_length=1, max_length=240)
    content_type: Literal["task", "fixed_event", "reminder", "note"]
    description: str | None = Field(max_length=10000)
    local_date: str | None  # date
    local_time: str | None  # time
    timezone: str = Field(min_length=1, max_length=64)
    duration_minutes: int | None = Field(ge=0, le=10080)
    priority: int = Field(ge=0, le=4)
    important: bool
    reminder: VoiceReminder | None
    recurring: bool
    recurrence_rule: str | None = Field(max_length=500)
    original_text: str = Field(min_length=1, max_length=50000)


class VoiceTasksV1(BaseModel):
    """voice-tasks.v1: one transcript decomposed into independent task candidates.

    A single spoken message may contain several action items; each becomes its own
    task candidate. At least one item is expected.
    """

    model_config = _STRICT
    tasks: list[VoiceTaskV1] = Field(min_length=1, max_length=20)


class QuickPlanV1(BaseModel):
    """quick-plan.v1: analysis of a quick-add line into scheduled task candidates.

    The model splits the input into tasks with concrete times/importance, may ask a
    few (bounded) clarifying questions, and explains its plan in one line. Nothing is
    created here — the user reviews, optionally answers, or saves as-is.
    """

    model_config = _STRICT
    tasks: list[VoiceTaskV1] = Field(max_length=20)
    questions: list[str] = Field(max_length=2)
    summary: str = Field(max_length=500)


class CaptureCategory(BaseModel):
    model_config = _STRICT
    name: str = Field(max_length=120)
    confidence: float = Field(ge=0, le=1)


class CaptureTag(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)


class CaptureFact(BaseModel):
    model_config = _STRICT
    field: Literal["brand", "model", "material", "color", "storage_location", "usage_status"]
    value: str | None = Field(default=None, max_length=240)
    confidence: float = Field(ge=0, le=1)
    evidence_summary: str = Field(max_length=300)


class CaptureAnalysisV1(BaseModel):
    """capture-analysis.v1: title/category/tag and uncertain fact suggestions."""

    model_config = _STRICT
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(max_length=4000)
    capture_type: Literal[
        "item",
        "inspiration",
        "note",
        "image",
        "document",
        "link",
        "location",
        "purchase",
        "blog_material",
    ]
    category: CaptureCategory
    # Required by the contract (may be empty lists, but must be present).
    tags: list[CaptureTag] = Field(max_length=12)
    facts: list[CaptureFact] = Field(max_length=20)
    needs_user_input: list[str] = Field(max_length=8)
