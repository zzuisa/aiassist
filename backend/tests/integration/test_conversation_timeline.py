from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def test_messages_remain_ordered_and_attached_to_owned_conversation(db_session, make_user) -> None:
    from app.models.agent_conversation import AgentMessage
    from app.modules.agent.conversation_service import (
        accept_message,
        create_conversation,
        execute_turn,
    )

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="timeline-1",
        text="hi",
    )
    execute_turn(db_session, turn.id)
    rows = list(
        db_session.scalars(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation.id)
            .order_by(AgentMessage.created_at, AgentMessage.id)
        ).all()
    )
    assert [row.role for row in rows] == ["user", "assistant"]
    assert rows[1].reply_to_id == rows[0].id
