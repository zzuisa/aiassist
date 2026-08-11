"""Versioned Agent status events on the existing durable jobs stream."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent import AgentRun, AgentTask
from app.models.agent_conversation import AgentTurn
from app.models.foundation import AsyncJob, AsyncJobEvent

EVENT_NAME = "agent.status_changed"
SCHEMA_VERSION = "agent-status-event.v1"

CONVERSATION_EVENT_SCHEMA_VERSION = "conversation-event.v1"
CONVERSATION_MESSAGE_CREATED = "conversation.message_created"
CONVERSATION_TURN_UPDATED = "conversation.turn_updated"


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def progress_payload(
    current: int | None,
    total: int | None,
    stage_label: str | None,
) -> dict[str, int | str | None] | None:
    """Return numeric progress only when both values are known."""
    if current is None or total is None:
        return None
    return {
        "current": current,
        "total": total,
        "stage_label": stage_label,
    }


def build_status_payload(
    task: AgentTask,
    run: AgentRun,
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build the public payload; private prompts and tool parameters are excluded."""
    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": "agent_status_changed",
        "task_id": str(task.id),
        "job_id": str(task.job_id),
        "trace_id": task.job.trace_id,
        "agent": {
            "agent_id": str(run.id),
            "parent_agent_id": str(run.parent_run_id) if run.parent_run_id else None,
            "agent_key": run.agent_key,
            "agent_version": run.agent_version,
            "agent_name": run.agent_name,
            "responsibility": run.responsibility,
            "current_task": run.current_task,
            "status": run.status,
            "current_tool": run.current_tool,
            "progress": progress_payload(
                run.progress_current,
                run.progress_total,
                run.stage_label,
            ),
            "result_summary": run.result_summary,
            "error_message": run.error_message,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
        },
        "timestamp": _iso(timestamp or datetime.now(UTC)),
    }


def publish_status(
    session: Session,
    task: AgentTask,
    run: AgentRun,
) -> AsyncJobEvent:
    """Append a replayable status event in the caller's transaction."""
    session.flush()
    job = session.get(AsyncJob, task.job_id)
    if job is None:  # pragma: no cover - protected by the task foreign key
        raise RuntimeError("Agent task has no paired async job")
    event = AsyncJobEvent(
        user_id=task.user_id,
        job_id=task.job_id,
        job_version=job.version,
        event_type=EVENT_NAME,
        payload_json=build_status_payload(task, run),
    )
    session.add(event)
    session.flush()
    return event


def build_conversation_event_payload(
    turn: AgentTurn,
    *,
    event_type: str,
    message_id: uuid.UUID | None = None,
    stage_label: str | None = None,
    capability_name: str | None = None,
    result_summary: str | None = None,
    error_message: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build a ``conversation-event.v1`` payload.

    Deliberately excludes anything not in the contract: no endpoint, no
    credential, no prompt/reasoning text, and no raw MCP tool output — only
    the safe, bounded-length summary/error strings the contract allows.
    """
    if event_type not in (CONVERSATION_MESSAGE_CREATED, CONVERSATION_TURN_UPDATED):
        raise ValueError(f"Unknown conversation event_type: {event_type}")
    return {
        "schema_version": CONVERSATION_EVENT_SCHEMA_VERSION,
        "event_type": event_type,
        "conversation_id": str(turn.conversation_id),
        "turn_id": str(turn.id),
        "message_id": str(message_id) if message_id is not None else None,
        "status": turn.status,
        "stage_label": (stage_label or turn.current_step or None),
        "capability_name": capability_name,
        "result_summary": result_summary[:1000] if result_summary else None,
        "error_message": (
            (error_message or turn.error_message)[:1000]
            if (error_message or turn.error_message)
            else None
        ),
        "timestamp": _iso(timestamp or datetime.now(UTC)) or datetime.now(UTC).isoformat(),
    }


def publish_conversation_event(
    session: Session,
    turn: AgentTurn,
    *,
    event_type: str,
    message_id: uuid.UUID | None = None,
    stage_label: str | None = None,
    capability_name: str | None = None,
    result_summary: str | None = None,
    error_message: str | None = None,
) -> AsyncJobEvent:
    """Append a replayable conversation event on the Turn's paired job stream."""
    session.flush()
    job = session.get(AsyncJob, turn.job_id)
    if job is None:  # pragma: no cover - protected by the turn foreign key
        raise RuntimeError("Agent turn has no paired async job")
    payload = build_conversation_event_payload(
        turn,
        event_type=event_type,
        message_id=message_id,
        stage_label=stage_label,
        capability_name=capability_name,
        result_summary=result_summary,
        error_message=error_message,
    )
    event = AsyncJobEvent(
        user_id=job.user_id,
        job_id=turn.job_id,
        job_version=job.version,
        event_type=event_type,
        payload_json=payload,
    )
    session.add(event)
    session.flush()
    return event
