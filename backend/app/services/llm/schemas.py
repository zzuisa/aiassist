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


# ---------------------------------------------------------------------------
# Blog content-management (spec 005, T023)
# ---------------------------------------------------------------------------

_CONTENT_CLASS_LITERAL = Literal[
    "technical",
    "project",
    "learning",
    "life",
    "travel",
    "diary",
    "essay",
    "bookmark",
    "media",
    "item",
    "quick",
]


class BlogSuggestion(BaseModel):
    """A scored suggestion (category / tag / keyword)."""

    model_config = _STRICT
    name: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=300)


class BlogStructuredField(BaseModel):
    model_config = _STRICT
    value: str | float | int | bool | list[str | float | int | bool] | None
    confidence: float = Field(ge=0, le=1)
    evidence_summary: str = Field(max_length=500)


class BlogRelatedPostSuggestion(BaseModel):
    model_config = _STRICT
    post_id: str = Field(description="uuid")
    reason: str = Field(max_length=300)


class BlogClaim(BaseModel):
    model_config = _STRICT
    statement: str = Field(max_length=500)
    support: Literal["source", "user_text", "inference", "unknown"]
    evidence_summary: str = Field(max_length=500)


class BlogWarning(BaseModel):
    model_config = _STRICT
    code: Literal[
        "possible_new_fact",
        "protected_token_changed",
        "privacy_risk",
        "missing_required_field",
        "truncated_input",
        "uncertain_classification",
        "source_attribution_required",
        "other",
    ]
    field: str | None = Field(max_length=128)
    message: str = Field(max_length=500)
    severity: Literal["info", "warning", "blocking"]


class BlogOptimizationV1(BaseModel):
    """blog-optimization.v1: full AI optimization candidate for a post.

    Every field is required (mirrors the contract ``required`` set); nullable
    fields express "unknown" without inventing data.
    """

    model_config = _STRICT
    schema_version: Literal["blog-optimization.v1"]
    title: str | None = Field(max_length=240)
    subtitle: str | None = Field(max_length=240)
    summary: str | None = Field(max_length=2000)
    markdown: str | None = Field(max_length=200_000)
    content_class_suggestion: _CONTENT_CLASS_LITERAL | None
    content_type_suggestion: str | None = Field(max_length=120)
    category_suggestions: list[BlogSuggestion] = Field(max_length=5)
    tag_suggestions: list[BlogSuggestion] = Field(max_length=20)
    keyword_suggestions: list[BlogSuggestion] = Field(max_length=30)
    occurred_at: str | None
    location: str | None = Field(max_length=240)
    project: str | None = Field(max_length=240)
    source_summary: str | None = Field(max_length=2000)
    structured_fields: dict[str, BlogStructuredField] = Field(max_length=100)
    related_post_suggestions: list[BlogRelatedPostSuggestion] = Field(max_length=10)
    claims: list[BlogClaim] = Field(max_length=100)
    warnings: list[BlogWarning] = Field(max_length=100)


class BlogBodyOptimizationV1(BaseModel):
    """Lean response for body-only rewriting.

    Requiring the full metadata schema for a language-only body pass caused
    long-form model responses to omit unrelated nullable/list fields and fail
    validation. This contract asks only for the artifact the operation needs.
    """

    model_config = _STRICT
    schema_version: Literal["blog-body-optimization.v1"]
    markdown: str = Field(min_length=1, max_length=200_000)


class BlogSkillConfigV1(BaseModel):
    """blog-skill-config.v1: the persisted configuration of a skill version."""

    model_config = _STRICT
    schema_version: Literal["blog-skill-config.v1"]
    applicable_content_classes: list[_CONTENT_CLASS_LITERAL] = Field(min_length=1)
    applicable_content_type_ids: list[str] = Field(max_length=100)
    processing_goal: str = Field(min_length=1, max_length=4000)
    content_rules: list[str] = Field(max_length=100)
    title_rules: list[str] = Field(max_length=100)
    summary_rules: list[str] = Field(max_length=100)
    body_structure: list[str] = Field(max_length=100)
    taxonomy_rules: list[str] = Field(max_length=100)
    keyword_rules: list[str] = Field(max_length=100)
    prohibitions: list[str] = Field(min_length=1, max_length=100)
    field_policies: dict[
        str,
        Literal[
            "forbid",
            "suggest_only",
            "require_confirmation",
            "fill_if_empty",
            "auto_fill",
            "allow_overwrite",
            "keep_both_on_conflict",
        ],
    ] = Field(max_length=200)
    output_fields: list[str] = Field(min_length=1, max_length=200)
    output_schema: Literal["blog-optimization.v1"]
    validation_rules: list[str] = Field(max_length=100)
    recommended_model: str | None = Field(max_length=120)
    max_content_chars: int = Field(ge=1000, le=200_000)
    long_content_strategy: Literal["reject", "chunk", "summarize_then_process"]
