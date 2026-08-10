"""Agent runtime state survives loss of process-local ORM state."""

from __future__ import annotations

from sqlalchemy import select


def test_task_run_status_and_records_survive_session_reset(db_session, make_user) -> None:
    from app.models.agent import AgentRun, AgentTask, ExecutionRecord
    from app.modules.agent.service import create_agent_task, execute_query_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="当前有多少分类",
        intent_key="taxonomy.categories",
    )
    db_session.commit()
    execute_query_task(db_session, task.id)
    db_session.commit()
    task_id = task.id
    db_session.expunge_all()

    recovered = db_session.get(AgentTask, task_id)
    runs = list(db_session.scalars(select(AgentRun).where(AgentRun.task_id == task_id)).all())
    records = list(
        db_session.scalars(select(ExecutionRecord).where(ExecutionRecord.task_id == task_id)).all()
    )
    assert recovered is not None and recovered.status == "success"
    assert len(runs) == 1 and runs[0].status == "success"
    assert len(records) == 1 and records[0].status == "success"
