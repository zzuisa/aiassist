from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.errors import ValidationError
from app.db.session import get_db
from app.models.ai_config import AIConfigBinding, AIConfigProfile, AIPromptVersion, AISkillVersion
from app.modules.ai_config import service
from app.modules.ai_config.catalog import MODULES, get_module
from app.modules.ai_config.schemas import (
    Activation,
    DryRunRequest,
    PromptVersionCreate,
    SkillVersionCreate,
)

router = APIRouter(prefix="/ai-config/modules", tags=["ai-config"])


def _version(row: AIPromptVersion | AISkillVersion) -> dict:
    return {
        "id": str(row.id),
        "version_number": row.version_number,
        "instruction": row.instruction,
        "created_at": row.created_at,
    }


@router.get("")
def list_modules(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    profiles = {
        p.module_key: p
        for p in db.scalars(select(AIConfigProfile).where(AIConfigProfile.user_id == user.id)).all()
    }
    return [
        {
            "key": item.key,
            "title": item.title,
            "allowed_tool_keys": list(item.allowed_tool_keys),
            "active_prompt_version_id": str(profiles[item.key].active_prompt_version_id)
            if profiles.get(item.key) and profiles[item.key].active_prompt_version_id
            else None,
            "active_skill_version_id": str(profiles[item.key].active_skill_version_id)
            if profiles.get(item.key) and profiles[item.key].active_skill_version_id
            else None,
            "safety_boundary": item.safety_instruction,
        }
        for item in MODULES.values()
    ]


@router.get("/bindings/recent")
def list_recent_bindings(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    rows = db.scalars(
        select(AIConfigBinding)
        .where(AIConfigBinding.user_id == user.id)
        .order_by(AIConfigBinding.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": str(row.id),
            "module_key": row.module_key,
            "prompt_version_id": str(row.prompt_version_id) if row.prompt_version_id else None,
            "skill_version_id": str(row.skill_version_id) if row.skill_version_id else None,
            "model_key": row.model_key,
            "run_reference": row.run_reference,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/{module_key}")
def get_module_config(
    module_key: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        module = get_module(module_key)
    except ValueError as exc:
        raise ValidationError("Unknown AI module", code="ai_module_unknown") from exc
    profile = db.scalar(
        select(AIConfigProfile).where(
            AIConfigProfile.user_id == user.id, AIConfigProfile.module_key == module_key
        )
    )
    prompts = (
        db.scalars(
            select(AIPromptVersion)
            .where(AIPromptVersion.profile_id == profile.id)
            .order_by(AIPromptVersion.version_number.desc())
        ).all()
        if profile
        else []
    )
    skills = (
        db.scalars(
            select(AISkillVersion)
            .where(AISkillVersion.profile_id == profile.id)
            .order_by(AISkillVersion.version_number.desc())
        ).all()
        if profile
        else []
    )
    return {
        "key": module.key,
        "title": module.title,
        "baseline_instruction": module.baseline_instruction,
        "allowed_tool_keys": list(module.allowed_tool_keys),
        "safety_boundary": module.safety_instruction,
        "active_prompt_version_id": str(profile.active_prompt_version_id)
        if profile and profile.active_prompt_version_id
        else None,
        "active_skill_version_id": str(profile.active_skill_version_id)
        if profile and profile.active_skill_version_id
        else None,
        "prompt_versions": [_version(row) for row in prompts],
        "skill_versions": [
            {
                **_version(row),
                "name": row.name,
                "parameter_defaults": row.parameter_defaults,
                "allowed_tool_keys": row.allowed_tool_keys,
            }
            for row in skills
        ],
    }


@router.post("/{module_key}/prompt-versions", status_code=201)
def create_prompt(
    module_key: str,
    body: PromptVersionCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = service.save_prompt(db, user.id, module_key, body.instruction, body.change_summary)
    except ValueError as exc:
        raise ValidationError("Invalid Prompt configuration", code=str(exc)) from exc
    db.commit()
    return _version(row)


@router.post("/{module_key}/skill-versions", status_code=201)
def create_skill(
    module_key: str,
    body: SkillVersionCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = service.save_skill(
            db, user.id, module_key, body.name, body.instruction, body.parameter_defaults
        )
    except ValueError as exc:
        raise ValidationError("Invalid Skill configuration", code=str(exc)) from exc
    db.commit()
    return {**_version(row), "name": row.name, "parameter_defaults": row.parameter_defaults}


@router.post("/{module_key}/activate")
def activate(
    module_key: str,
    body: Activation,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    try:
        profile = service.activate(
            db, user.id, module_key, body.prompt_version_id, body.skill_version_id
        )
    except ValueError as exc:
        raise ValidationError("Invalid configuration activation", code=str(exc)) from exc
    db.commit()
    return {
        "module_key": profile.module_key,
        "active_prompt_version_id": str(profile.active_prompt_version_id)
        if profile.active_prompt_version_id
        else None,
        "active_skill_version_id": str(profile.active_skill_version_id)
        if profile.active_skill_version_id
        else None,
    }


@router.post("/{module_key}/dry-run")
def dry_run(
    module_key: str,
    body: DryRunRequest,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Run a read-only configuration trial; never invokes a business tool."""

    if module_key != "conversation_route":
        config = service.bind(db, user.id, module_key, run_reference="dry-run")
        db.commit()
        return {
            "module_key": module_key,
            "status": "configuration_resolved",
            "prompt_version_id": str(config.prompt_version_id)
            if config.prompt_version_id
            else None,
            "skill_version_id": str(config.skill_version_id) if config.skill_version_id else None,
            "tool_call": None,
            "message": "该模块配置解析成功；试运行未执行业务写入。",
        }

    from app.modules.agent.conversation_router import route_message

    outcome = route_message(
        body.input_text,
        session=db,
        user_id=user.id,
        run_reference="dry-run",
    )
    db.commit()
    return {
        "module_key": module_key,
        "status": "routed",
        "route_kind": outcome.route.route_kind,
        "selected_tool": outcome.selected_tool,
        "tool_call": outcome.route.tool_call.model_dump(mode="json")
        if outcome.route.tool_call
        else None,
        "arguments": outcome.route.semantic_arguments,
        "validation_errors": list(outcome.validation_errors),
        "message": "试运行只生成并校验路由，不会执行工具或修改业务数据。",
    }
