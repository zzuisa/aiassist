"""Compatibility facade backed by durable Agent tasks."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.session import session_scope
from app.models.agent import AgentTask
from app.modules.agent import service as agent_service
from app.modules.assistant.context import load_context
from app.modules.jobs import service as jobs_service
from app.modules.tasks import calendar_service
from app.modules.tasks import service as task_service


def _public_card(card: dict) -> dict:
    return {
        **card,
        "actions": [
            {key: value for key, value in action.items() if not key.startswith("_")}
            for action in card.get("actions", [])
        ],
    }


def complete_agent_task(session: Session, task: AgentTask) -> dict:
    """Build legacy cards and store both private actions and public output durably."""
    context = load_context(session, task.user_id, task.intent_key)
    cards: list[dict] = []
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
    else:
        actions = []
        for item in context.payload["tasks"]:
            if item["is_fixed"] or not item["is_ai_adjustable"]:
                continue
            actions.append(
                {
                    "id": f"reschedule:{item['id']}",
                    "label": f"调整「{item['title']}」到下一个空档",
                    "destructive": False,
                    "_task_id": item["id"],
                    "_task_version": item["version"],
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
                    "fixed_kept": [
                        item["id"] for item in context.payload["tasks"] if item["is_fixed"]
                    ],
                },
                "actions": actions,
            }
        )
    public = {
        "id": str(task.id),
        "intent": task.intent_key,
        "status": "completed",
        "job_id": str(task.job_id),
        "cards": [_public_card(card) for card in cards],
        "grounded_refs": context.entity_refs,
    }
    task.scope_json = {
        **task.scope_json,
        "assistant_compat": {
            "cards": cards,
            "grounded_refs": context.entity_refs,
        },
    }
    task.result_summary = json.dumps(public, ensure_ascii=False, separators=(",", ":"))
    task.status = "success"
    task.finished_at = datetime.now(UTC)
    jobs_service.transition(
        session,
        task.job,
        status="completed",
        progress=100,
        current_step="分析完成",
        result={"agent_task_id": str(task.id)},
    )
    session.flush()
    return public


def create_run(session: Session, user_id: uuid.UUID, intent: str, instruction: str | None) -> dict:
    task = agent_service.create_agent_task(
        session,
        user_id=user_id,
        request_text=instruction or intent,
        intent_key=intent,
    )
    return complete_agent_task(session, task)


def _load_run(session: Session, user_id: uuid.UUID, run_id: str) -> tuple[AgentTask, dict]:
    try:
        task_id = uuid.UUID(run_id)
    except ValueError as exc:
        raise NotFoundError("Run not found") from exc
    task = agent_service.get_owned_task(session, user_id, task_id)
    compat = task.scope_json.get("assistant_compat")
    if not isinstance(compat, dict):
        raise NotFoundError("Run not found")
    return task, compat


def get_run(user_id: uuid.UUID, run_id: str) -> dict:
    with session_scope() as session:
        task, _compat = _load_run(session, user_id, run_id)
        try:
            result = json.loads(task.result_summary or "{}")
        except json.JSONDecodeError as exc:
            raise NotFoundError("Run not found") from exc
        if not isinstance(result, dict):
            raise NotFoundError("Run not found")
        return result


def execute_action(session: Session, user_id: uuid.UUID, run_id: str, action_id: str) -> dict:
    _task, compat = _load_run(session, user_id, run_id)
    action = next(
        (
            action
            for card in compat.get("cards", [])
            for action in card.get("actions", [])
            if action.get("id") == action_id
        ),
        None,
    )
    if action is None:
        raise NotFoundError("Action not found")
    if action_id.startswith("reschedule:"):
        task_id = uuid.UUID(action["_task_id"])
        target = task_service.get_task(session, user_id, task_id)
        try:
            calendar_service.reschedule_task(
                session,
                user_id,
                target,
                version=action["_task_version"],
                start_at=datetime.fromisoformat(action["_new_start"]),
                due_at=None,
                by_ai=True,
            )
        except ValidationError as exc:
            raise ConflictError("固定事件不可调整或已过期", code="fixed_event") from exc
        session.commit()
        return {"applied": action_id, "task_id": str(task_id)}
    raise ValidationError("Unsupported action", code="unsupported_action")


def clear_runs() -> None:
    """Compatibility no-op: durable runs are intentionally not process-local."""
