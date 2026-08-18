from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from app.modules.agent.planning_schemas import AgentTaskPlanProposal

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT.parent / "specs" / "011-collaborative-agent-orchestration" / "contracts"


def test_planning_proposal_matches_versioned_contract() -> None:
    payload = {
        "schema_version": "agent-task-plan.v1",
        "objective": "查询后分析",
        "steps": [
            {
                "step_key": "step_query",
                "title": "查询文章",
                "responsibility": "取得文章范围",
                "tool_name": "posts.list_recent",
                "operation_type": "query",
                "arguments": {"limit": 3},
                "depends_on": [],
                "input_source": "current_message",
                "expected_output": "文章 ID",
                "requires_confirmation": False,
            }
        ],
    }
    schema = json.loads((CONTRACTS / "agent-task-plan.v1.json").read_text())
    jsonschema.validate(payload, schema)
    assert AgentTaskPlanProposal.model_validate(payload).schema_version == "agent-task-plan.v1"


def test_planning_contract_rejects_hidden_reasoning() -> None:
    payload = {
        "schema_version": "agent-task-plan.v1",
        "objective": "测试",
        "steps": [],
        "reasoning": "private",
    }
    schema = json.loads((CONTRACTS / "agent-task-plan.v1.json").read_text())
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("contract unexpectedly accepted hidden reasoning")
