"""Owned blog settings endpoints with optimistic concurrency (T168)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.posts import settings_service

router = APIRouter(prefix="/blog/settings", tags=["blog-settings"])


class BlogSettingsWrite(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal["blog-settings.v1"]
    create_defaults: dict
    clipboard: dict
    url_capture: dict
    ai_apply: dict
    word_cloud: dict
    version: int


def _response(db: Session, user_id, row) -> dict:  # type: ignore[no-untyped-def]
    return {
        **settings_service.settings_to_dict(row),
        "warnings": settings_service.validate_references(db, user_id, row),
    }


@router.get("")
def get_blog_settings(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = settings_service.get_settings(db, user.id)
    result = _response(db, user.id, row)
    db.commit()
    return result


@router.put("")
def put_blog_settings(
    body: BlogSettingsWrite,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    payload = body.model_dump(exclude={"schema_version", "version"})
    row, _warnings = settings_service.update_settings(db, user.id, payload, version=body.version)
    result = _response(db, user.id, row)
    db.commit()
    return result
