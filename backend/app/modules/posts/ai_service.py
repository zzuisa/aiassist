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
from app.models.blog import PostAICandidate, PostAIRun, PostCandidateDecision
from app.models.foundation import ActivityLog
from app.models.posts import Post, PostRevision
from app.modules.posts import (
    diffing,
    protected_content,
    service,
    settings_service,
    skill_service,
)
from app.services.outbox.publisher import append_event

OPTIMIZATION_TYPES = ("full", "language", "structure", "metadata", "check", "reoptimize")
SCOPES = ("all", "body", "metadata", "selected_fields")
AI_SCHEMA_VERSION = "blog-optimization.v1"
AI_PROVIDERS = ("radio", "aiassist")


def _compute_input_hash(
    *,
    post_id: uuid.UUID,
    base_revision_id: uuid.UUID | None,
    optimization_type: str,
    scope: str,
    selected_fields: list[str],
    skill_version_id: uuid.UUID,
    provider_key: str,
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
            "provider": provider_key,
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
    provider_key: str | None = None,
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
        session,
        user_id,
        manual_skill_id=skill_id,
        content_type_id=post.content_type_id,
        content_class=post.content_class,
    )
    resolved_provider = provider_key or settings_service.get_default_ai_provider(session, user_id)
    if resolved_provider not in AI_PROVIDERS:
        raise ValidationError("invalid AI optimization provider", code="invalid_ai_provider")
    resolved_model = (
        "radio-gemini"
        if resolved_provider == "radio"
        else (model_key or skill_version.recommended_model or "default")
    )
    base_revision_id = post.current_revision_id

    input_hash = _compute_input_hash(
        post_id=post.id,
        base_revision_id=base_revision_id,
        optimization_type=optimization_type,
        scope=scope,
        selected_fields=selected_fields,
        skill_version_id=skill_version.id,
        provider_key=resolved_provider,
        model_key=resolved_model,
        instruction=instruction,
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
        session,
        user_id=user_id,
        job_type="blog.optimize",
        entity_type="post",
        entity_id=post.id,
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
        provider_key=resolved_provider,
        model_key=resolved_model,
        ai_schema_version=AI_SCHEMA_VERSION,
        field_policy_json=field_policies,
        protected_tokens_json=protected,
        input_hash=input_hash,
    )
    session.add(run)
    session.flush()

    # Put immutable display context on the Job itself. Jobs are the source of
    # truth for the global task center and SSE stream, so the client should not
    # need an N+1 request to discover which article/provider each card belongs
    # to. Later result transitions preserve this nested context.
    jobs_service.transition(
        session,
        job,
        status="queued",
        progress=0,
        current_step="等待执行",
        result={
            "context": {
                "post_id": str(post.id),
                "post_title": post.title,
                "provider_key": resolved_provider,
                "optimization_type": optimization_type,
                "scope": scope,
            }
        },
    )

    # Reflect the queued state on the post projection (presentation only).
    post.latest_ai_status = "ai_queued"
    if post.content_status in ("draft", "triage", "completed"):
        post.content_status = "ai_queued"

    append_event(
        session,
        event_type="blog.optimize",
        aggregate_type="post_ai_run",
        aggregate_id=run.id,
        routing_key="blog.optimize",
        payload={
            "run_id": str(run.id),
            "post_id": str(post.id),
            "job_id": str(job.id),
            "scope": scope,
            "optimization_type": optimization_type,
            "selected_fields": selected_fields,
            "instruction": instruction,
        },
        user_id=user_id,
    )
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
        session,
        post,
        candidate_markdown,
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


# ---------------------------------------------------------------------------
# Candidate review + field-level apply (spec 005, US4, T087/T088/T090)
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = ("applied", "rejected", "copied")
_APPLY_ACTIONS = ("apply_all", "apply_body", "apply_metadata", "apply_fields")


def get_candidate(
    session: Session, user_id: uuid.UUID, candidate_id: uuid.UUID, *, lock: bool = False
) -> PostAICandidate:
    candidate = session.get(PostAICandidate, candidate_id, with_for_update=lock)
    if candidate is None or candidate.user_id != user_id:
        raise NotFoundError("Candidate not found")
    return candidate


