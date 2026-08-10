"""Skill service: version validation, deterministic scope resolution (T022).

Resolution order (first match wins):
  1. manual      — caller specifies skill_id directly
  2. content_type — BlogSkillDefault where scope_type='content_type' and
     scope_key=str(content_type_id)
  3. content_class — BlogSkillDefault where scope_type='content_class' and scope_key=content_class
  4. global       — BlogSkillDefault where scope_type='global' and scope_key='*'

At each step the skill must be enabled (not deleted) and the resolved version
must be complete (config_json is not empty).  Resolution always returns the
*current_version* of the skill, not a user-pinned version.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.blog import (
    BlogSkill,
    BlogSkillDefault,
    BlogSkillVersion,
    PostAIRun,
)
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
        return [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
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


# ---------------------------------------------------------------------------
# Skill CRUD, versions, copy, restore, recent runs (spec 005, US5, T102)
# ---------------------------------------------------------------------------


def list_skills(session: Session, user_id: uuid.UUID) -> list[BlogSkill]:
    return list(
        session.scalars(
            select(BlogSkill)
            .where(BlogSkill.user_id == user_id, BlogSkill.deleted_at.is_(None))
            .order_by(BlogSkill.created_at.desc())
        ).all()
    )


def create_skill(
    session: Session,
    user_id: uuid.UUID,
    *,
    name: str,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    recommended_model: str | None = None,
    max_content_chars: int = 200_000,
    long_content_strategy: str = "reject",
) -> BlogSkill:
    """Create a skill; when *config* is given, add its first immutable version."""
    if not name or not name.strip():
        raise ValidationError("Skill name is required", code="invalid_name")
    skill = BlogSkill(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name.strip(),
        description=description,
        enabled=True,
    )
    session.add(skill)
    session.flush()
    if config is not None:
        save_skill_version(
            session,
            user_id,
            skill,
            config=config,
            recommended_model=recommended_model,
            max_content_chars=max_content_chars,
            long_content_strategy=long_content_strategy,
            change_summary="初始版本",
        )
    return skill


def update_skill_meta(
    session: Session,
    user_id: uuid.UUID,
    skill_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
) -> BlogSkill:
    skill = get_skill(session, user_id, skill_id)
    if name is not None:
        if not name.strip():
            raise ValidationError("Skill name is required", code="invalid_name")
        skill.name = name.strip()
    if description is not None:
        skill.description = description
    return skill


def set_skill_enabled(
    session: Session, user_id: uuid.UUID, skill_id: uuid.UUID, enabled: bool
) -> BlogSkill:
    skill = get_skill(session, user_id, skill_id)
    skill.enabled = enabled
    return skill


def soft_delete_skill(session: Session, user_id: uuid.UUID, skill_id: uuid.UUID) -> None:
    """Soft-delete a skill and drop any defaults that pointed at it."""
    skill = get_skill(session, user_id, skill_id)
    skill.deleted_at = datetime.now(UTC)
    skill.enabled = False
    for d in session.scalars(
        select(BlogSkillDefault).where(
            BlogSkillDefault.user_id == user_id, BlogSkillDefault.skill_id == skill_id
        )
    ).all():
        session.delete(d)


def copy_skill(session: Session, user_id: uuid.UUID, skill_id: uuid.UUID) -> BlogSkill:
    """Fork a skill: new skill carrying a copy of the source's current config."""
    src = get_skill(session, user_id, skill_id)
    version = current_skill_version(session, user_id, src)
    config = dict(version.config_json) if version else None
    return create_skill(
        session,
        user_id,
        name=f"{src.name}（副本）",
        description=src.description,
        config=config,
        recommended_model=version.recommended_model if version else None,
        max_content_chars=version.max_content_chars if version else 200_000,
        long_content_strategy=version.long_content_strategy if version else "reject",
    )


def restore_version(
    session: Session, user_id: uuid.UUID, skill_id: uuid.UUID, version_id: uuid.UUID
) -> BlogSkillVersion:
    """Restore an old version by appending it as a NEW current version (immutable)."""
    skill = get_skill(session, user_id, skill_id)
    target = get_skill_version(session, user_id, version_id)
    if target.skill_id != skill.id:
        raise ValidationError("Version does not belong to skill", code="version_mismatch")
    return save_skill_version(
        session,
        user_id,
        skill,
        config=dict(target.config_json),
        recommended_model=target.recommended_model,
        max_content_chars=target.max_content_chars,
        long_content_strategy=target.long_content_strategy,
        change_summary=f"从 v{target.version_number} 恢复",
    )


