from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_conversation_and_retryable_state_survive_session_reload(db_session, make_user) -> None:
    from app.models.agent_conversation import AgentTurn
    from app.modules.agent.conversation_service import accept_message, create_conversation

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="restart-1",
        text="任务",
    )
    turn.status = "stalled"
    db_session.commit()
    db_session.expunge_all()
    restored = db_session.get(AgentTurn, turn.id)
    assert restored.status == "stalled"
    assert restored.conversation_id == conversation.id
