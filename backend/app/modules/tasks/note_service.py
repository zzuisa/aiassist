"""Task note text + image attachments.

One mutable note per task. Images are attached in batches: each uploaded object is
validated and associated independently inside a savepoint, so one bad file never
rolls back the note or the other images (FR-013). A sanitized, EXIF-stripped
preview is generated for each image; the private original is never served directly.
"""

from __future__ import annotations

import io
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.tasks import TaskNote, TaskNoteAsset
from app.models.voice import UploadSession
from app.modules.captures.upload_service import make_sanitized_derivative, validate_image
from app.modules.tasks import service as task_service
from app.services.storage.providers.local import get_storage

_PREVIEW_MAX = 1280
# Only these get a generated thumbnail; other files attach as-is (basic card).
_PREVIEWABLE_IMAGE = {"image/jpeg", "image/png", "image/webp"}
PROCESSING_VERSION = "tna-1"


def get_note(session: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskNote | None:
    task_service.get_task(session, user_id, task_id)  # ownership check (404 if not owned)
    return session.scalar(
        select(TaskNote).where(
            TaskNote.user_id == user_id,
            TaskNote.task_id == task_id,
            TaskNote.deleted_at.is_(None),
        )
    )


def get_or_create_note(session: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskNote:
    note = get_note(session, user_id, task_id)
    if note is None:
        note = TaskNote(id=uuid.uuid4(), user_id=user_id, task_id=task_id, content="", version=1)
        session.add(note)
        session.flush()
    return note


def list_assets(session: Session, note_id: uuid.UUID) -> list[TaskNoteAsset]:
    return list(
        session.scalars(
            select(TaskNoteAsset)
            .where(TaskNoteAsset.note_id == note_id, TaskNoteAsset.deleted_at.is_(None))
            .order_by(TaskNoteAsset.position)
        ).all()
    )


def save_note_text(
    session: Session,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    content: str,
    version: int | None = None,
) -> TaskNote:
    content = (content or "").strip()
    if len(content) > 20000:
        raise ValidationError("Note too long", code="note_too_long")
    existing = get_note(session, user_id, task_id)
    # Nothing to persist: no text and no note yet -> return a soft-empty note
    # instead of erroring (the user simply hasn't written anything).
    if not content and existing is None:
        return TaskNote(id=uuid.uuid4(), user_id=user_id, task_id=task_id, content="", version=0)
    note = get_or_create_note(session, user_id, task_id)
    if version is not None and note.version != version:
        raise ConflictError(
            "Note was modified elsewhere. Refresh and retry.", code="version_conflict"
        )
    note.content = content
    note.version += 1
    return note


def _next_position(session: Session, note_id: uuid.UUID) -> int:
    current = session.scalar(
        select(func.max(TaskNoteAsset.position)).where(TaskNoteAsset.note_id == note_id)
    )
    return 0 if current is None else current + 1


def attach_images(
    session: Session, user_id: uuid.UUID, task_id: uuid.UUID, upload_ids: list[uuid.UUID]
) -> tuple[TaskNote, list[dict]]:
    """Attach a batch of completed uploads to the task note.

    Each item is processed in its own savepoint; a failure is reported per-item
    (`status='failed'`) without rolling back the note or already-attached images.
    """
    note = get_or_create_note(session, user_id, task_id)
    storage = get_storage()
    results: list[dict] = []

    for upload_id in upload_ids:
        try:
            with session.begin_nested():
                upload = session.get(UploadSession, upload_id)
                if upload is None or upload.user_id != user_id:
                    raise ValidationError("Upload not found", code="not_found")
                if upload.purpose != "task_note_image":
                    raise ValidationError("Wrong upload purpose", code="invalid_purpose")
                if upload.status != "completed":
                    raise ValidationError("Upload not completed", code="upload_incomplete")
                if session.scalar(
                    select(TaskNoteAsset.id).where(TaskNoteAsset.upload_id == upload_id)
                ):
                    raise ConflictError("Already attached", code="already_attached")

                data = b"".join(storage.open_stream(upload.object_key_temp))
                media_type = upload.expected_media_type
                is_image = media_type in _PREVIEWABLE_IMAGE
                width = height = None
                if is_image and media_type is not None:
                    width, height = validate_image(data, media_type)

                asset = TaskNoteAsset(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    note_id=note.id,
                    upload_id=upload_id,
                    storage_key=upload.object_key_temp,
                    filename=upload.filename or "file",
                    media_type=media_type,
                    byte_size=upload.byte_size or len(data),
                    sha256=upload.sha256,
                    width=width,
                    height=height,
                    position=_next_position(session, note.id),
                    processing_status="pending" if is_image else "ready",
                    processing_version=PROCESSING_VERSION,
                )
                session.add(asset)
                session.flush()

                # Only images get a sanitized (EXIF/GPS-stripped) thumbnail; other
                # files attach as-is. The private original is served via access.
                if is_image:
                    try:
                        preview = make_sanitized_derivative(data, max_size=_PREVIEW_MAX)
                        preview_key = f"assets/{user_id}/{asset.id.hex}-preview.webp"
                        storage.put_stream(
                            preview_key,
                            io.BytesIO(preview),
                            media_type="image/webp",
                            max_bytes=len(preview) + 1,
                        )
                        asset.preview_storage_key = preview_key
                        asset.processing_status = "ready"
                    except Exception as exc:  # preview failure keeps the original attached
                        asset.processing_status = "failed"
                        asset.last_error = str(exc)[:255]

            results.append(
                {
                    "upload_id": str(upload_id),
                    "status": "attached",
                    "asset_id": str(asset.id),
                }
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            results.append({"upload_id": str(upload_id), "status": "failed", "error": exc.code})
    return note, results


def note_exists(session: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
    """True when the task already has a (non-deleted) note."""
    return (
        session.scalar(
            select(TaskNote.id).where(
                TaskNote.user_id == user_id,
                TaskNote.task_id == task_id,
                TaskNote.deleted_at.is_(None),
            )
        )
        is not None
    )


def get_owned_asset(
    session: Session, user_id: uuid.UUID, task_id: uuid.UUID, asset_id: uuid.UUID
) -> TaskNoteAsset:
    """Resolve an asset through the owned task + note; foreign ids -> not found."""
    note = get_note(session, user_id, task_id)
    if note is None:
        raise NotFoundError("Note not found")
    asset = session.get(TaskNoteAsset, asset_id)
    if (
        asset is None
        or asset.note_id != note.id
        or asset.user_id != user_id
        or asset.deleted_at is not None
    ):
        raise NotFoundError("Asset not found")
    return asset
