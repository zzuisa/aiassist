from __future__ import annotations

import pytest
from app.core.errors import ValidationError
from app.modules.agent.planning_schemas import AgentTaskPlanProposal


def _proposal(steps: list[dict]) -> AgentTaskPlanProposal:
    return AgentTaskPlanProposal.model_validate(
        {"schema_version": "agent-task-plan.v1", "objective": "测试计划", "steps": steps}
    )


def _step(key: str, *, depends_on: list[str] | None = None) -> dict:
    return {
        "step_key": key,
        "title": key,
        "responsibility": "完成测试工作",
        "tool_name": "posts.list_recent",
        "operation_type": "query",
        "arguments": {"limit": 2},
        "depends_on": depends_on or [],
        "input_source": "dependency" if depends_on else "current_message",
        "expected_output": "文章范围",
        "requires_confirmation": False,
    }


def test_plan_schema_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError):
        _proposal([_step("step_one"), _step("step_one")])


def test_plan_policy_rejects_cycles() -> None:
    from app.modules.agent.planning_service import validate_plan_graph

    proposal = _proposal(
        [_step("step_one", depends_on=["step_two"]), _step("step_two", depends_on=["step_one"])]
    )
    with pytest.raises(ValidationError, match="cycle"):
        validate_plan_graph(proposal, max_depth=4)


def test_plan_policy_accepts_parallel_dag() -> None:
    from app.modules.agent.planning_service import validate_plan_graph

    proposal = _proposal(
        [_step("step_one"), _step("step_two"), _step("step_three", depends_on=["step_one"])]
    )
    validate_plan_graph(proposal, max_depth=4)


def test_analysis_without_context_gets_query_dependency_fallback() -> None:
    from app.modules.agent.planning_service import _seed_proposal
    from app.modules.agent.registry import tool_registry

    proposal = _seed_proposal(
        objective="找最近文章并分析关键词",
        tool_name="content.extract_metadata",
        arguments={},
        tool=tool_registry.get("content.extract_metadata"),
        has_context_scope=False,
        can_query=True,
        query_arguments={"limit": 10},
    )
    assert [step.tool_name for step in proposal.steps] == [
        "posts.list_recent",
        "content.extract_metadata",
    ]
    assert proposal.steps[1].depends_on == ["step_query"]


def test_scope_policy_rejects_root_analysis_without_context() -> None:
    from app.modules.agent.planning_service import _validate_scope_flow

    proposal = _proposal(
        [
            {
                **_step("step_analyze"),
                "tool_name": "content.extract_metadata",
                "operation_type": "analyze",
                "arguments": {},
                "expected_output": "分析提案",
            }
        ]
    )
    with pytest.raises(ValidationError, match="scope"):
        _validate_scope_flow(proposal, has_context_scope=False)
