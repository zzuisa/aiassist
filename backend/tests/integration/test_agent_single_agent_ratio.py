"""Simple single-tool queries overwhelmingly use one Agent run."""

from __future__ import annotations

from sqlalchemy import func, select


def test_simple_query_single_agent_ratio_is_at_least_ninety_five_percent(
    db_session,
    make_user,
) -> None:
    from app.models.agent import AgentRun
    from app.modules.agent.service import create_agent_task, execute_query_task

    user = make_user()
    task_ids = []
    for _index in range(20):
        task = create_agent_task(
            db_session,
            user_id=user.id,
            request_text="当前有多少分类",
            intent_key="taxonomy.categories",
        )
        db_session.flush()
        execute_query_task(db_session, task.id)
        task_ids.append(task.id)
    counts = dict(
        db_session.execute(
            select(AgentRun.task_id, func.count(AgentRun.id))
            .where(AgentRun.task_id.in_(task_ids))
            .group_by(AgentRun.task_id)
        ).all()
    )
    ratio = sum(counts.get(task_id) == 1 for task_id in task_ids) / len(task_ids)
    assert ratio >= 0.95
