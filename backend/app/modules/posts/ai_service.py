"""AI optimization submission + finalization (spec 005, US3, T071/T074).

Submitting an optimization is transactional and *bound to a fixed base*: the
current revision, the resolved Skill version, the model key and the output schema
are all pinned at submit time and never re-resolved later. An exact-duplicate
submission (same input hash, still active) returns the existing Job instead of
queuing a second run. The AI never mutates the current article — the worker saves
an unapplied candidate revision and a PostAICandidate row.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError, VersionConflictError
from app.models.blog import PostAICandidate, PostAIRun
from app.models.posts import Post
from app.modules.posts import protected_content, service, skill_service
from app.services.outbox.publisher import append_event

OPTIMIZATION_TYPES = ("full", "language", "structure", "metadata", "check", "reoptimize")
SCOPES = ("all", "body", "metadata", "selected_fields")
AI_SCHEMA_VERSION = "blog-optimization.v1"


def _compute_input_hash(
    *,
    post_id: uuid.UUID,
    base_revision_id: uuid.UUID | None,
    optimization_type: str,
    scope: str,
    selected_fields: list[str],
    skill_version_id: uuid.UUID,
    model_key: str,
    instruction: str | None,
) -> str:
    payload = json.dumps(
        {
            "post": str(post_id),
            "base": str(base_revision_id),
            "type": optimization_type,
            "scope": scope,
            "fields": sorted(selected_fields),
            "skill_version": str(skill_version_id),
            "model": model_key,
            "instruction": instruction or "",
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def submit_optimization(
    session: Session,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    *,
    post_version: int,
    optimization_type: str,
    scope: str = "all",
    selected_fields: list[str] | None = None,
    skill_id: uuid.UUID | None = None,
    model_key: str | None = None,
    instruction: str | None = None,
) -> tuple[Any, PostAIRun, bool]:
    """Submit an AI optimization. Returns ``(job, run, is_duplicate)``.

    Binds the current revision, resolved Skill version, model and schema. A
    duplicate (identical input still active) returns the existing job with
    ``is_duplicate=True`` and does not enqueue a second run.
    """
    from app.modules.jobs import service as jobs_service

    if optimization_type not in OPTIMIZATION_TYPES:
        raise ValidationError("invalid optimization_type", code="invalid_optimization_type")
    if scope not in SCOPES:
        raise ValidationError("invalid scope", code="invalid_scope")
    selected_fields = selected_fields or []
    if scope == "selected_fields":
        service.validate_selected_fields(selected_fields)

    post = service.get_post(session, user_id, post_id)
    if post.version != post_version:
        raise VersionConflictError(
            "Post changed; refresh before optimizing", code="version_conflict"
        )

    # Fixed binding: resolve the Skill version once, now.
    _skill, skill_version = skill_service.resolve_skill(
        session, user_id,
        manual_skill_id=skill_id,
        content_type_id=post.content_type_id,
        content_class=post.content_class,
    )
    resolved_model = model_key or skill_version.recommended_model or "default"
    base_revision_id = post.current_revision_id

    input_hash = _compute_input_hash(
        post_id=post.id, base_revision_id=base_revision_id,
        optimization_type=optimization_type, scope=scope, selected_fields=selected_fields,
        skill_version_id=skill_version.id, model_key=resolved_model, instruction=instruction,
    )

    # Exact-duplicate detection: an active run with the same input is reused.
    existing = session.scalar(
        select(PostAIRun).where(
            PostAIRun.user_id == user_id,
            PostAIRun.post_id == post.id,
            PostAIRun.input_hash == input_hash,
            PostAIRun.outcome.is_(None),
        )
    )
    if existing is not None:
        job = jobs_service.get_owned_job(session, user_id, existing.async_job_id)
        return job, existing, True

    field_policies = (skill_version.config_json or {}).get("field_policies", {})
    protected = protected_content.extract_tokens(post.markdown)

    job = jobs_service.create_job(
        session, user_id=user_id, job_type="blog.optimize",
        entity_type="post", entity_id=post.id,
    )
    run = PostAIRun(
        id=uuid.uuid4(),
        user_id=user_id,
        async_job_id=job.id,
        post_id=post.id,
        base_revision_id=base_revision_id or uuid.uuid4(),
        optimization_type=optimization_type,
        content_class=post.content_class,
        content_type_id=post.content_type_id,
        skill_version_id=skill_version.id,
        model_key=resolved_model,
        ai_schema_version=AI_SCHEMA_VERSION,
        field_policy_json=field_policies,
        protected_tokens_json=protected,
        input_hash=input_hash,
    )
    session.add(run)
    session.flush()

    # Reflect the queued state on the post projection (presentation only).
    post.latest_ai_status = "ai_queued"
    if post.content_status in ("draft", "triage", "completed"):
        post.content_status = "ai_queued"

    append_event(
        session, event_type="blog.optimize", aggregate_type="post_ai_run",
        aggregate_id=run.id, routing_key="blog.optimize",
        payload={"run_id": str(run.id), "post_id": str(post.id), "job_id": str(job.id),
                 "scope": scope, "optimization_type": optimization_type,
                 "selected_fields": selected_fields, "instruction": instruction},
        user_id=user_id,
    )
    try:
        from app.workers.tasks.blog import optimize as blog_optimize

        blog_optimize.delay(str(run.id), scope, selected_fields, instruction)
    except Exception:
        from app.core.observability import get_logger

        get_logger("posts").warning("blog_optimize_enqueue_failed", run_id=str(run.id))
    return job, run, False


def get_run(session: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> PostAIRun:
    run = session.get(PostAIRun, run_id)
    if run is None or run.user_id != user_id:
        raise NotFoundError("AI run not found")
    return run


def cancel_run(session: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> Any:
    """Request cancellation of an active run's Job (checkpoint-honored by worker)."""
    from app.modules.jobs import service as jobs_service

    run = get_run(session, user_id, run_id)
    if run.outcome is not None:
        raise ConflictError("Run already finished", code="run_finished")
    job = jobs_service.get_owned_job(session, user_id, run.async_job_id)
    return jobs_service.request_cancel(session, job)


