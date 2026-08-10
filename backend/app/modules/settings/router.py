"""Settings endpoints: get/patch settings, change password."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.posts import settings_service as blog_settings_service
from app.modules.settings import service
from app.modules.tasks import plan_service

router = APIRouter(prefix="/settings", tags=["settings"])


class NotificationPreferences(BaseModel):
    model_config = {"extra": "forbid"}
    in_app_enabled: bool = True
    email_enabled: bool = False
    critical_email_enabled: bool = True
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class AIOptimizationPreferences(BaseModel):
    model_config = {"extra": "forbid"}
    default_provider: Literal["radio", "aiassist"] = "radio"


class SettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    locale: str | None = Field(default=None, min_length=2, max_length=16)
    notification_preferences: NotificationPreferences | None = None
    ai_optimization: AIOptimizationPreferences | None = None


class PasswordChange(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def _settings_out(user, deps: dict, blog_settings) -> dict:  # type: ignore[no-untyped-def]
    default_provider = blog_settings_service.settings_to_dict(blog_settings)["ai_apply"][
        "default_provider"
    ]
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "timezone": user.timezone,
            "locale": user.locale,
            "notification_preferences": user.notification_preferences,
        },
        "notification_preferences": user.notification_preferences,
        "dependencies": deps,
        "ai_optimization": {
            "default_provider": default_provider,
            "version": blog_settings.version,
            "providers": [
                {
                    "key": "radio",
                    "label": "Radio（Gemini 轻量正文优化）",
                    "configured": deps["radio"]["configured"],
                    "state": deps["radio"]["state"],
                },
                {
                    "key": "aiassist",
                    "label": "AI Assist（完整优化）",
                    "configured": deps["llm"]["configured"],
                    "state": deps["llm"]["state"],
                },
            ],
        },
    }


@router.get("")
def get_settings_endpoint(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    db_user = service.get_user(db, user.id)
    blog_settings = blog_settings_service.get_settings(db, user.id)
    db.commit()
    return _settings_out(db_user, service.dependency_states(), blog_settings)


@router.patch("")
def patch_settings(
    body: SettingsPatch,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    data = body.model_dump(exclude_unset=True)
    ai_preferences = data.pop("ai_optimization", None)
    if body.notification_preferences is not None:
        data["notification_preferences"] = body.notification_preferences.model_dump()
    db_user = service.update_settings(db, user.id, data) if data else service.get_user(db, user.id)
    blog_settings = blog_settings_service.get_settings(db, user.id)
    if ai_preferences is not None:
        blog_settings = blog_settings_service.set_default_ai_provider(
            db, user.id, ai_preferences["default_provider"]
        )
    db.commit()
    return _settings_out(db_user, service.dependency_states(), blog_settings)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    service.change_password(db, user.id, body.current_password, body.new_password)
    db.commit()
    return Response(status_code=204)


class MemoryItem(BaseModel):
    model_config = {"extra": "forbid"}
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=1000)


class MemoryBody(BaseModel):
    model_config = {"extra": "forbid"}
    items: list[MemoryItem] = Field(max_length=12)


@router.get("/memory")
def get_memory(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    db_user = service.get_user(db, user.id)
    facts = plan_service.get_user_facts(db_user)
    return {"items": [{"question": f["q"], "answer": f["a"]} for f in facts]}


@router.put("/memory")
def put_memory(
    body: MemoryBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    db_user = service.get_user(db, user.id)
    plan_service.set_user_facts(db_user, [{"q": i.question, "a": i.answer} for i in body.items])
    db.commit()
    facts = plan_service.get_user_facts(db_user)
    return {"items": [{"question": f["q"], "answer": f["a"]} for f in facts]}
