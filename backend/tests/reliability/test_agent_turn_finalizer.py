from __future__ import annotations

import pytest

pytestmark = [pytest.mark.reliability]


def test_top_level_failure_persists_terminal_turn_and_job(db_session, make_user) -> None:
    from app.models.foundation import AsyncJob
    from app.modules.agent.conversation_service import (
        accept_message,
        create_conversation,
        finalize_turn_failure,
    )

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="failure-1",
        text="任务",
    )
    finalize_turn_failure(db_session, turn.id, RuntimeError("private detail"))
    assert turn.status == "failed"
    assert "private detail" not in turn.error_message
    assert db_session.get(AsyncJob, turn.job_id).status == "failed"