# ---------------------------------------------------------------------------
# Finalization helpers used by the worker (T074)
# ---------------------------------------------------------------------------


def save_candidate(
    session: Session,
    run: PostAIRun,
    *,
    candidate_markdown: str,
    field_diff: dict[str, Any],
    validation: dict[str, Any],
    outcome: str,
) -> PostAICandidate:
    """Atomically save an unapplied AI candidate revision + PostAICandidate row.

    The current article text is never changed here. ``outcome`` is 'complete' or
    'partial'; the candidate status mirrors whether a merge is required.
    """
    post = session.get(Post, run.post_id)
    if post is None:
        raise ConflictError("post gone", code="post_missing")

    revision = service.create_ai_revision(
        session, post, candidate_markdown,
        change_summary=f"AI {run.optimization_type} 优化建议",
    )
    revision.async_job_id = run.async_job_id
    revision.skill_version_id = run.skill_version_id
    session.flush()

    status = "merge_required" if outcome == "partial" else "pending"
    candidate = PostAICandidate(
        id=uuid.uuid4(),
        user_id=run.user_id,
        post_id=run.post_id,
        ai_run_id=run.id,
        base_revision_id=run.base_revision_id,
        candidate_revision_id=revision.id,
        status=status,
        field_diff_json=field_diff,
        validation_json=validation,
    )
    session.add(candidate)
    session.flush()

    run.candidate_id = candidate.id
    run.outcome = outcome
    run.completed_at = datetime.now(UTC)
    run.validation_summary_json = validation

    # Presentation-only: the post now has a candidate awaiting review.
    post.latest_ai_status = "ai_review"
    post.content_status = "ai_review"
    post.ai_optimization_count = (post.ai_optimization_count or 0) + 1
    now = datetime.now(UTC)
    if post.first_ai_optimized_at is None:
        post.first_ai_optimized_at = now
    post.last_ai_optimized_at = now
    post.last_skill_version_id = run.skill_version_id
    return candidate


def mark_run_failed(session: Session, run: PostAIRun, *, code: str) -> None:
    post = session.get(Post, run.post_id)
    run.outcome = "failed"
    run.completed_at = datetime.now(UTC)
    run.validation_summary_json = {"error": code}
    if post is not None:
        # Editing is never blocked: fall back to a normal editable status.
        post.latest_ai_status = "failed"
        if post.content_status in ("ai_queued", "ai_processing"):
            post.content_status = "draft"