def list_candidates(
    session: Session, user_id: uuid.UUID, post_id: uuid.UUID
) -> list[PostAICandidate]:
    service.get_post(session, user_id, post_id)  # ownership + existence
    return list(
        session.scalars(
            select(PostAICandidate)
            .where(
                PostAICandidate.post_id == post_id,
                PostAICandidate.user_id == user_id,
            )
            .order_by(PostAICandidate.created_at.desc())
        ).all()
    )


def _candidate_snapshot(
    base_snapshot: dict[str, Any],
    candidate_markdown: str,
    field_diff: dict[str, Any],
) -> dict[str, Any]:
    """The AI's proposed full state: base overlaid with proposed field values."""
    snap = dict(base_snapshot)
    snap["structured_data"] = dict(base_snapshot.get("structured_data") or {})
    snap["markdown"] = candidate_markdown
    for path, entry in field_diff.items():
        to_val = entry.get("to")
        if path.startswith("structured_data."):
            snap["structured_data"][path.split(".", 1)[1]] = to_val
        elif path != "markdown":
            snap[path] = to_val
    return snap


def compare_candidate(
    session: Session, user_id: uuid.UUID, candidate_id: uuid.UUID
) -> dict[str, Any]:
    """Three-way (base / current / candidate) comparison for review."""
    candidate = get_candidate(session, user_id, candidate_id)
    post = service.get_post(session, user_id, candidate.post_id)
    base_rev = session.get(PostRevision, candidate.base_revision_id)
    cand_rev = session.get(PostRevision, candidate.candidate_revision_id)
    if base_rev is None or cand_rev is None:
        raise ConflictError("Candidate revisions missing", code="candidate_corrupt")

    base_snap = dict(base_rev.snapshot_json or {})
    current_snap = service.build_snapshot(post)
    cand_snap = _candidate_snapshot(base_snap, cand_rev.markdown, candidate.field_diff_json)

    fields = diffing.field_diff(base_snap, current_snap, cand_snap)
    body = diffing.body_diff(post.markdown, cand_rev.markdown)
    conflicts = [f for f, e in fields.items() if e["status"] == diffing.CONFLICT]

    return {
        "candidate": serialize_candidate(candidate),
        "post_version": post.version,
        "field_diff": fields,
        "body_diff": body,
        "conflicts": conflicts,
        "validation": candidate.validation_json,
    }


def serialize_candidate(candidate: PostAICandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "post_id": str(candidate.post_id),
        "ai_run_id": str(candidate.ai_run_id),
        "base_revision_id": str(candidate.base_revision_id),
        "candidate_revision_id": str(candidate.candidate_revision_id),
        "status": candidate.status,
        "field_diff": candidate.field_diff_json,
        "validation": candidate.validation_json,
        "applied_revision_id": (
            str(candidate.applied_revision_id) if candidate.applied_revision_id else None
        ),
        "created_at": candidate.created_at.isoformat(),
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
    }


def _resolve_apply_paths(
    action: str, selected_fields: list[str], field_diff: dict[str, Any]
) -> list[str]:
    proposed = list(field_diff.keys())
    if action == "apply_all":
        return proposed
    if action == "apply_body":
        return ["markdown"] if "markdown" in proposed else []
    if action == "apply_metadata":
        return [p for p in proposed if p != "markdown"]
    # apply_fields: only the explicitly selected, validated subset.
    unknown = [f for f in selected_fields if f not in field_diff]
    if unknown:
        raise ValidationError(
            f"Selected fields not in candidate: {unknown}", code="invalid_selected_fields"
        )
    return list(selected_fields)


