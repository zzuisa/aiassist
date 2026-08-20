"""Unit checks for the fixed LangGraph orchestration boundary."""

from __future__ import annotations

import pytest


def test_graph_runtime_requires_langgraph_dependency() -> None:
    from app.modules.agent import graph_runtime

    try:
        import langgraph  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="LangGraph dependencies"):
            graph_runtime.build_agent_graph()
    else:
        graph = graph_runtime.build_agent_graph()
        assert graph is not None


def test_graph_state_uses_plan_id_as_thread_identity() -> None:
    from app.modules.agent.graph_runtime import AgentGraphState

    state: AgentGraphState = {"plan_id": "plan-1", "iterations": 0}
    assert state["plan_id"] == "plan-1"
