"""Resolve editable configuration while retaining non-editable policy boundaries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_config import AIConfigBinding, AIConfigProfile, AIPromptVersion, AISkillVersion
from app.modules.ai_config.catalog import get_module


@dataclass(frozen=True)
class ResolvedAIConfig:
    module_key: str
    system_instruction: str
    tool_defaults: dict[str, dict]
    prompt_version_id: uuid.UUID | None
    skill_version_id: uuid.UUID | None


def _profile(
    session: Session, user_id: uuid.UUID, module_key: str, *, create: bool = False
) -> AIConfigProfile | None:
    profile = session.scalar(
        select(AIConfigProfile).where(
            AIConfigProfile.user_id == user_id, AIConfigProfile.module_key == module_key
        )
    )
    if profile is None and create:
        profile = AIConfigProfile(user_id=user_id, module_key=module_key)
        session.add(profile)
        session.flush()
    return profile


def resolve(session: Session, user_id: uuid.UUID, module_key: str) -> ResolvedAIConfig:
    module = get_module(module_key)
    profile = _profile(session, user_id, module_key)
    prompt = (
        session.get(AIPromptVersion, profile.active_prompt_version_id)
        if profile and profile.active_prompt_version_id
        else None
    )
    skill = (
        session.get(AISkillVersion, profile.active_skill_version_id)
        if profile and profile.active_skill_version_id
        else None
    )
    defaults: dict[str, dict] = {
        tool: dict(params) for tool, params in (module.baseline_defaults or {}).items()
    }
    if skill:
        for tool, params in skill.parameter_defaults.items():
            if tool in module.allowed_tool_keys and isinstance(params, dict):
                defaults[tool] = {**defaults.get(tool, {}), **params}
    editable_instruction = prompt.instruction if prompt else module.baseline_instruction
    skill_instruction = (
        f"\n\n当前 Skill：{skill.instruction}" if skill and skill.instruction else ""
    )
    return ResolvedAIConfig(
        module_key,
        f"{module.safety_instruction}\n\n{editable_instruction}{skill_instruction}",
        defaults,
        prompt.id if prompt else None,
        skill.id if skill else None,
    )


def bind(
    session: Session,
    user_id: uuid.UUID,
    module_key: str,
    *,
    model_key: str = "scenario-default",
    run_reference: str | None = None,
) -> ResolvedAIConfig:
    """Resolve once and persist the exact version identities used by an AI call."""

    config = resolve(session, user_id, module_key)
    session.add(
        AIConfigBinding(
            user_id=user_id,
            module_key=module_key,
            prompt_version_id=config.prompt_version_id,
            skill_version_id=config.skill_version_id,
            model_key=model_key[:120],
            run_reference=run_reference[:200] if run_reference else None,
        )
    )
    session.flush()
    return config


def save_prompt(
    session: Session,
    user_id: uuid.UUID,
    module_key: str,
    instruction: str,
    change_summary: str | None = None,
) -> AIPromptVersion:
    if not instruction.strip() or len(instruction) > 12_000:
        raise ValueError("invalid_prompt_instruction")
    get_module(module_key)
    profile = _profile(session, user_id, module_key, create=True)
    if profile is None:  # defensive; create=True always creates it
        raise RuntimeError("AI configuration profile was not created")
    version = (
        int(
            session.scalar(
                select(func.coalesce(func.max(AIPromptVersion.version_number), 0)).where(
                    AIPromptVersion.profile_id == profile.id
                )
            )
            or 0
        )
        + 1
    )
    row = AIPromptVersion(
        profile_id=profile.id,
        version_number=version,
        instruction=instruction.strip(),
        change_summary=change_summary,
    )
    session.add(row)
    session.flush()
    return row


def save_skill(
    session: Session,
    user_id: uuid.UUID,
    module_key: str,
    name: str,
    instruction: str,
    parameter_defaults: dict[str, dict],
) -> AISkillVersion:
    module = get_module(module_key)
    if not name.strip() or len(name) > 120 or len(instruction) > 12_000:
        raise ValueError("invalid_skill")
    if any(
        tool not in module.allowed_tool_keys or not isinstance(params, dict)
        for tool, params in parameter_defaults.items()
    ):
        raise ValueError("invalid_skill_tool_defaults")
    recent_defaults = parameter_defaults.get("posts.list_recent")
    if recent_defaults is not None:
        limit = recent_defaults.get("limit")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("invalid_recent_article_limit")
    profile = _profile(session, user_id, module_key, create=True)
    if profile is None:  # defensive; create=True always creates it
        raise RuntimeError("AI configuration profile was not created")
    version = (
        int(
            session.scalar(
                select(func.coalesce(func.max(AISkillVersion.version_number), 0)).where(
                    AISkillVersion.profile_id == profile.id
                )
            )
            or 0
        )
        + 1
    )
    row = AISkillVersion(
        profile_id=profile.id,
        version_number=version,
        name=name.strip(),
        instruction=instruction.strip(),
        allowed_tool_keys=list(parameter_defaults),
        parameter_defaults=parameter_defaults,
        output_guidance="",
    )
    session.add(row)
    session.flush()
    return row


def activate(
    session: Session,
    user_id: uuid.UUID,
    module_key: str,
    prompt_version_id: uuid.UUID | None,
    skill_version_id: uuid.UUID | None,
) -> AIConfigProfile:
    profile = _profile(session, user_id, module_key, create=True)
    if profile is None:  # defensive; create=True always creates it
        raise RuntimeError("AI configuration profile was not created")
    if prompt_version_id:
        prompt = session.get(AIPromptVersion, prompt_version_id)
        if prompt is None or prompt.profile_id != profile.id:
            raise ValueError("ai_config_version_not_owned")
    if skill_version_id:
        skill = session.get(AISkillVersion, skill_version_id)
        if skill is None or skill.profile_id != profile.id:
            raise ValueError("ai_config_version_not_owned")
    profile.active_prompt_version_id, profile.active_skill_version_id = (
        prompt_version_id,
        skill_version_id,
    )
    return profile
