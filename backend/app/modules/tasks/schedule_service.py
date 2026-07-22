"""Two-phase schedule adjustment: grounded preview generation + selective apply.

Preview generation records each suggestion with the source task's version at
generation time. Apply re-checks version and fixed-event rules per item; stale or
fixed items are rejected, never silently overwritten (FR-016/FR-017/FR-018).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.scheduling import SchedulePreview
from app.models.tasks import Task
from app.modules.tasks.calendar_service import reschedule_task

PREVIEW_TTL_MINUTES = 30


def _baseline_hash(tasks: list[Task]) -> str:
    parts = sorted(f"{t.id}:{t.version}" for t in tasks)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def create_preview(
    session: Session,
    user_id: uuid.UUID,
    *,
    scope_start: datetime,
    scope_end: datetime,
    suggestions: list[dict],
    explanation: str | None,
    async_job_id: uuid.UUID | None = None,
) -> SchedulePreview:
    """Persist a ready preview. `suggestions` follow schedule-preview.v1 shape.

    Fixed-event suggestions are forced to recommendation=keep, selectable=false.
    """
    tasks = list(
        session.scalars(
            select(Task).where(Task.user_id == user_id, Task.deleted_at.is_(None))
        ).all()
    )
    task_by_id = {str(t.id): t for t in tasks}

    normalized: list[dict] = []
    for s in suggestions:
        task = task_by_id.get(str(s.get("task_id")))
        selectable = bool(s.get("selectable", True))
        recommendation = s.get("recommendation", "move")
        if task is not None and (task.is_fixed or not task.is_ai_adjustable):
            selectable = False
            recommendation = "keep"
        normalized.append(
            {
                **s,
                "task_version": task.version if task else s.get("task_version", 1),
                "selectable": selectable,
                "recommendation": recommendation,
            }
        )

    now = datetime.now(UTC)
    preview = SchedulePreview(
        id=uuid.uuid4(),
        user_id=user_id,
        scope_start=scope_start,
        scope_end=scope_end,
        status="ready",
        baseline_hash=_baseline_hash(tasks),
        suggestions_json=normalized,
        explanation=explanation,
        async_job_id=async_job_id,
        expires_at=now + timedelta(minutes=PREVIEW_TTL_MINUTES),
        created_at=now,
    )
    session.add(preview)
    return preview


def get_preview(session: Session, user_id: uuid.UUID, preview_id: uuid.UUID) -> SchedulePreview:
    preview = session.get(SchedulePreview, preview_id)
    if preview is None or preview.user_id != user_id:
        raise NotFoundError("Preview not found")
    return preview


def apply_preview(
    session: Session, user_id: uuid.UUID, preview_id: uuid.UUID, suggestion_ids: list[str]
) -> dict:
    """Apply selected suggestions after per-item version and fixed-event checks."""
    preview = get_preview(session, user_id, preview_id)
    now = datetime.now(UTC)
    if preview.expires_at <= now or preview.status in ("expired", "applied"):
        preview.status = "expired"
        raise ConflictError("Preview expired; regenerate it", code="preview_expired")

    by_id = {s["suggestion_id"]: s for s in preview.suggestions_json}
    applied: list[str] = []
    rejected: list[dict] = []

    for sid in suggestion_ids:
        s = by_id.get(sid)
        if s is None:
            rejected.append({"suggestion_id": sid, "code": "invalid_time", "detail": "unknown"})
            continue
        if not s.get("selectable", False):
            rejected.append(
                {"suggestion_id": sid, "code": "fixed_event", "detail": "not selectable"}
            )
            continue
        task = session.get(Task, uuid.UUID(s["task_id"]))
        if task is None or task.user_id != user_id or task.deleted_at is not None:
            rejected.append({"suggestion_id": sid, "code": "version_conflict", "detail": "missing"})
            continue
        if task.version != s["task_version"]:
            rejected.append({"suggestion_id": sid, "code": "version_conflict", "detail": "stale"})
            continue
        try:
            new_start = _parse(s.get("new_start"))
            new_end = _parse(s.get("new_end"))
            reschedule_task(
                session,
                user_id,
                task,
                version=task.version,
                start_at=new_start,
                due_at=new_end,
                by_ai=True,
            )
            applied.append(sid)
        except Exception:
            rejected.append({"suggestion_id": sid, "code": "fixed_event", "detail": "rejected"})

    preview.status = "applied" if not rejected else "partially_applied"
    preview.applied_at = now

    activity_id = uuid.uuid4()
    return {"applied": applied, "rejected": rejected, "activity_id": str(activity_id)}


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
