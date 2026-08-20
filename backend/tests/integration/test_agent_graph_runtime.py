"""LangGraph plan projection, cancellation, and recovery integration checks."""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def _plan(db_session, user):
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import persist_plan
    from app.modules.agent.service import create_agent_task

    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="查询并分析博客",
        intent_key="articles.list_recent",
    )
    proposal = AgentTaskPlanProposal.model_validate(
        {
            "objective": "查询并分析博客",
            "steps": [
                {
                    "step_key": "step_query",
                    "title": "查询博客",
                    "responsibility": "查询博客",
                    "tool_name": "posts.list_recent",
                    "operation_type": "query",
                    "arguments": {"limit": 2},
                    "depends_on": [],
                    "input_source": "current_message",
                    "expected_output": "博客列表",
                    "requires_confirmation": False,
                },
                {
                    "step_key": "step_analyze",
                    "title": "分析博客",
                    "responsibility": "分析博客",
                    "tool_name": "content.extract_metadata",
                    "operation_type": "analyze",
                    "arguments": {},
                    "depends_on": ["step_query"],
                    "input_source": "dependency",
                    "expected_output": "分析结果",
                    "requires_confirmation": False,
                },
            ],
        }
    )
    return persist_plan(db_session, task=task, proposal=proposal)


def test_plan_uses_durable_graph_thread_identity(db_session, make_user) -> None:
    plan = _plan(db_session, make_user())

    assert plan.graph_thread_id == str(plan.id)
    assert plan.runtime_state == "checkpointed"


def test_cancel_preserves_completed_effects_and_stops_future_steps(db_session, make_user) -> None:
    from app.models.agent import AgentPlanStep
    from app.modules.agent.planning_service import cancel_plan

    user = make_user()
    plan = _plan(db_session, user)
    steps = list(
        db_session.scalars(
            select(AgentPlanStep)
            .where(AgentPlanStep.plan_id == plan.id)
            .order_by(AgentPlanStep.position)
        ).all()
    )
    steps[0].status = "success"
    cancelled = cancel_plan(db_session, user_id=user.id, plan_id=plan.id)

    assert cancelled.status == "cancelled"
    assert cancelled.runtime_state == "checkpointed"
    assert steps[0].status == "success"
    assert steps[1].status == "cancelled"
