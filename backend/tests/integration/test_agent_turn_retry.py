from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_retry_is_owned_and_duplicate_click_is_idempotent(db_session, make_user) -> None:
    from app.modules.agent.conversation_service import (
        accept_message,
        create_conversation,
        retry_turn,
    )

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    original = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="retry-1",
        text="任务",
    )
    original.status = "stalled"
    first = retry_turn(db_session, user_id=user.id, turn_id=original.id)
    second = retry_turn(db_session, user_id=user.id, turn_id=original.id)
    assert first.id == second.id
    assert first.retry_of_id == original.id
