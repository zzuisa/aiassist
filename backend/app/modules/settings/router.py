"""Settings endpoints: get/patch settings, change password."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.settings import service

router = APIRouter(prefix="/settings", tags=["settings"])


class NotificationPreferences(BaseModel):
    model_config = {"extra": "forbid"}
    in_app_enabled: bool = True
    email_enabled: bool = False
    critical_email_enabled: bool = True
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class SettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    locale: str | None = Field(default=None, min_length=2, max_length=16)
    notification_preferences: NotificationPreferences | None = None


class PasswordChange(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def _settings_out(user, deps: dict) -> dict:  # type: ignore[no-untyped-def]
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
    }


@router.get("")
def get_settings_endpoint(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    db_user = service.get_user(db, user.id)
    return _settings_out(db_user, service.dependency_states())


@router.patch("")
def patch_settings(
    body: SettingsPatch,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    data = body.model_dump(exclude_unset=True)
    if body.notification_preferences is not None:
        data["notification_preferences"] = body.notification_preferences.model_dump()
    db_user = service.update_settings(db, user.id, data)
    db.commit()
    return _settings_out(db_user, service.dependency_states())


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    service.change_password(db, user.id, body.current_password, body.new_password)
    db.commit()
    return Response(status_code=204)
