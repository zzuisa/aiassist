"""Skill service: version validation, deterministic scope resolution (T022).

Resolution order (first match wins):
  1. manual      — caller specifies skill_id directly
  2. content_type — BlogSkillDefault where scope_type='content_type' and scope_key=str(content_type_id)
  3. content_class — BlogSkillDefault where scope_type='content_class' and scope_key=content_class
  4. global       — BlogSkillDefault where scope_type='global' and scope_key='*'

At each step the skill must be enabled (not deleted) and the resolved version
must be complete (config_json is not empty).  Resolution always returns the
*current_version* of the skill, not a user-pinned version.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pydantic import ValidationError as PydanticValidationError

from app.core.errors import NotFoundError, ValidationError
from app.models.blog import BlogSkill, BlogSkillDefault, BlogSkillVersion
from app.services.llm.schemas import BlogSkillConfigV1

# ---------------------------------------------------------------------------
# Version validation
# ---------------------------------------------------------------------------

_VALID_STRATEGIES = frozenset({"reject", "chunk", "summarize_then_process"})


def validate_skill_version_config(config: dict[str, Any]) -> list[str]:
    """Return a list of validation errors for a skill version config dict.

    Empty list = valid.  The config_json schema is blog-skill-config.v1, validated
    against the strict :class:`BlogSkillConfigV1` model.
    """
    try:
        BlogSkillConfigV1.model_validate(config)
    except PydanticValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        ]
    return []


def is_version_complete(version: BlogSkillVersion) -> bool:
    """True if the version has a non-empty, valid config_json."""
    config = version.config_json or {}
    if not config:
        return False
    return not validate_skill_version_config(config)


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def get_skill(
    session: Session, user_id: uuid.UUID, skill_id: uuid.UUID, *, include_deleted: bool = False
) -> BlogSkill:
    skill = session.get(BlogSkill, skill_id)
    if skill is None or skill.user_id != user_id:
        raise NotFoundError("Skill not found")
    if not include_deleted and skill.deleted_at is not None:
        raise NotFoundError("Skill not found")
    return skill


def get_skill_version(
    session: Session, user_id: uuid.UUID, version_id: uuid.UUID
) -> BlogSkillVersion:
    v = session.get(BlogSkillVersion, version_id)
    if v is None or v.user_id != user_id:
        raise NotFoundError("Skill version not found")
    return v


def current_skill_version(
    session: Session, user_id: uuid.UUID, skill: BlogSkill
) -> BlogSkillVersion | None:
    if not skill.current_version_id:
        return None
    v = session.get(BlogSkillVersion, skill.current_version_id)
    if v is None or v.user_id != user_id:
        return None
    return v


def save_skill_version(
    session: Session,
    user_id: uuid.UUID,
    skill: BlogSkill,
    *,
    config: dict[str, Any],
    recommended_model: str | None = None,
    max_content_chars: int = 200_000,
    long_content_strategy: str = "reject",
    change_summary: str | None = None,
) -> BlogSkillVersion:
    """Append a new immutable version; advance skill.current_version_id."""
    if long_content_strategy not in _VALID_STRATEGIES:
        raise ValidationError(
            f"long_content_strategy must be one of {sorted(_VALID_STRATEGIES)}",
            code="invalid_strategy",
        )
    errors = validate_skill_version_config(config)
    if errors:
        raise ValidationError(f"Invalid skill config: {'; '.join(errors)}", code="invalid_config")

    # Determine next version_number
    max_ver = session.scalar(
        select(BlogSkillVersion.version_number)
        .where(BlogSkillVersion.skill_id == skill.id)
        .order_by(BlogSkillVersion.version_number.desc())
        .limit(1)
    )
    next_number = (max_ver or 0) + 1

    version = BlogSkillVersion(
        id=uuid.uuid4(),
        user_id=user_id,
        skill_id=skill.id,
        version_number=next_number,
        config_json=config,
        schema_version="blog-skill-config.v1",
        recommended_model=recommended_model,
        max_content_chars=max_content_chars,
        long_content_strategy=long_content_strategy,
        change_summary=change_summary,
    )
    session.add(version)
    session.flush()
    skill.current_version_id = version.id
    return version


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def _resolve_default(
    session: Session,
    user_id: uuid.UUID,
    scope_type: str,
    scope_key: str,
) -> tuple[BlogSkill, BlogSkillVersion] | None:
    default = session.scalar(
        select(BlogSkillDefault).where(
            BlogSkillDefault.user_id == user_id,
            BlogSkillDefault.scope_type == scope_type,
            BlogSkillDefault.scope_key == scope_key,
        )
    )
    if default is None:
        return None
    skill = session.get(BlogSkill, default.skill_id)
    if skill is None or skill.deleted_at is not None or not skill.enabled:
        return None
    version = current_skill_version(session, user_id, skill)
    if version is None or not is_version_complete(version):
        return None
    return skill, version


def resolve_skill(
    session: Session,
    user_id: uuid.UUID,
    *,
    manual_skill_id: uuid.UUID | None = None,
    content_type_id: uuid.UUID | None = None,
    content_class: str | None = None,
) -> tuple[BlogSkill, BlogSkillVersion]:
    """Return the skill+version to use for a given post context.

    Resolution order: manual → content_type → content_class → global.
    Raises NotFoundError if no applicable skill is found.
    """
    # 1. Manual override
    if manual_skill_id:
        skill = session.get(BlogSkill, manual_skill_id)
        if skill and skill.user_id == user_id and skill.enabled and skill.deleted_at is None:
            version = current_skill_version(session, user_id, skill)
            if version and is_version_complete(version):
                return skill, version

    # 2. Content-type default
    if content_type_id:
        result = _resolve_default(session, user_id, "content_type", str(content_type_id))
        if result:
            return result

    # 3. Content-class default
    if content_class:
        result = _resolve_default(session, user_id, "content_class", content_class)
        if result:
            return result

    # 4. Global default
    result = _resolve_default(session, user_id, "global", "*")
    if result:
        return result

    raise NotFoundError(
        "No applicable skill found. Create a skill and set it as the global default.",
        code="no_skill",
    )


# ---------------------------------------------------------------------------
# Default management
# ---------------------------------------------------------------------------


def set_skill_default(
    session: Session,
    user_id: uuid.UUID,
    scope_type: str,
    scope_key: str,
    skill_id: uuid.UUID,
) -> BlogSkillDefault:
    """Upsert a scope default for a skill.  Validates scope_type and that the skill exists."""
    if scope_type not in ("global", "content_class", "content_type"):
        raise ValidationError(
            "scope_type must be one of: global, content_class, content_type",
            code="invalid_scope",
        )
    # Ensure skill is owned and active
    get_skill(session, user_id, skill_id)

    existing = session.scalar(
        select(BlogSkillDefault).where(
            BlogSkillDefault.user_id == user_id,
            BlogSkillDefault.scope_type == scope_type,
            BlogSkillDefault.scope_key == scope_key,
        )
    )
    if existing:
        existing.skill_id = skill_id
        return existing

    default = BlogSkillDefault(
        id=uuid.uuid4(),
        user_id=user_id,
        scope_type=scope_type,
        scope_key=scope_key,
        skill_id=skill_id,
    )
    session.add(default)
    session.flush()
    return default


def remove_skill_default(
    session: Session, user_id: uuid.UUID, scope_type: str, scope_key: str
) -> bool:
    """Delete a scope default if it exists.  Returns True if deleted."""
    default = session.scalar(
        select(BlogSkillDefault).where(
            BlogSkillDefault.user_id == user_id,
            BlogSkillDefault.scope_type == scope_type,
            BlogSkillDefault.scope_key == scope_key,
        )
    )
    if default is None:
        return False
    session.delete(default)
    return True
