"""Failed-chain retry preserves unrelated success and enforces retry policy."""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def test_retry_resets_only_retryable_failed_chain(db_session, make_user) -> None:
    from app.models.agent import AgentPlanStep
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import persist_plan
    from app.modules.agent.scheduler import retry_failed_chain
    from app.modules.agent.service import create_agent_task
    from app.modules.jobs import service as jobs_service

    user = make_user()
    task = create_agent_task(
        db_session, user_id=user.id, request_text="查询并分析", intent_key="articles.list_recent"
    )
    proposal = AgentTaskPlanProposal.model_validate(
        {
            "objective": "查询并分析",
            "steps": [
                {
                    "step_key": "step_query",
                    "title": "查询",
                    "responsibility": "查询文章",
                    "tool_name": "posts.list_recent",
                    "operation_type": "query",
                    "arguments": {"limit": 2},
                    "depends_on": [],
                    "input_source": "current_message",
                    "expected_output": "文章 ID",
                    "requires_confirmation": False,
                },
                {
                    "step_key": "step_analyze",
                    "title": "分析",
                    "responsibility": "分析文章",
                    "tool_name": "content.extract_metadata",
                    "operation_type": "analyze",
                    "arguments": {},
                    "depends_on": ["step_query"],
                    "input_source": "dependency",
                    "expected_output": "分析提案",
                    "requires_confirmation": False,
                },
            ],
        }
    )
    plan = persist_plan(db_session, task=task, proposal=proposal)
    steps = {
        step.step_key: step
        for step in db_session.scalars(
            select(AgentPlanStep).where(AgentPlanStep.plan_id == plan.id)
        ).all()
    }
    steps["step_query"].status = "success"
    steps["step_analyze"].status = "failed"
    steps["step_analyze"].error_retryable = True
    steps["step_analyze"].attempt_count = 1
    plan.status = "partial_success"
    task.status = "partial_success"
    jobs_service.transition(db_session, task.job, status="completed")

    retry_failed_chain(db_session, user_id=user.id, plan_id=plan.id)
    assert steps["step_query"].status == "success"
    assert steps["step_analyze"].status == "pending"
    assert plan.status == "pending"
