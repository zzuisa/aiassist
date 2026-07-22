"""Today dashboard aggregation.

Read-only aggregation over already-committed data in the user's timezone. It
does not duplicate business data and never depends on AI/workers. Placeholder
sections (habits/suggestions/recent_captures) are filled in by their stories.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models.foundation import User
from app.models.tasks import Task
from app.modules.jobs import service as jobs_service
from app.modules.jobs.schemas import serialize_job
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskOut

router = APIRouter(tags=["today"])


def _day_bounds(local_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    end_local = datetime.combine(local_date, time.max, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


@router.get("/today")
def get_today(
    date_param: date | None = Query(default=None, alias="date"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    db_user = db.get(User, user.id)
    if db_user is None:
        raise NotFoundError("User not found")
    tz = ZoneInfo(db_user.timezone)
    now = datetime.now(UTC)
    local_today = date_param or now.astimezone(tz).date()
    day_start, day_end = _day_bounds(local_today, tz)

    def to_out(t: Task) -> dict:
        return TaskOut.from_model(t, task_service.get_tag_ids(db, t.id)).model_dump(mode="json")

    open_tasks = list(
        db.scalars(
            select(Task).where(
                Task.user_id == user.id,
                Task.deleted_at.is_(None),
                Task.status.in_(["todo", "in_progress"]),
            )
        ).all()
    )
    timeline = [t for t in open_tasks if t.start_at and day_start <= t.start_at <= day_end]
    timeline.sort(key=lambda t: t.start_at or now)
    todos = [t for t in open_tasks if t.type in ("task", "habit_task")]
    overdue = [t for t in open_tasks if t.due_at and t.due_at < now]

    current = task_service.select_current_task(db, user.id, now)
    active_jobs = jobs_service.list_jobs(
        db, user.id, statuses=["pending", "queued", "processing", "waiting_user"], limit=20
    )

    completed_today = db.scalar(
        select(Task.id).where(
            Task.user_id == user.id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= day_start,
            Task.completed_at <= day_end,
        )
    )

    return {
        "date": local_today.isoformat(),
        "stats": {
            "open_count": len(open_tasks),
            "overdue_count": len(overdue),
            "completed_today": 1 if completed_today else 0,
        },
        "current_task": to_out(current) if current else None,
        "timeline": [to_out(t) for t in timeline],
        "todos": [to_out(t) for t in todos],
        "habits": [],  # US3
        "overdue": [to_out(t) for t in overdue],
        "conflicts": [],  # US2
        "suggestions": [],  # US2/US9
        "recent_captures": [],  # US5
        "jobs": [serialize_job(j).model_dump(mode="json") for j in active_jobs],
    }
