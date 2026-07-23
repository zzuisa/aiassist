"""Voice record endpoints: create, get, retry, confirm."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.observability import get_logger
from app.db.session import get_db
from app.models.voice import VoiceRecord
from app.modules.voice import service
from app.services.llm.schemas import VoiceTaskV1

router = APIRouter(prefix="/voice-records", tags=["voice"])


def _out(record: VoiceRecord) -> dict:
    return {
        "id": str(record.id),
        "status": record.status,
        "transcript": record.transcript,
        "candidate": record.parsed_payload_json,
        "schema_version": record.schema_version,
        "job_id": str(record.async_job_id) if record.async_job_id else None,
        "error": {"code": record.error_code, "message": record.error_message}
        if record.error_code
        else None,
        "created_at": record.created_at.isoformat(),
    }


class VoiceCreate(BaseModel):
    model_config = {"extra": "forbid"}
    upload_id: uuid.UUID
    locale_hint: str | None = None


@router.post("", status_code=202)
def create_voice(
    body: VoiceCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    record = service.create_voice_record(db, user.id, body.upload_id)
    db.commit()
    # Enqueue processing (best-effort; the record is durable regardless).
    try:
        from app.workers.tasks.voice import process_voice

        process_voice.delay(str(record.id))
    except Exception:
        get_logger("voice").warning("voice_enqueue_failed")
    return _out(record)


class VoiceFromText(BaseModel):
    model_config = {"extra": "forbid"}
    transcript: str = Field(min_length=1, max_length=50000)


@router.post("/from-text", status_code=201)
def create_from_text(
    body: VoiceFromText,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Real-time recognition path: the browser already transcribed speech; parse
    the text into a structured candidate via the LLM gateway and return it for
    confirmation. No formal entity is created until the user confirms."""
    record = service.create_from_transcript(db, user.id, body.transcript)
    db.flush()
    # Parse synchronously (single LLM call) so the confirmation card is immediate.
    service.run_pipeline(db, record.id)
    db.commit()
    return _out(record)


@router.get("/{voice_id}")
def get_voice(
    voice_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _out(service.get_record(db, user.id, voice_id))


@router.post("/{voice_id}/retry", status_code=202)
def retry_voice(
    voice_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    record = service.retry(db, user.id, voice_id)
    db.commit()
    try:
        from app.workers.tasks.voice import process_voice

        process_voice.delay(str(record.id))
    except Exception:
        get_logger("voice").warning("voice_enqueue_failed")
    return _out(record)


class VoiceConfirm(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: str = Field(pattern="^voice-task\\.v1$")
    candidate: VoiceTaskV1


@router.post("/{voice_id}/confirm", status_code=201)
def confirm_voice(
    voice_id: uuid.UUID,
    body: VoiceConfirm,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    entity_type, entity_id = service.confirm(db, user.id, voice_id, body.candidate)
    db.commit()
    return {"entity_type": entity_type, "entity_id": str(entity_id)}
