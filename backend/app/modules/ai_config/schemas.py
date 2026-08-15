from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=1, max_length=12_000)
    change_summary: str | None = Field(default=None, max_length=500)


class SkillVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    instruction: str = Field(default="", max_length=12_000)
    parameter_defaults: dict[str, dict] = Field(default_factory=dict)


class Activation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_version_id: uuid.UUID | None = None
    skill_version_id: uuid.UUID | None = None


class DryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_text: str = Field(min_length=1, max_length=4_000)
