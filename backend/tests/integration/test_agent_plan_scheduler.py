"""Coordinator claims parallel roots and only releases satisfied descendants."""

from __future__ import annotations

import threading
import time
import uuid

import pytest

pytestmark = [pytest.mark.integration]


def test_ready_batch_uses_bounded_real_concurrency(monkeypatch) -> None:
    from app.modules.agent import graph_runtime

    lock = threading.Lock()
    active = 0
    maximum = 0

    def execute(step_id: uuid.UUID) -> uuid.UUID:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return step_id

    monkeypatch.setattr(graph_runtime, "_execute_claimed_step", execute)
    ids = [uuid.uuid4() for _ in range(4)]
    result = graph_runtime._execute_ready(
        {"plan_id": str(uuid.uuid4()), "ready_step_ids": [str(value) for value in ids]}
    )
    assert result == {"ready_step_ids": []}
    assert maximum > 1


def test_scheduler_claims_ready_steps_and_propagates_failure(db_session, make_user) -> None:
    from app.models.agent import AgentPlanStep
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import persist_plan
    from app.modules.agent.scheduler import coordinate_plan
    from app.modules.agent.service import create_agent_task

    user = make_user()
    task = create_agent_task(
        db_session, user_id=user.id, request_text="并行查询", intent_key="articles.list_recent"
    )
    common = {
        "responsibility": "执行查询",
        "operation_type": "query",
        "arguments": {},
        "input_source": "current_message",
        "expected_output": "查询结果",
        "requires_confirmation": False,
    }
    proposal = AgentTaskPlanProposal.model_validate(
        {
            "objective": "并行查询后分析",
            "steps": [
                {
                    **common,
                    "step_key": "step_posts",
                    "title": "查询文章",
                    "tool_name": "posts.list_recent",
                    "arguments": {"limit": 2},
                    "depends_on": [],
                },
                {
                    **common,
                    "step_key": "step_tags",
                    "title": "查询标签",
                    "tool_name": "taxonomy.tags",
                    "depends_on": [],
                },
                {
                    **common,
                    "step_key": "step_categories",
                    "title": "查询分类",
                    "tool_name": "taxonomy.categories",
                    "depends_on": ["step_posts"],
                    "input_source": "dependency",
                },
            ],
        }
    )
    plan = persist_plan(db_session, task=task, proposal=proposal)
    roots = coordinate_plan(db_session, plan.id)
    assert len(roots) == 2
    rows = {step.step_key: step for step in db_session.query(AgentPlanStep).all()}
    rows["step_posts"].status = "failed"
    rows["step_posts"].error_retryable = True
    rows["step_posts"].finished_at = plan.created_at
    rows["step_tags"].status = "success"
    rows["step_tags"].finished_at = plan.created_at
    assert coordinate_plan(db_session, plan.id) == []
    assert rows["step_categories"].status == "blocked"
    assert plan.status == "partial_success"
