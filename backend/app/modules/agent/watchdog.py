"""Locked repair for conversation Turns whose workers stopped heartbeating."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent_conversation import AgentTurn
from app.models.foundation import AsyncJob
from app.modules.agent.status import CONVERSATION_TURN_UPDATED, publish_conversation_event
from app.modules.jobs import service as jobs_service


def repair_stalled_turns(session: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=get_settings().agent_turn_heartbeat_timeout_seconds)
    session.flush()
    turns = list(
        session.scalars(
            select(AgentTurn)
            .where(
                AgentTurn.status.in_(("routing", "executing")),
                or_(AgentTurn.last_heartbeat_at < cutoff, AgentTurn.last_heartbeat_at.is_(None)),
            )
            .with_for_update(skip_locked=True)
        ).all()
    )
    for turn in turns:
        turn.status = "stalled"
        turn.error_code = "agent_turn_stalled"
        turn.error_message = "处理长时间没有进展，可以安全重试。"
        turn.current_step = "处理已停滞"
        turn.finished_at = current
        job = session.get(AsyncJob, turn.job_id)
        if job is not None:
            jobs_service.transition(
                session,
                job,
                status="failed",
                current_step="处理已停滞",
                error_code=turn.error_code,
                error_message=turn.error_message,
                error_retryable=True,
            )
        publish_conversation_event(
            session,
            turn,
            event_type=CONVERSATION_TURN_UPDATED,
            error_message=turn.error_message,
        )
    session.flush()
    return len(turns)
