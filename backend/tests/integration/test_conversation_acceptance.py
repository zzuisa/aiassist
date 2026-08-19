"""Message-idempotency and ownership-isolation for the durable accept-message transaction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


def test_accept_message_persists_conversation_message_turn_job_and_outbox(
    db_session, make_user
) -> None:
    from app.models.agent_conversation import AgentMessage
    from app.models.foundation import AsyncJob, OutboxEvent
    from app.modules.agent import conversation_service
    from sqlalchemy import select

    user = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=user.id)
    db_session.commit()

    client_message_id = str(uuid.uuid4())
    turn = conversation_service.accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id=client_message_id,
        text="嗨，帮我找最近十篇文章",
    )
    db_session.commit()

    assert turn.status == "accepted"
    message = db_session.get(AgentMessage, turn.user_message_id)
    assert message is not None
    assert message.content_json["text"] == "嗨，帮我找最近十篇文章"
    assert message.client_message_id == client_message_id

    job = db_session.get(AsyncJob, turn.job_id)
    assert job is not None
    assert job.job_type == "agent.conversation_turn"

    outbox_row = db_session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == turn.id))
    assert outbox_row is not None
    assert outbox_row.event_type == "agent.turn_accepted"
    assert outbox_row.payload_json["turn_id"] == str(turn.id)

    conversation_after = db_session.get(type(conversation), conversation.id)
    assert conversation_after.last_message_at is not None


def test_accept_message_is_idempotent_on_client_message_id(db_session, make_user) -> None:
    from app.modules.agent import conversation_service

    user = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=user.id)
    db_session.commit()

    client_message_id = str(uuid.uuid4())
    first = conversation_service.accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id=client_message_id,
        text="重复发送的第一次",
    )
    db_session.commit()

    second = conversation_service.accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id=client_message_id,
        text="重复发送的第一次",
    )
    db_session.commit()

    assert first.id == second.id
    assert first.user_message_id == second.user_message_id


def test_accept_message_idempotency_rejects_conversation_switch(db_session, make_user) -> None:
    from app.core.errors import ValidationError
    from app.modules.agent import conversation_service

    user = make_user()
    conversation_a = conversation_service.create_conversation(db_session, user_id=user.id)
    conversation_b = conversation_service.create_conversation(db_session, user_id=user.id)
    db_session.commit()

    client_message_id = str(uuid.uuid4())
    conversation_service.accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation_a.id,
        client_message_id=client_message_id,
        text="first conversation",
    )
    db_session.commit()

    with pytest.raises(ValidationError):
        conversation_service.accept_message(
            db_session,
            user_id=user.id,
            conversation_id=conversation_b.id,
            client_message_id=client_message_id,
            text="second conversation",
        )


def test_accept_message_rejects_empty_and_oversized_text(db_session, make_user) -> None:
    from app.core.errors import ValidationError
    from app.modules.agent import conversation_service

    user = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=user.id)
    db_session.commit()

    with pytest.raises(ValidationError):
        conversation_service.accept_message(
            db_session,
            user_id=user.id,
            conversation_id=conversation.id,
            client_message_id=str(uuid.uuid4()),
            text="   ",
        )

    with pytest.raises(ValidationError):
        conversation_service.accept_message(
            db_session,
            user_id=user.id,
            conversation_id=conversation.id,
            client_message_id=str(uuid.uuid4()),
            text="x" * 4001,
        )


def test_conversation_and_turn_lookups_are_owner_isolated(db_session, make_user) -> None:
    from app.core.errors import NotFoundError
    from app.modules.agent import conversation_service

    owner = make_user()
    other = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=owner.id)
    db_session.commit()

    turn = conversation_service.accept_message(
        db_session,
        user_id=owner.id,
        conversation_id=conversation.id,
        client_message_id=str(uuid.uuid4()),
        text="owner-only message",
    )
    db_session.commit()

    # Owner can read their own conversation/turn.
    assert conversation_service.get_owned_conversation(db_session, owner.id, conversation.id)
    assert conversation_service.get_owned_turn(db_session, owner.id, turn.id).id == turn.id

    # A different authenticated user gets NotFoundError, never someone else's data.
    with pytest.raises(NotFoundError):
        conversation_service.get_owned_conversation(db_session, other.id, conversation.id)
    with pytest.raises(NotFoundError):
        conversation_service.get_owned_turn(db_session, other.id, turn.id)

    owned_list = conversation_service.list_owned_conversations(db_session, other.id)
    assert conversation.id not in {c.id for c in owned_list}


def test_list_conversation_messages_is_owner_isolated_and_paginates(db_session, make_user) -> None:
    from app.core.errors import NotFoundError
    from app.modules.agent import conversation_service

    owner = make_user()
    other = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=owner.id)
    db_session.commit()

    for _ in range(3):
        conversation_service.accept_message(
            db_session,
            user_id=owner.id,
            conversation_id=conversation.id,
            client_message_id=str(uuid.uuid4()),
            text="msg",
        )
    db_session.commit()

    page, next_cursor = conversation_service.list_conversation_messages(
        db_session, owner.id, conversation.id, limit=2
    )
    assert len(page) == 2
    assert next_cursor is not None

    rest, next_cursor_2 = conversation_service.list_conversation_messages(
        db_session, owner.id, conversation.id, cursor=next_cursor, limit=2
    )
    assert len(rest) == 1
    assert next_cursor_2 is None

    with pytest.raises(NotFoundError):
        conversation_service.list_conversation_messages(db_session, other.id, conversation.id)


def test_recent_message_window_loads_newest_first_and_pages_backward(db_session, make_user) -> None:
    from app.modules.agent import conversation_service

    owner = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=owner.id)
    message_ids = []
    for index in range(5):
        turn = conversation_service.accept_message(
            db_session,
            user_id=owner.id,
            conversation_id=conversation.id,
            client_message_id=str(uuid.uuid4()),
            text=f"msg-{index}",
        )
        message_ids.append(turn.user_message_id)
        db_session.flush()
    db_session.commit()

    recent, before = conversation_service.list_recent_conversation_messages(
        db_session, owner.id, conversation.id, limit=2
    )
    assert [message.id for message in recent] == message_ids[-2:]
    assert before == message_ids[-2]

    earlier, before_2 = conversation_service.list_recent_conversation_messages(
        db_session, owner.id, conversation.id, before=before, limit=2
    )
    assert [message.id for message in earlier] == message_ids[1:3]
    assert before_2 == message_ids[1]


def test_active_turns_hide_expired_failures_and_keep_only_latest_unresolved_retry(
    db_session, make_user
) -> None:
    from app.modules.agent import conversation_service

    owner = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=owner.id)

    def make_turn(label: str):
        return conversation_service.accept_message(
            db_session,
            user_id=owner.id,
            conversation_id=conversation.id,
            client_message_id=str(uuid.uuid4()),
            text=label,
        )

    expired = make_turn("expired")
    expired.status = "failed"
    expired.finished_at = datetime.now(UTC) - timedelta(days=2)

    unresolved = make_turn("unresolved")
    unresolved.status = "failed"
    unresolved.finished_at = datetime.now(UTC) - timedelta(hours=1)

    superseded = make_turn("superseded")
    superseded.status = "failed"
    superseded.finished_at = datetime.now(UTC) - timedelta(minutes=30)
    retry = make_turn("retry")
    retry.retry_of_id = superseded.id
    db_session.commit()

    visible = conversation_service.list_active_turns(db_session, owner.id, conversation.id)

    assert {turn.id for turn in visible} == {unresolved.id, retry.id}


def test_accept_message_requires_owned_conversation(db_session, make_user) -> None:
    from app.core.errors import NotFoundError
    from app.modules.agent import conversation_service

    owner = make_user()
    intruder = make_user()
    conversation = conversation_service.create_conversation(db_session, user_id=owner.id)
    db_session.commit()

    with pytest.raises(NotFoundError):
        conversation_service.accept_message(
            db_session,
            user_id=intruder.id,
            conversation_id=conversation.id,
            client_message_id=str(uuid.uuid4()),
            text="should not be accepted",
        )
