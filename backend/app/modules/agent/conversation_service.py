"""Durable conversation/message/turn acceptance and owned lookups.

``accept_message`` is the single entry point that persists a user message and
opens its Turn. Per data-model.md Transaction Boundary §1, the Conversation
(if newly created), Message, Turn, Job, and outbox event all commit together
in the CALLER's transaction — this module never calls ``session.commit()``,
matching the convention in ``app/modules/agent/service.py``. Routing, tool
execution, and reply generation are later phases (worker Turn execution); this
module only guarantees the message/turn exist durably before any of that runs.

Every read filters by ``user_id`` — there is no cross-user visibility path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.agent_conversation import AgentConversation, AgentMessage, AgentTurn
from app.modules.jobs import service as jobs_service
from app.services.outbox.publisher import append_event

MAX_MESSAGE_TEXT_LENGTH = 4000
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


def create_conversation(
    session: Session,
    *,
    user_id: uuid.UUID,
    title: str | None = None,
) -> AgentConversation:
    conversation = AgentConversation(
        user_id=user_id,
        title=title,
        status="active",
        context_json={},
    )
    session.add(conversation)
    session.flush()
    return conversation


def get_owned_conversation(
    session: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> AgentConversation:
    conversation = session.get(AgentConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise NotFoundError("Conversation not found")
    return conversation


def list_owned_conversations(
    session: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> list[AgentConversation]:
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)
    stmt = select(AgentConversation).where(AgentConversation.user_id == user_id)
    if status is not None:
        stmt = stmt.where(AgentConversation.status == status)
    stmt = stmt.order_by(
        AgentConversation.last_message_at.desc().nulls_last(),
        AgentConversation.created_at.desc(),
    ).limit(limit)
    return list(session.scalars(stmt).all())


def get_owned_turn(session: Session, user_id: uuid.UUID, turn_id: uuid.UUID) -> AgentTurn:
    turn = session.get(AgentTurn, turn_id)
    if turn is None:
        raise NotFoundError("Turn not found")
    conversation = session.get(AgentConversation, turn.conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise NotFoundError("Turn not found")
    return turn


def list_active_turns(
    session: Session, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[AgentTurn]:
    get_owned_conversation(session, user_id, conversation_id)
    return list(
        session.scalars(
            select(AgentTurn)
            .where(
                AgentTurn.conversation_id == conversation_id,
                AgentTurn.status.notin_(
                    ("success", "partial_success", "failed", "stalled", "cancelled")
                ),
            )
            .order_by(AgentTurn.created_at)
        ).all()
    )


def list_conversation_messages(
    session: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    cursor: uuid.UUID | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> tuple[list[AgentMessage], uuid.UUID | None]:
    """Return one page of owned messages, oldest-after-cursor first."""
    get_owned_conversation(session, user_id, conversation_id)
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)
    stmt = select(AgentMessage).where(AgentMessage.conversation_id == conversation_id)
    if cursor is not None:
        anchor = session.get(AgentMessage, cursor)
        if anchor is not None and anchor.conversation_id == conversation_id:
            stmt = stmt.where(
                tuple_(AgentMessage.created_at, AgentMessage.id)
                > tuple_(anchor.created_at, anchor.id)  # type: ignore[arg-type]
            )
    stmt = stmt.order_by(AgentMessage.created_at, AgentMessage.id).limit(limit + 1)
    rows = list(session.scalars(stmt).all())
    next_cursor: uuid.UUID | None = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1].id
        rows = rows[:limit]
    return rows, next_cursor


def _find_turn_for_client_message(
    session: Session,
    user_id: uuid.UUID,
    client_message_id: str,
) -> AgentTurn | None:
    message = session.scalar(
        select(AgentMessage).where(
            AgentMessage.user_id == user_id,
            AgentMessage.client_message_id == client_message_id,
        )
    )
    if message is None:
        return None
    turn = session.scalar(select(AgentTurn).where(AgentTurn.user_message_id == message.id))
    return turn


def accept_message(
    session: Session,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_message_id: str,
    text: str,
) -> AgentTurn:
    """Durably accept one user message, idempotent on ``client_message_id``.

    Creates the AgentMessage, its AgentTurn, a paired AsyncJob, and an outbox
    event in this single caller-owned transaction. A retried delivery with the
    same ``client_message_id`` for this user returns the SAME Turn rather than
    creating a duplicate — no model/tool call has necessarily happened yet,
    but the durable record is guaranteed to exist exactly once.
    """
    normalized = text.strip()
    if not normalized:
        raise ValidationError("Message text is required", code="agent_message_text_empty")
    if len(normalized) > MAX_MESSAGE_TEXT_LENGTH:
        raise ValidationError("Message text is too long", code="agent_message_text_too_long")
    client_message_id = client_message_id.strip()
    if not client_message_id:
        raise ValidationError(
            "client_message_id is required", code="agent_client_message_id_empty"
        )

    conversation = get_owned_conversation(session, user_id, conversation_id)

    existing_turn = _find_turn_for_client_message(session, user_id, client_message_id)
    if existing_turn is not None:
        if existing_turn.conversation_id != conversation_id:
            raise ValidationError(
                "client_message_id was already used in a different conversation",
                code="agent_client_message_id_conflict",
            )
        return existing_turn

    message = AgentMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        kind="text",
        content_json={"text": normalized},
        client_message_id=client_message_id,
    )
    session.add(message)
    session.flush()

    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="agent.conversation_turn",
        entity_type="agent_conversation",
        entity_id=conversation.id,
        idempotency_key=f"agent-turn:{user_id}:{client_message_id}",
        max_retries=1,
    )

    turn = AgentTurn(
        conversation_id=conversation.id,
        user_message_id=message.id,
        job_id=job.id,
        status="accepted",
        retry_count=0,
    )
    session.add(turn)
    session.flush()

    now = datetime.now(UTC)
    conversation.last_message_at = now
    conversation.status = "active"

    append_event(
        session,
        event_type="agent.turn_accepted",
        aggregate_type="agent_turn",
        aggregate_id=turn.id,
        routing_key="agent.conversation",
        payload={
            "turn_id": str(turn.id),
            "conversation_id": str(conversation.id),
            "user_message_id": str(message.id),
            "job_id": str(job.id),
        },
        user_id=user_id,
    )
    session.flush()
    return turn