def decide_candidate(
    session: Session,
    user_id: uuid.UUID,
    candidate_id: uuid.UUID,
    *,
    action: str,
    selected_fields: list[str] | None = None,
    current_version: int,
) -> dict[str, Any]:
    """Apply a terminal decision to a candidate under an optimistic version lock.

    ``apply_*`` merges only the resolved fields into a *new* version-checked
    revision; the candidate's other proposals and the user's untouched fields are
    never silently overwritten. ``keep_current``/``reject`` discard the proposal;
    ``copy`` forks the candidate into a new draft post. Every path records an
    immutable :class:`PostCandidateDecision` and an activity log.
    """
    selected_fields = selected_fields or []
    candidate = get_candidate(session, user_id, candidate_id, lock=True)
    if candidate.status in _TERMINAL_STATUSES:
        raise ConflictError("Candidate already decided", code="candidate_decided")

    post = service.get_post(session, user_id, candidate.post_id)
    if post.version != current_version:
        raise VersionConflictError("Post was modified; refresh", code="version_conflict")

    current_before_id = post.current_revision_id
    result_revision_id: uuid.UUID | None = None
    applied_paths: list[str] = []

    if action in ("keep_current", "reject"):
        candidate.status = "rejected"
    elif action == "copy":
        new_post = _fork_candidate(session, user_id, post, candidate)
        candidate.status = "copied"
        result_revision_id = new_post.current_revision_id
    elif action in _APPLY_ACTIONS:
        applied_paths = _resolve_apply_paths(action, selected_fields, candidate.field_diff_json)
        result_revision_id = _merge_apply(session, user_id, post, candidate, applied_paths)
        candidate.status = "applied"
        candidate.applied_revision_id = result_revision_id
    else:
        raise ValidationError(f"Unknown action '{action}'", code="invalid_action")

    candidate.reviewed_at = datetime.now(UTC)
    # Once no pending candidate remains, the article is a normal draft again.
    if post.content_status == "ai_review":
        post.content_status = "draft"
    post.latest_ai_status = candidate.status

    decision = PostCandidateDecision(
        id=uuid.uuid4(),
        user_id=user_id,
        post_id=post.id,
        candidate_id=candidate.id,
        action=action,
        selected_fields_json={"fields": applied_paths},
        rejected_fields_json={
            "fields": [p for p in candidate.field_diff_json if p not in applied_paths]
        },
        current_revision_before_id=current_before_id,
        result_revision_id=result_revision_id,
    )
    session.add(decision)
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action=f"post.candidate_{candidate.status}",
            entity_type="post",
            entity_id=post.id,
            after_summary_json={
                "candidate_id": str(candidate.id),
                "action": action,
                "applied_fields": applied_paths,
            },
        )
    )
    session.flush()
    return {
        "candidate": serialize_candidate(candidate),
        "decision_id": str(decision.id),
        "post_version": post.version,
        "result_revision_id": str(result_revision_id) if result_revision_id else None,
    }


def _merge_apply(
    session: Session,
    user_id: uuid.UUID,
    post: Post,
    candidate: PostAICandidate,
    apply_paths: list[str],
) -> uuid.UUID:
    """Merge *apply_paths* from the candidate into a new applied revision."""
    base_rev = session.get(PostRevision, candidate.base_revision_id)
    cand_rev = session.get(PostRevision, candidate.candidate_revision_id)
    if base_rev is None or cand_rev is None:
        raise ConflictError("Candidate revisions missing", code="candidate_corrupt")
    base_snap = dict(base_rev.snapshot_json or {})
    cand_snap = _candidate_snapshot(base_snap, cand_rev.markdown, candidate.field_diff_json)

    # Apply only the selected candidate values onto the *current* post state.
    service.apply_snapshot(post, cand_snap, apply_paths)
    post.version += 1

    new_rev = service.new_revision(
        session,
        post,
        post.markdown,
        "ai_applied",
        post.current_revision_id,
        change_summary=f"应用 AI 候选（{len(apply_paths)} 个字段）",
        snapshot=service.build_snapshot(post),
    )
    new_rev.applied_at = datetime.now(UTC)
    new_rev.base_revision_id = candidate.base_revision_id
    post.current_revision_id = new_rev.id
    return new_rev.id


def _fork_candidate(
    session: Session,
    user_id: uuid.UUID,
    post: Post,
    candidate: PostAICandidate,
) -> Post:
    """Create an independent draft post from the AI candidate (never touches src)."""
    cand_rev = session.get(PostRevision, candidate.candidate_revision_id)
    base_rev = session.get(PostRevision, candidate.base_revision_id)
    if cand_rev is None or base_rev is None:
        raise ConflictError("Candidate revisions missing", code="candidate_corrupt")
    cand_snap = _candidate_snapshot(
        dict(base_rev.snapshot_json or {}), cand_rev.markdown, candidate.field_diff_json
    )
    new_post = service.create_post(
        session,
        user_id,
        title=f"{post.title}（AI 副本）",
        markdown=cand_rev.markdown,
    )
    service.apply_snapshot(new_post, cand_snap)
    return new_post
