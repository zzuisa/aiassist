"""Upload session lifecycle: create temp key -> stream bytes -> complete.

Bytes are streamed to a temporary private object key with hard byte/type limits.
The business record (voice_record / capture) is created only after the upload is
completed, following the compensation pattern (temp object -> commit -> finalize).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.models.voice import UploadSession
from app.services.storage.providers.local import get_storage
from sqlalchemy.orm import Session

UPLOAD_TTL_MINUTES = 60

_MAX_BYTES = {
    "voice": "upload_audio_max_bytes",
    "capture": "upload_image_max_bytes",
    "post_cover": "upload_image_max_bytes",
    "attachment": "upload_markdown_max_bytes",
}

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_ALLOWED_AUDIO_PREFIX = "audio/"


def create_session(
    session: Session,
    user_id: uuid.UUID,
    *,
    purpose: str,
    filename: str,
    media_type: str,
    byte_size: int,
    sha256: str | None = None,
) -> UploadSession:
    settings = get_settings()
    max_attr = _MAX_BYTES.get(purpose)
    if max_attr is None:
        raise ValidationError("Unknown upload purpose", code="invalid_purpose")
    max_bytes = getattr(settings, max_attr)
    if byte_size > max_bytes:
        raise ValidationError(
            f"Declared size exceeds limit ({max_bytes})", code="payload_too_large", status=413
        )
    if purpose in ("capture", "post_cover") and media_type not in _ALLOWED_IMAGE_TYPES:
        raise ValidationError("Unsupported image type", code="unsupported_media", status=415)
    if purpose == "voice" and not media_type.startswith(_ALLOWED_AUDIO_PREFIX):
        raise ValidationError("Unsupported audio type", code="unsupported_media", status=415)

    temp_key = f"tmp/{user_id}/{uuid.uuid4().hex}"
    upload = UploadSession(
        id=uuid.uuid4(),
        user_id=user_id,
        purpose=purpose,
        object_key_temp=temp_key,
        expected_media_type=media_type,
        max_bytes=max_bytes,
        status="created",
        sha256_client=sha256,
        filename=filename,
        expires_at=datetime.now(UTC) + timedelta(minutes=UPLOAD_TTL_MINUTES),
    )
    session.add(upload)
    session.flush()
    return upload


def get_owned(session: Session, user_id: uuid.UUID, upload_id: uuid.UUID) -> UploadSession:
    upload = session.get(UploadSession, upload_id)
    if upload is None or upload.user_id != user_id:
        raise NotFoundError("Upload session not found")
    return upload


def store_bytes(session: Session, upload: UploadSession, stream) -> None:  # type: ignore[no-untyped-def]
    """Stream request bytes to the temporary object, enforcing max_bytes."""
    stored = get_storage().put_stream(
        upload.object_key_temp,
        stream,
        media_type=upload.expected_media_type,
        max_bytes=upload.max_bytes,
    )
    upload.byte_size = stored.byte_size
    upload.sha256 = stored.sha256
    upload.status = "uploaded"


def complete(session: Session, user_id: uuid.UUID, upload_id: uuid.UUID) -> UploadSession:
    """Idempotently finalize an uploaded object (moves to a final key)."""
    upload = get_owned(session, user_id, upload_id)
    if upload.status == "completed":
        return upload
    if upload.status != "uploaded":
        raise ValidationError("Upload has no stored bytes", code="upload_incomplete")
    final_key = f"assets/{user_id}/{upload.id.hex}"
    get_storage().copy(upload.object_key_temp, final_key)
    get_storage().delete(upload.object_key_temp)
    upload.object_key_temp = final_key  # now the final key
    upload.status = "completed"
    upload.completed_at = datetime.now(UTC)
    return upload
