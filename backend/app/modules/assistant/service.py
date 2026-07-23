"""Assistant run orchestration + structured action cards.

An assistant run loads authorized grounded context, produces structured action
cards referencing real entity IDs+versions, and stores those source versions.
Applying an action goes through the normal domain service (ownership + fixed-event
+ optimistic-version checks re-run); unselected/fixed/stale data never changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.modules.assistant.context import load_context
from app.modules.jobs import service as jobs_service
from app.modules.tasks import calendar_service
from app.modules.tasks import service as task_service

# In-memory run store keyed by run id. A run is short-lived and tied to a job;
# action definitions carry the grounded source versions for re-checking on apply.
_RUNS: dict[str, dict] = {}


def create_run(session: Session, user_id: uuid.UUID, intent: str, instruction: str | None) -> dict:
    job = jobs_service.create_job(
        session, user_id=user_id, job_type=f"assistant.{intent}", entity_type="assistant_run"
    )
    context = load_context(session, user_id, intent)

    cards: list[dict] = []
    grounded_refs = context.entity_refs

    if context.empty:
        cards.append(
            {
                "id": "no_result",
                "kind": "summary",
                "title": "未找到相关数据",
                "body": {"message": "没有找到可操作的记录，请先创建任务。"},
                "actions": [],
            }
        )
    elif intent in ("plan_today", "adjust_week"):
        # Grounded plan: propose a concrete move only for AI-adjustable tasks.
        actions = []
        for t in context.payload["tasks"]:
            if t["is_fixed"] or not t["is_ai_adjustable"]:
                continue
            actions.append(
                {
                    "id": f"reschedule:{t['id']}",
                    "label": f"调整「{t['title']}」到下一个空档",
                    "destructive": False,
                    # Stored source version re-checked on apply.
                    "_task_id": t["id"],
                    "_task_version": t["version"],
                    "_new_start": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                }
            )
        cards.append(
            {
                "id": "plan",
                "kind": "plan",
                "title": "今日安排建议",
                "body": {
                    "reason": "基于当前未完成任务的具体时间建议",
                    "fixed_kept": [t["id"] for t in context.payload["tasks"] if t["is_fixed"]],
                },
                "actions": actions,
            }
        )

    run_id = str(uuid.uuid4())
    _RUNS[run_id] = {
        "user_id": str(user_id),
        "intent": intent,
        "job_id": str(job.id),
        "cards": cards,
        "grounded_refs": grounded_refs,
    }
    jobs_service.transition(session, job, status="completed", progress=100, current_step="分析完成")
    return {
        "id": run_id,
        "intent": intent,
        "status": "completed",
        "job_id": str(job.id),
        "cards": [_public_card(c) for c in cards],
        "grounded_refs": grounded_refs,
    }


def _public_card(card: dict) -> dict:
    """Strip internal (_-prefixed) action fields before returning to the client."""
    return {
        **card,
        "actions": [
            {k: v for k, v in a.items() if not k.startswith("_")} for a in card.get("actions", [])
        ],
    }


def get_run(user_id: uuid.UUID, run_id: str) -> dict:
    run = _RUNS.get(run_id)
    if run is None or run["user_id"] != str(user_id):
        raise NotFoundError("Run not found")
    return {
        "id": run_id,
        "intent": run["intent"],
        "status": "completed",
        "job_id": run["job_id"],
        "cards": [_public_card(c) for c in run["cards"]],
        "grounded_refs": run["grounded_refs"],
    }


def execute_action(session: Session, user_id: uuid.UUID, run_id: str, action_id: str) -> dict:
    """Apply exactly one explicit action through the normal domain service.

    Re-runs ownership, fixed-event and optimistic-version checks. Rejects stale or
    fixed targets; only the selected action takes effect.
    """
    run = _RUNS.get(run_id)
    if run is None or run["user_id"] != str(user_id):
        raise NotFoundError("Run not found")

    action = None
    for card in run["cards"]:
        for a in card.get("actions", []):
            if a["id"] == action_id:
                action = a
                break
    if action is None:
        raise NotFoundError("Action not found")

    if action_id.startswith("reschedule:"):
        task_id = uuid.UUID(action["_task_id"])
        task = task_service.get_task(session, user_id, task_id)
        # Optimistic version + fixed-event checks re-run inside the domain service.
        new_start = datetime.fromisoformat(action["_new_start"])
        try:
            calendar_service.reschedule_task(
                session,
                user_id,
                task,
                version=action["_task_version"],
                start_at=new_start,
                due_at=None,
                by_ai=True,
            )
        except ValidationError as exc:
            raise ConflictError("固定事件不可调整或已过期", code="fixed_event") from exc
        session.commit()
        return {"applied": action_id, "task_id": str(task_id)}

    raise ValidationError("Unsupported action", code="unsupported_action")


def clear_runs() -> None:
    _RUNS.clear()
