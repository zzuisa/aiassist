"""Image processing pipeline: hash -> sanitize -> thumbnail/preview -> OCR hook.

Steps are idempotent and keyed by processing_version so worker redelivery does
not create duplicate derivatives. The raw original is read-only; derivatives use
versioned object keys.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.observability import get_logger
from app.db.session import session_scope
from app.modules.captures import upload_service
from app.services.storage.providers.local import get_storage
from app.workers.celery_app import celery

log = get_logger("worker.images")
PROCESSING_VERSION = "v1"


def _derive_key(original_key: str, role: str) -> str:
    return f"{original_key}.{PROCESSING_VERSION}.{role}.webp"


def process_capture_images(capture_id: uuid.UUID) -> str:
    """Run the sanitize/thumbnail pipeline for a capture's original assets."""
    from app.models.captures import Capture, CaptureAsset

    storage = get_storage()
    with session_scope() as s:
        capture = s.get(Capture, capture_id)
        if capture is None or capture.deleted_at is not None:
            return "skipped"
        capture.processing_status = "processing"
        originals = list(
            s.scalars(
                select(CaptureAsset).where(
                    CaptureAsset.capture_id == capture_id,
                    CaptureAsset.role == "original",
                    CaptureAsset.status == "ready",
                )
            ).all()
        )

        for original in originals:
            data = b"".join(storage.open_stream(original.storage_key))
            media_type = original.media_type or "image/jpeg"
            if not media_type.startswith("image/"):
                continue
            try:
                width, height = upload_service.validate_image(data, media_type)
            except Exception as exc:
                log.warning("image_validate_failed", capture_id=str(capture_id), error=str(exc))
                capture.processing_status = "failed"
                return "failed"
            original.width, original.height = width, height

            for role, size in (("thumbnail", 320), ("preview", 1280)):
                key = _derive_key(original.storage_key, role)
                if storage.exists(key):
                    continue  # idempotent: derivative already produced
                derivative = upload_service.make_sanitized_derivative(data, max_size=size)
                import io as _io

                stored = storage.put_stream(
                    key,
                    _io.BytesIO(derivative),
                    media_type="image/webp",
                    max_bytes=len(derivative) + 1,
                )
                exists = s.scalar(
                    select(CaptureAsset).where(
                        CaptureAsset.capture_id == capture_id,
                        CaptureAsset.role == role,
                        CaptureAsset.processing_version == PROCESSING_VERSION,
                    )
                )
                if exists is None:
                    s.add(
                        CaptureAsset(
                            id=uuid.uuid4(),
                            user_id=capture.user_id,
                            capture_id=capture_id,
                            role=role,
                            storage_key=key,
                            media_type="image/webp",
                            byte_size=stored.byte_size,
                            sha256=stored.sha256,
                            gps_removed=True,
                            processing_version=PROCESSING_VERSION,
                            status="ready",
                        )
                    )

        # Duplicate hint by original sha256.
        for original in originals:
            if original.sha256:
                dup = s.scalar(
                    select(CaptureAsset).where(
                        CaptureAsset.user_id == capture.user_id,
                        CaptureAsset.sha256 == original.sha256,
                        CaptureAsset.role == "original",
                        CaptureAsset.capture_id != capture_id,
                    )
                )
                if dup is not None:
                    capture.possible_duplicate_of = dup.capture_id

        if capture.processing_status == "processing":
            capture.processing_status = "ready"
        return capture.processing_status


@celery.task(name="app.workers.tasks.images.process_capture", bind=True, max_retries=3)
def process_capture(self, capture_id: str) -> str:  # type: ignore[no-untyped-def]
    return process_capture_images(uuid.UUID(capture_id))
