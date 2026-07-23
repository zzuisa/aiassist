"""Capture service: create (save-first), filter, update (user-over-AI), convert.

Creating a capture persists the record and its original assets immediately, then
enqueues async processing via the outbox. User edits never touch AI columns and
AI results never touch user columns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError, VersionConflictError
from app.models.captures import Capture, CaptureAsset
from app.models.foundation import ActivityLog
from app.models.relations import EntityRelation
from app.models.tasks import Task
from app.models.voice import UploadSession
from app.modules.jobs import service as jobs_service
from app.services.outbox.publisher import append_event

_USER_FIELDS = {
    "title": "title_user",
    "description": "description_user",
    "brand": "brand_user",
    "model": "model_user",
    "material": "material_user",
    "color": "color_user",
    "storage_location": "storage_location_user",
}


def create_capture(
    session: Session,
    user_id: uuid.UUID,
    *,
    capture_type: str,
    title: str | None,
    description: str | None,
    upload_ids: list[uuid.UUID],
    url: str | None = None,
) -> Capture:
    capture = Capture(
        id=uuid.uuid4(),
        user_id=user_id,
        type=capture_type,
        title_user=title,
        description_user=description,
        processing_status="pending" if upload_ids else "ready",
    )
    session.add(capture)
    session.flush()

    # Attach original assets from completed uploads (save-first).
    for upload_id in upload_ids:
        upload = session.get(UploadSession, upload_id)
        if upload is None or upload.user_id != user_id:
            raise ValidationError("Upload not found", code="invalid_upload")
        if upload.status != "completed":
            raise ValidationError("Upload not completed", code="upload_incomplete")
        session.add(
            CaptureAsset(
                id=uuid.uuid4(),
                user_id=user_id,
                capture_id=capture.id,
                upload_id=upload.id,
                role="original",
                storage_key=upload.object_key_temp,
                media_type=upload.expected_media_type,
                byte_size=upload.byte_size,
                sha256=upload.sha256,
                status="ready",
            )
        )

    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="capture.created",
            entity_type="capture",
            entity_id=capture.id,
        )
    )
    if upload_ids:
        job = jobs_service.create_job(
            session,
            user_id=user_id,
            job_type="capture.process",
            entity_type="capture",
            entity_id=capture.id,
            idempotency_key=f"capture:{capture.id}:process",
        )
        append_event(
            session,
            event_type="capture.created",
            aggregate_type="capture",
            aggregate_id=capture.id,
            routing_key="image.process.capture",
            payload={"capture_id": str(capture.id), "job_id": str(job.id)},
            user_id=user_id,
        )
    return capture


def get_capture(session: Session, user_id: uuid.UUID, capture_id: uuid.UUID) -> Capture:
    capture = session.get(Capture, capture_id)
    if capture is None or capture.user_id != user_id or capture.deleted_at is not None:
        raise NotFoundError("Capture not found")
    return capture


def list_captures(
    session: Session,
    user_id: uuid.UUID,
    *,
    type_: str | None = None,
    state: str | None = None,
    limit: int = 50,
) -> list[Capture]:
    stmt = select(Capture).where(Capture.user_id == user_id, Capture.deleted_at.is_(None))
    if type_:
        stmt = stmt.where(Capture.type == type_)
    if state == "pending":
        stmt = stmt.where(Capture.processing_status.in_(["pending", "processing"]))
    elif state == "needs_input":
        stmt = stmt.where(Capture.processing_status == "needs_input")
    elif state == "duplicate":
        stmt = stmt.where(Capture.possible_duplicate_of.is_not(None))
    elif state == "wishlist":
        stmt = stmt.where(Capture.usage_status == "wishlist")
    elif state == "owned":
        stmt = stmt.where(Capture.usage_status.in_(["owned", "in_use", "stored"]))
    elif state == "blog_material":
        stmt = stmt.where(Capture.type == "blog_material")
    stmt = stmt.order_by(Capture.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def update_capture(
    session: Session, user_id: uuid.UUID, capture_id: uuid.UUID, version: int, data: dict
) -> Capture:
    capture = get_capture(session, user_id, capture_id)
    if capture.version != version:
        raise VersionConflictError("Capture was modified; refresh", code="version_conflict")
    for api_field, col in _USER_FIELDS.items():
        if api_field in data:
            setattr(capture, col, data[api_field])
    if "category_id" in data:
        capture.category_id = data["category_id"]
    if data.get("usage_status"):
        capture.usage_status = data["usage_status"]
    capture.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="capture.updated",
            entity_type="capture",
            entity_id=capture.id,
        )
    )
    return capture


def apply_ai_suggestions(
    session: Session, capture: Capture, analysis: dict, confidence: float | None = None
) -> None:
    """Store AI results in *_ai columns only. Never touches user columns."""
    capture.title_ai = analysis.get("title")
    capture.description_ai = analysis.get("description")
    for fact in analysis.get("facts", []):
        field = fact.get("field")
        value = fact.get("value")
        # AI facts only populate *_ai columns; usage_status stays user-owned and
        # the AI value is surfaced separately in the UI, never written here.
        if field in ("brand", "model", "material", "color", "storage_location"):
            setattr(capture, f"{field}_ai", value)
    capture.ocr_text = analysis.get("ocr_text", capture.ocr_text)
    capture.ai_confidence = confidence
    capture.processing_status = "ready"


def delete_capture(session: Session, user_id: uuid.UUID, capture_id: uuid.UUID) -> None:
    capture = get_capture(session, user_id, capture_id)
    capture.deleted_at = datetime.now(UTC)
    capture.version += 1


def convert_capture(
    session: Session,
    user_id: uuid.UUID,
    capture_id: uuid.UUID,
    target_type: str,
    overrides: dict | None = None,
) -> tuple[str, uuid.UUID]:
    """Convert/relate a capture to another entity, within the same user."""
    capture = get_capture(session, user_id, capture_id)
    overrides = overrides or {}
    if target_type in ("task", "restock_reminder", "habit"):
        task = Task(
            id=uuid.uuid4(),
            user_id=user_id,
            type="task",
            title=overrides.get("title") or capture.title_user or capture.title_ai or "收藏项",
            status="todo",
            source_type="capture",
            source_id=capture.id,
        )
        session.add(task)
        session.flush()
        _relate(session, user_id, capture.id, "task", task.id, "converted_to")
        return "task", task.id
    if target_type in ("purchase", "blog_material"):
        # Mark capture type; relation is to itself (semantic conversion).
        capture.type = "purchase" if target_type == "purchase" else "blog_material"
        capture.version += 1
        return "capture", capture.id
    raise ValidationError("Unsupported conversion target", code="invalid_target")


def _relate(
    session: Session,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    relation_type: str,
) -> None:
    session.add(
        EntityRelation(
            id=uuid.uuid4(),
            user_id=user_id,
            source_type="capture",
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relation_type=relation_type,
        )
    )


def list_assets(session: Session, capture_id: uuid.UUID) -> list[CaptureAsset]:
    return list(
        session.scalars(
            select(CaptureAsset).where(
                CaptureAsset.capture_id == capture_id, CaptureAsset.deleted_at.is_(None)
            )
        ).all()
    )
