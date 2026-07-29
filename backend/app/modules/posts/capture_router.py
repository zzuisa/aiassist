"""Capture + source endpoints (spec 005, US1, T038).

Paths mirror the OpenAPI contract: capture under ``/posts/captures/*`` and source
detail/retry/snapshot-access under ``/post-sources/*``.  Every capture is durable
before returning; the URL path returns ``202`` with a pending extraction Job.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, require_csrf
from app.core.errors import ConflictError, NotFoundError
from app.db.session import get_db
from app.modules.jobs.schemas import serialize_job
from app.modules.posts import capture_service
from app.modules.posts.schemas import (
    BlankCaptureBody,
    CaptureResultOut,
    ClipboardCaptureBody,
    PostSourceOut,
    QuickCaptureBody,
    UrlCaptureBody,
    post_out,
    source_out,
)

captures_router = APIRouter(prefix="/posts/captures", tags=["blog-capture"])
sources_router = APIRouter(prefix="/post-sources", tags=["blog-sources"])


def _result(post, source, job) -> CaptureResultOut:
    return CaptureResultOut(
        post=post_out(post),
        source=source_out(source),
        job=serialize_job(job).model_dump(mode="json") if job is not None else None,
        warnings=[],
    )


@captures_router.post("/blank", status_code=201)
def capture_blank(
    body: BlankCaptureBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> CaptureResultOut:
    post, src, job, warnings = capture_service.capture_blank(
        db, user.id, title=body.title, content_class=body.content_class,
        language=body.language, content_type_id=body.content_type_id,
    )
    db.commit()
    out = _result(post, src, job)
    out.warnings = warnings
    return out


@captures_router.post("/clipboard", status_code=201)
def capture_clipboard(
    body: ClipboardCaptureBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> CaptureResultOut:
    post, src, job, warnings = capture_service.capture_clipboard(
        db, user.id, raw_content=body.raw_content, detected_format=body.detected_format,
        normalized_markdown=body.normalized_markdown, content_class=body.content_class,
        content_type_id=body.content_type_id,
    )
    db.commit()
    out = _result(post, src, job)
    out.warnings = warnings
    return out


@captures_router.post("/url", status_code=202)
def capture_url(
    body: UrlCaptureBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> CaptureResultOut:
    post, src, job, warnings = capture_service.capture_url(
        db, user.id, url=body.url, note=body.note, usage=body.usage,
        content_class=body.content_class, content_type_id=body.content_type_id,
    )
    db.commit()
    out = _result(post, src, job)
    out.warnings = warnings
    return out


@captures_router.post("/quick", status_code=201)
def capture_quick(
    body: QuickCaptureBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> CaptureResultOut:
    post, src, job, warnings = capture_service.capture_quick(
        db, user.id, content=body.content, content_class=body.content_class,
    )
    db.commit()
    out = _result(post, src, job)
    out.warnings = warnings
    return out


# ------------------------------------------------------------------ sources


@sources_router.get("/{source_id}")
def get_source(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PostSourceOut:
    return source_out(capture_service.get_source(db, user.id, source_id))


@sources_router.post("/{source_id}/retry", status_code=202)
def retry_source(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    job = capture_service.retry_source(db, user.id, source_id)
    db.commit()
    return serialize_job(job).model_dump(mode="json")


@sources_router.get("/{source_id}/snapshot-access")
def snapshot_access(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Authorize access to an owned private source snapshot.

    Only the owner may obtain a reference; sources with no stored snapshot get a
    404 so private object keys are never leaked to non-owners.
    """
    src = capture_service.get_source(db, user.id, source_id)
    if not src.snapshot_object_key:
        raise NotFoundError("No snapshot for this source")
    from app.services.storage.providers.local import get_storage

    try:
        access = get_storage().access_url(src.snapshot_object_key, expires_in_seconds=300)
    except Exception as exc:  # storage unavailable — never expose the raw key
        raise ConflictError("Snapshot access temporarily unavailable", code="storage_unavailable") from exc
    return {"url": access.url, "expires_at": None}
