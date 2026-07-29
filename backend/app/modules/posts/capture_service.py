"""Content capture: blank / clipboard / URL / quick paths (spec 005, US1, T037).

Every capture persists the raw content and a first ``capture`` revision *before*
any extraction or AI runs, so nothing is lost when the network or Workers are
down.  All four paths are transactional: Post + PostSource + first revision +
(optional) Job + Outbox event commit together, and the URL path returns without
waiting on the network.

Ordering guarantee for URL capture: the durable rows (Post, PostSource, Job,
Outbox) are written in one transaction; the Celery enqueue is a best-effort
*after* signal — if it is lost, the Outbox publisher still drives extraction and
``retry_source`` can re-arm it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.foundation import ActivityLog
from app.models.blog import PostSource
from app.models.posts import Post
from app.modules.posts import normalization, service
from app.modules.posts.content_types import validate_content_class
from app.services.outbox.publisher import append_event


def _now() -> datetime:
    return datetime.now(UTC)


def _title_from_text(text: str, fallback: str = "未命名") -> str:
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:240]
    return fallback


def _create_post(
    session: Session,
    user_id: uuid.UUID,
    *,
    title: str,
    markdown: str,
    content_status: str,
    content_class: str,
    language: str,
    content_type_id: uuid.UUID | None,
) -> Post:
    validate_content_class(content_class)
    post = Post(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title or "未命名",
        markdown=markdown,
        status="draft",
        content_status=content_status,
        content_class=content_class,
        language=language,
        content_type_id=content_type_id,
    )
    session.add(post)
    session.flush()
    rev = service._new_revision(session, post, markdown, "capture", None)
    rev.applied_at = _now()
    post.current_revision_id = rev.id
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="post.captured",
            entity_type="post",
            entity_id=post.id,
        )
    )
    return post


def _add_source(
    session: Session,
    user_id: uuid.UUID,
    post: Post,
    *,
    source_type: str,
    status: str,
    **fields: Any,
) -> PostSource:
    src = PostSource(
        id=uuid.uuid4(),
        user_id=user_id,
        post_id=post.id,
        source_type=source_type,
        status=status,
        captured_at=_now(),
        **fields,
    )
    session.add(src)
    session.flush()
    return src


# ---------------------------------------------------------------------------
# Capture paths
# ---------------------------------------------------------------------------


def capture_blank(
    session: Session,
    user_id: uuid.UUID,
    *,
    title: str,
    content_class: str = "essay",
    language: str = "zh-CN",
    content_type_id: uuid.UUID | None = None,
) -> tuple[Post, PostSource, None, list[str]]:
    post = _create_post(
        session, user_id, title=title, markdown="", content_status="draft",
        content_class=content_class, language=language, content_type_id=content_type_id,
    )
    src = _add_source(session, user_id, post, source_type="blank", status="saved")
    return post, src, None, []


def capture_clipboard(
    session: Session,
    user_id: uuid.UUID,
    *,
    raw_content: str,
    detected_format: str,
    normalized_markdown: str | None = None,
    content_class: str = "quick",
    content_type_id: uuid.UUID | None = None,
) -> tuple[Post, PostSource, None, list[str]]:
    try:
        norm = normalization.normalize_clipboard(
            raw_content, detected_format, client_markdown=normalized_markdown
        )
    except ValueError as exc:
        raise ValidationError(str(exc), code="invalid_detected_format") from exc

    title = _title_from_text(norm.original_text, fallback="剪贴内容")
    post = _create_post(
        session, user_id, title=title, markdown=norm.normalized_markdown,
        content_status="triage", content_class=content_class, language="zh-CN",
        content_type_id=content_type_id,
    )
    src = _add_source(
        session, user_id, post, source_type="clipboard", status="completed",
        detected_format=norm.detected_format, original_text=norm.original_text,
        normalized_markdown=norm.normalized_markdown, extracted_at=_now(),
    )
    return post, src, None, norm.warnings


def capture_quick(
    session: Session,
    user_id: uuid.UUID,
    *,
    content: str,
    content_class: str = "quick",
) -> tuple[Post, PostSource, None, list[str]]:
    title = _title_from_text(content, fallback="快速记录")
    post = _create_post(
        session, user_id, title=title, markdown=content, content_status="triage",
        content_class=content_class, language="zh-CN", content_type_id=None,
    )
    src = _add_source(
        session, user_id, post, source_type="quick", status="completed",
        detected_format="plain", original_text=content, normalized_markdown=content,
        extracted_at=_now(),
    )
    return post, src, None, []


def capture_url(
    session: Session,
    user_id: uuid.UUID,
    *,
    url: str,
    note: str | None = None,
    usage: str = "triage",
    content_class: str = "bookmark",
    content_type_id: uuid.UUID | None = None,
) -> tuple[Post, PostSource, Any, list[str]]:
    """Durably save a URL source + pending article + extraction Job (no network here)."""
    from app.modules.jobs import service as jobs_service

    # Reject obviously unsafe URLs up-front (scheme/credentials); DNS/IP checks
    # happen in the worker at fetch time (per-hop), so a transient DNS failure
    # never blocks the durable save.
    from app.modules.posts.url_extractor import UrlSecurityError, canonicalize_url

    try:
        canonical = canonicalize_url(url)
    except UrlSecurityError as exc:
        raise ValidationError(str(exc), code=exc.code) from exc

    initial_md = f"# {note.strip()}\n\n<{canonical}>" if note else f"<{canonical}>"
    post = _create_post(
        session, user_id, title=note.strip()[:240] if note else canonical[:240],
        markdown=initial_md, content_status="pending_parse", content_class=content_class,
        language="zh-CN", content_type_id=content_type_id,
    )
    src = _add_source(
        session, user_id, post, source_type="url", status="pending",
        original_url=canonical, user_note=note,
        metadata_json={"usage": usage},
    )

    job = jobs_service.create_job(
        session, user_id=user_id, job_type="blog.parse",
        entity_type="post", entity_id=post.id,
    )
    src.async_job_id = job.id

    append_event(
        session, event_type="blog.parse", aggregate_type="post_source",
        aggregate_id=src.id, routing_key="blog.parse",
        payload={"source_id": str(src.id), "post_id": str(post.id), "job_id": str(job.id)},
        user_id=user_id,
    )
    # Best-effort enqueue; the Outbox publisher is the durable driver.
    try:
        from app.workers.tasks.blog import extract as blog_extract

        blog_extract.delay(str(src.id))
    except Exception:
        from app.core.observability import get_logger

        get_logger("posts").warning("blog_extract_enqueue_failed", source_id=str(src.id))
    return post, src, job, []


# ---------------------------------------------------------------------------
# Source access + retry
# ---------------------------------------------------------------------------


def get_source(session: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> PostSource:
    src = session.get(PostSource, source_id)
    if src is None or src.user_id != user_id:
        raise NotFoundError("Source not found")
    return src


def retry_source(session: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> Any:
    """Create a fresh extraction attempt for a failed/partial URL source."""
    from app.modules.jobs import service as jobs_service

    src = get_source(session, user_id, source_id)
    if src.source_type != "url":
        raise ConflictError("Only URL sources can be retried", code="not_url_source")
    if src.status not in ("failed", "partial"):
        raise ConflictError(
            "Only failed or partial sources can be retried", code="source_not_retryable"
        )
    src.status = "pending"
    src.error_code = None
    src.error_message = None
    src.fetch_attempt_count += 1

    job = jobs_service.create_job(
        session, user_id=user_id, job_type="blog.parse",
        entity_type="post", entity_id=src.post_id,
    )
    src.async_job_id = job.id
    append_event(
        session, event_type="blog.parse", aggregate_type="post_source",
        aggregate_id=src.id, routing_key="blog.parse",
        payload={"source_id": str(src.id), "post_id": str(src.post_id), "job_id": str(job.id),
                 "retry": True},
        user_id=user_id,
    )
    try:
        from app.workers.tasks.blog import extract as blog_extract

        blog_extract.delay(str(src.id))
    except Exception:
        from app.core.observability import get_logger

        get_logger("posts").warning("blog_extract_retry_enqueue_failed", source_id=str(src.id))
    return job


def list_sources_for_post(session: Session, user_id: uuid.UUID, post_id: uuid.UUID) -> list[PostSource]:
    return list(
        session.scalars(
            select(PostSource)
            .where(PostSource.user_id == user_id, PostSource.post_id == post_id)
            .order_by(PostSource.created_at)
        ).all()
    )
