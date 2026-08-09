"""Contract checks for durable Agent status events."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

pytestmark = [pytest.mark.contract]


def test_agent_status_event_matches_versioned_contract(db_session, make_user) -> None:
    from app.models.agent import AgentRun
    from app.modules.agent.service import create_agent_task
    from app.modules.agent.status import build_status_payload

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="给我最近 10 篇文章",
        intent_key="articles.list_recent",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="article-query-agent",
        agent_version="runtime-query-v1",
        agent_name="文章查询 Agent",
        responsibility="查询文章元数据",
        current_task=task.request_text,
        status="running",
        progress_current=1,
        progress_total=10,
        stage_label="正在查询",
    )
    db_session.add(run)
    db_session.flush()

    payload = build_status_payload(task, run)
    schema_path = (
        Path(__file__).parents[3]
        / "specs/007-self-service-agent/contracts/schemas/agent-status-event.v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert len("agent.status_changed") <= 40
    assert payload["agent"]["status"] in {
        "pending",
        "running",
        "waiting_confirmation",
        "success",
        "partial_success",
        "failed",
        "skipped",
    }