def list_skill_versions(
    session: Session, user_id: uuid.UUID, skill_id: uuid.UUID
) -> list[BlogSkillVersion]:
    get_skill(session, user_id, skill_id, include_deleted=True)
    return list(
        session.scalars(
            select(BlogSkillVersion)
            .where(
                BlogSkillVersion.skill_id == skill_id,
                BlogSkillVersion.user_id == user_id,
            )
            .order_by(BlogSkillVersion.version_number.desc())
        ).all()
    )


def recent_runs(
    session: Session, user_id: uuid.UUID, skill_id: uuid.UUID, limit: int = 20
) -> list[PostAIRun]:
    """Recent AI runs bound to any version of this skill (reproducibility view)."""
    version_ids = [v.id for v in list_skill_versions(session, user_id, skill_id)]
    if not version_ids:
        return []
    return list(
        session.scalars(
            select(PostAIRun)
            .where(
                PostAIRun.user_id == user_id,
                PostAIRun.skill_version_id.in_(version_ids),
            )
            .order_by(PostAIRun.created_at.desc())
            .limit(limit)
        ).all()
    )


def impacted_scopes(
    session: Session, user_id: uuid.UUID, skill_id: uuid.UUID
) -> list[dict[str, str]]:
    """Scopes whose default currently resolves to this skill (change/disable impact)."""
    defaults = session.scalars(
        select(BlogSkillDefault).where(
            BlogSkillDefault.user_id == user_id, BlogSkillDefault.skill_id == skill_id
        )
    ).all()
    return [{"scope_type": d.scope_type, "scope_key": d.scope_key} for d in defaults]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_version(v: BlogSkillVersion, *, include_config: bool = False) -> dict[str, Any]:
    out = {
        "id": str(v.id),
        "skill_id": str(v.skill_id),
        "version_number": v.version_number,
        "schema_version": v.schema_version,
        "recommended_model": v.recommended_model,
        "max_content_chars": v.max_content_chars,
        "long_content_strategy": v.long_content_strategy,
        "change_summary": v.change_summary,
        "created_at": v.created_at.isoformat(),
    }
    if include_config:
        out["config"] = v.config_json
    return out


def serialize_skill(
    session: Session, user_id: uuid.UUID, skill: BlogSkill, *, include_config: bool = False
) -> dict[str, Any]:
    version = current_skill_version(session, user_id, skill)
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "enabled": skill.enabled,
        "current_version": serialize_version(version, include_config=include_config)
        if version
        else None,
        "current_version_complete": bool(version and is_version_complete(version)),
        "default_scopes": impacted_scopes(session, user_id, skill.id),
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Safe default seeding (spec 005, US5, T110)
# ---------------------------------------------------------------------------

_SEED_SKILL_CONFIG: dict[str, Any] = {
    "schema_version": "blog-skill-config.v1",
    "applicable_content_classes": ["essay", "technical", "life", "bookmark", "quick"],
    "applicable_content_type_ids": [],
    "processing_goal": "在不改变原意的前提下提升表达清晰度与结构",
    "content_rules": ["保留原文事实与代码", "不虚构不存在的信息"],
    "title_rules": ["标题简洁准确"],
    "summary_rules": ["用一到两句概括要点"],
    "body_structure": ["合理分段", "必要时加入小标题"],
    "taxonomy_rules": [],
    "keyword_rules": [],
    "prohibitions": ["禁止编造事实", "禁止删除代码块或命令"],
    "field_policies": {
        "title": "suggest_only",
        "summary": "fill_if_empty",
        "markdown": "require_confirmation",
    },
    "output_fields": ["title", "summary", "markdown"],
    "output_schema": "blog-optimization.v1",
    "validation_rules": ["不得改动受保护的代码/命令/数字"],
    "recommended_model": None,
    "max_content_chars": 200_000,
    "long_content_strategy": "reject",
}


def seed_default_skills(session: Session, user_id: uuid.UUID) -> BlogSkill | None:
    """Idempotently give a user one safe global Skill if they have none.

    Never replaces or edits user-defined skills: it only acts when the user has
    no skills at all, and only sets the global default when none exists.
    """
    has_any = session.scalar(
        select(BlogSkill.id)
        .where(BlogSkill.user_id == user_id, BlogSkill.deleted_at.is_(None))
        .limit(1)
    )
    if has_any:
        return None
    skill = create_skill(
        session,
        user_id,
        name="默认优化",
        description="安全的通用优化技能（可复制后自定义）",
        config=dict(_SEED_SKILL_CONFIG),
    )
    existing_global = session.scalar(
        select(BlogSkillDefault).where(
            BlogSkillDefault.user_id == user_id,
            BlogSkillDefault.scope_type == "global",
            BlogSkillDefault.scope_key == "*",
        )
    )
    if existing_global is None:
        set_skill_default(session, user_id, "global", "*", skill.id)
    return skill
