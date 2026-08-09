"""Bounded in-task fan-out provides real concurrency with isolated scopes."""

from __future__ import annotations

import time

import pytest

pytestmark = [pytest.mark.integration]


def test_parallel_runs_have_disjoint_scopes_and_are_faster_than_serial(
    db_session, make_user
) -> None:
    from app.models.agent import AgentRun
    from app.modules.agent.runner import WorkItem, run_bounded
    from app.modules.agent.service import create_agent_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="批量分析 25 篇文章",
        intent_key="articles.analyze",
    )
    items = [
        WorkItem(key=str(index), input_scope={"object_ids": [str(index)]}) for index in range(25)
    ]
    runs = [
        AgentRun(
            task_id=task.id,
            agent_key="content-analysis-agent",
            agent_version="006-v1",
            agent_name=f"内容分析 Agent {index + 1}",
            responsibility="分析指定范围的文章",
            current_task="提取标签和关键词",
            input_scope_json=item.input_scope,
            allowed_tools=["posts.read_body"],
            status="pending",
        )
        for index, item in enumerate(items)
    ]
    db_session.add_all(runs)
    db_session.commit()

    def work(item: WorkItem) -> str:
        time.sleep(0.02)
        return item.key

    started = time.perf_counter()
    serial = run_bounded(items, work, max_concurrency=1)
    serial_elapsed = time.perf_counter() - started
    started = time.perf_counter()
    parallel = run_bounded(items, work, max_concurrency=4)
    parallel_elapsed = time.perf_counter() - started

    scopes = [set(run.input_scope_json["object_ids"]) for run in runs]
    assert all(
        not left.intersection(right) for i, left in enumerate(scopes) for right in scopes[i + 1 :]
    )
    assert all(result.status == "success" for result in serial.results + parallel.results)
    assert parallel_elapsed <= serial_elapsed * 0.5
