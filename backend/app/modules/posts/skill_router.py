"""Blog Skill management endpoints (spec 005, US5, T104).

Skills are structured, versioned AI-behaviour configs. Versions are immutable;
editing a skill appends a new version and advances ``current_version_id``.
Deterministic *defaults* (global / content_class / content_type) decide which
skill an optimization resolves to. Historical runs keep resolving the exact
version they were bound to, so deleting or disabling a skill never rewrites the
past — those guarantees live in ``skill_service`` and are covered by tests.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.posts import skill_service
from app.modules.posts.schemas import (
    SkillCreateBody,
    SkillDefaultBody,
    SkillEnableBody,
    SkillMetaBody,
    SkillVersionBody,
)

skill_router = APIRouter(prefix="/blog/skills", tags=["blog-skills"])


@skill_router.get("")
def list_skills(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    # Lazy safe-seed so a user always has at least one usable skill (T110).
    seeded = skill_service.seed_default_skills(db, user.id)
    if seeded is not None:
        db.commit()
    return [
        skill_service.serialize_skill(db, user.id, s)
        for s in skill_service.list_skills(db, user.id)
    ]


@skill_router.post("", status_code=201)
def create_skill(
    body: SkillCreateBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    skill = skill_service.create_skill(
        db, user.id, name=body.name, description=body.description, config=body.config,
        recommended_model=body.recommended_model, max_content_chars=body.max_content_chars,
        long_content_strategy=body.long_content_strategy,
    )
    db.commit()
    return skill_service.serialize_skill(db, user.id, skill, include_config=True)


# --- Defaults (declared before /{skill_id} so static paths never collide) ---


@skill_router.get("/defaults/list")
def list_defaults(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    from sqlalchemy import select

    from app.models.blog import BlogSkillDefault

    rows = db.scalars(
        select(BlogSkillDefault).where(BlogSkillDefault.user_id == user.id)
    ).all()
    return [
        {
            "scope_type": d.scope_type,
            "scope_key": d.scope_key,
            "skill_id": str(d.skill_id),
        }
        for d in rows
    ]


@skill_router.put("/defaults")
def set_default(
    body: SkillDefaultBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    default = skill_service.set_skill_default(
        db, user.id, body.scope_type, body.scope_key, body.skill_id
    )
    db.commit()
    return {
        "scope_type": default.scope_type,
        "scope_key": default.scope_key,
        "skill_id": str(default.skill_id),
    }


@skill_router.delete("/defaults", status_code=204)
def remove_default(
    scope_type: str,
    scope_key: str,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> None:
    skill_service.remove_skill_default(db, user.id, scope_type, scope_key)
    db.commit()


@skill_router.get("/{skill_id}")
def get_skill(
    skill_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    skill = skill_service.get_skill(db, user.id, skill_id)
    return skill_service.serialize_skill(db, user.id, skill, include_config=True)


@skill_router.patch("/{skill_id}")
def update_skill(
    skill_id: uuid.UUID,
    body: SkillMetaBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    skill = skill_service.update_skill_meta(
        db, user.id, skill_id, name=body.name, description=body.description
    )
    db.commit()
    return skill_service.serialize_skill(db, user.id, skill, include_config=True)


@skill_router.post("/{skill_id}/enabled")
def set_enabled(
    skill_id: uuid.UUID,
    body: SkillEnableBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    skill = skill_service.set_skill_enabled(db, user.id, skill_id, body.enabled)
    db.commit()
    return skill_service.serialize_skill(db, user.id, skill)


@skill_router.delete("/{skill_id}", status_code=204)
def delete_skill(
    skill_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> None:
    skill_service.soft_delete_skill(db, user.id, skill_id)
    db.commit()


@skill_router.post("/{skill_id}/copy", status_code=201)
def copy_skill(
    skill_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    skill = skill_service.copy_skill(db, user.id, skill_id)
    db.commit()
    return skill_service.serialize_skill(db, user.id, skill, include_config=True)


# --- Versions ---


@skill_router.get("/{skill_id}/versions")
def list_versions(
    skill_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        skill_service.serialize_version(v, include_config=True)
        for v in skill_service.list_skill_versions(db, user.id, skill_id)
    ]


@skill_router.post("/{skill_id}/versions", status_code=201)
def add_version(
    skill_id: uuid.UUID,
    body: SkillVersionBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Edit-as-new-version: append an immutable version and make it current."""
    skill = skill_service.get_skill(db, user.id, skill_id)
    version = skill_service.save_skill_version(
        db, user.id, skill, config=body.config, recommended_model=body.recommended_model,
        max_content_chars=body.max_content_chars, long_content_strategy=body.long_content_strategy,
        change_summary=body.change_summary,
    )
    db.commit()
    return skill_service.serialize_version(version, include_config=True)


@skill_router.post("/{skill_id}/versions/{version_id}/restore", status_code=201)
def restore_version(
    skill_id: uuid.UUID,
    version_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    version = skill_service.restore_version(db, user.id, skill_id, version_id)
    db.commit()
    return skill_service.serialize_version(version, include_config=True)


@skill_router.get("/{skill_id}/runs")
def recent_runs(
    skill_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "id": str(r.id),
            "post_id": str(r.post_id),
            "skill_version_id": str(r.skill_version_id),
            "optimization_type": r.optimization_type,
            "outcome": r.outcome,
            "created_at": r.created_at.isoformat(),
        }
        for r in skill_service.recent_runs(db, user.id, skill_id)
    ]
