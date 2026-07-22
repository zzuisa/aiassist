"""Calendar week, schedule preview/apply, and reminder endpoints (US2)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models.foundation import User
from app.models.tasks import Task
from app.modules.jobs import service as jobs_service
from app.modules.jobs.schemas import serialize_job
from app.modules.tasks import calendar_service, schedule_service
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskOut

router = APIRouter(tags=["tasks"])


def _out(db: Session, t: Task) -> dict:
    return TaskOut.from_model(t, task_service.get_tag_ids(db, t.id)).model_dump(mode="json")


@router.get("/calendar/week")
def get_week(
    starts_on: date = Query(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    db_user = db.get(User, user.id)
    if db_user is None:
        raise NotFoundError("User not found")
    tz = ZoneInfo(db_user.timezone)
    starts_utc = datetime.combine(starts_on, time.min, tzinfo=tz).astimezone(UTC)
    events, unscheduled, conflicts = calendar_service.get_week(db, user.id, starts_utc)
    return {
        "starts_on": starts_on.isoformat(),
        "events": [_out(db, t) for t in events],
        "unscheduled": [_out(db, t) for t in unscheduled],
        "conflicts": [
            {
                "task_id": str(c.task_id),
                "conflicting_task_id": str(c.conflicting_task_id),
                "overlap_minutes": c.overlap_minutes,
                "fixed": c.fixed,
            }
            for c in conflicts
        ],
    }


class RescheduleBody(BaseModel):
    model_config = {"extra": "forbid"}
    version: int
    start_at: datetime | None = None
    due_at: datetime | None = None


@router.post("/tasks/{task_id}/reschedule", response_model=None)
def reschedule(
    task_id: uuid.UUID,
    body: RescheduleBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    task = task_service.get_task(db, user.id, task_id)
    calendar_service.reschedule_task(
        db,
        user.id,
        task,
        version=body.version,
        start_at=body.start_at,
        due_at=body.due_at,
        by_ai=False,
    )
    db.commit()
    return _out(db, task)


class PreviewCreate(BaseModel):
    model_config = {"extra": "forbid"}
    scope_start: datetime
    scope_end: datetime
    task_ids: list[uuid.UUID] = Field(default_factory=list)
    instruction: str | None = None


@router.post("/schedule-previews", status_code=202)
def create_schedule_preview(
    body: PreviewCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Create an async preview job. The preview is filled by the schedule worker;
    for MVP determinism a heuristic preview is produced synchronously and marked
    ready, while the durable job records the operation."""
    job = jobs_service.create_job(
        db, user_id=user.id, job_type="schedule.preview", entity_type="schedule_preview"
    )
    # Heuristic grounded preview: propose shifting conflicting non-fixed tasks.
    _events, _unscheduled, conflicts = calendar_service.get_week(db, user.id, body.scope_start)
    suggestions: list[dict] = []
    for c in conflicts:
        task = db.get(Task, c.task_id)
        if task is None:
            continue
        selectable = not (task.is_fixed or not task.is_ai_adjustable)
        suggestions.append(
            {
                "suggestion_id": f"s-{c.task_id}",
                "task_id": str(c.task_id),
                "task_version": task.version,
                "recommendation": "move" if selectable else "keep",
                "old_start": task.start_at.isoformat() if task.start_at else None,
                "old_end": task.due_at.isoformat() if task.due_at else None,
                "new_start": task.start_at.isoformat() if task.start_at else None,
                "new_end": task.due_at.isoformat() if task.due_at else None,
                "reason": "与其他任务时间冲突" if selectable else "固定事件不移动",
                "conflicting_task_ids": [str(c.conflicting_task_id)],
                "selectable": selectable,
            }
        )
    preview = schedule_service.create_preview(
        db,
        user.id,
        scope_start=body.scope_start,
        scope_end=body.scope_end,
        suggestions=suggestions,
        explanation="基于冲突的日程建议",
        async_job_id=job.id,
    )
    jobs_service.transition(db, job, status="completed", progress=100, current_step="预览已生成")
    db.commit()
    return {"preview_id": str(preview.id), "job": serialize_job(job).model_dump(mode="json")}


@router.get("/schedule-previews/{preview_id}")
def get_schedule_preview(
    preview_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    preview = schedule_service.get_preview(db, user.id, preview_id)
    return {
        "id": str(preview.id),
        "status": preview.status,
        "suggestions": preview.suggestions_json,
        "explanation": preview.explanation,
        "expires_at": preview.expires_at.isoformat(),
    }


class ApplyBody(BaseModel):
    model_config = {"extra": "forbid"}
    suggestion_ids: list[str] = Field(min_length=1)


@router.post("/schedule-previews/{preview_id}/apply")
def apply_schedule_preview(
    preview_id: uuid.UUID,
    body: ApplyBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    result = schedule_service.apply_preview(db, user.id, preview_id, body.suggestion_ids)
    db.commit()
    return result


class ReminderBody(BaseModel):
    model_config = {"extra": "forbid"}
    channel: str = "in_app"
    trigger_at: datetime
    offset_minutes: int | None = None
    is_critical: bool = False


@router.post("/tasks/{task_id}/reminders", status_code=201)
def add_reminder(
    task_id: uuid.UUID,
    body: ReminderBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.notifications import reminder_service

    task = task_service.get_task(db, user.id, task_id)
    reminder = reminder_service.create_reminder(
        db,
        user.id,
        task.id,
        channel=body.channel,
        trigger_at=body.trigger_at,
        offset_minutes=body.offset_minutes,
        is_critical=body.is_critical,
    )
    db.commit()
    return {"id": str(reminder.id), "status": reminder.status}
