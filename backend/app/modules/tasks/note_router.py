"""Task note endpoints: text note + batched image attachments (US2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.services.storage.providers.local import get_storage
from app.modules.tasks import note_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _asset_out(a) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(a.id),
        "filename": a.filename,
        "media_type": a.media_type,
        "width": a.width,
        "height": a.height,
        "position": a.position,
        "processing_status": a.processing_status,
    }


def _note_out(session, note) -> dict:  # type: ignore[no-untyped-def]
    if note is None:
        return {"content": "", "version": 0, "assets": []}
    return {
        "content": note.content,
        "version": note.version,
        "assets": [_asset_out(a) for a in note_service.list_assets(session, note.id)],
    }


class NoteBody(BaseModel):
    model_config = {"extra": "forbid"}
    content: str = Field(default="", max_length=20000)
    version: int | None = None


class AssetsBody(BaseModel):
    model_config = {"extra": "forbid"}
    upload_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


@router.get("/{task_id}/note")
def get_note(
    task_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _note_out(db, note_service.get_note(db, user.id, task_id))


@router.put("/{task_id}/note")
def put_note(
    task_id: uuid.UUID,
    body: NoteBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    note = note_service.save_note_text(db, user.id, task_id, body.content, body.version)
    db.commit()
    return _note_out(db, note)


@router.post("/{task_id}/note/assets", status_code=201)
def attach_assets(
    task_id: uuid.UUID,
    body: AssetsBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    note, results = note_service.attach_images(db, user.id, task_id, body.upload_ids)
    db.commit()
    return {"note": _note_out(db, note), "results": results}


@router.get("/{task_id}/note/assets/{asset_id}/access")
def asset_access(
    task_id: uuid.UUID,
    asset_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream the owned asset's bytes (sanitized preview for images, original for
    other files). Auth is via the session cookie, so the URL works as an <img> src."""
    asset = note_service.get_owned_asset(db, user.id, task_id, asset_id)
    key = asset.preview_storage_key or asset.storage_key
    content_type = "image/webp" if asset.preview_storage_key else asset.media_type
    return StreamingResponse(get_storage().open_stream(key), media_type=content_type)
