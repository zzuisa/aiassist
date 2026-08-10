"""Analysis orchestration uses 006 bindings, bounded fan-out and honest output."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def test_small_single_tool_request_uses_one_agent_but_large_batch_fans_out() -> None:
    from app.modules.agent.service import analysis_run_count

    assert analysis_run_count(object_count=3, selected_agent_count=1, max_concurrency=4) == 1
    assert analysis_run_count(object_count=25, selected_agent_count=1, max_concurrency=4) == 4
    assert analysis_run_count(object_count=6, selected_agent_count=2, max_concurrency=4) == 2


def test_effective_binding_comes_from_the_006_manifest_boundary() -> None:
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    binding = resolve_builtin_agent("editor-agent")

    assert binding.agent_key == "editor-agent"
    assert binding.version_ref.startswith("blog-agents.1:")
    assert binding.enabled is True
    assert binding.responsibility


def test_analysis_selection_reuses_existing_value_and_capability_gates(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.modules.agent.service import select_analysis_agents
    from app.modules.posts import orchestrator

    captured: dict[str, object] = {}

    def fake_build_plan(title: str, content: str, *, instruction: str):
        captured.update(title=title, content=content, instruction=instruction)
        return SimpleNamespace(
            selected_agents=["logic-agent", "data-agent", "scene-image-agent"],
            skipped_agents=[
                {
                    "agent": "illustration-agent",
                    "reason_code": "CAPABILITY_UNAVAILABLE",
                    "reason": "imagegen 未启用",
                }
            ],
        )

    monkeypatch.setattr(orchestrator, "build_plan", fake_build_plan)
    selected, skipped = select_analysis_agents(
        [{"id": "1", "title": "文章", "markdown": "正文关系与数据"}],
        "分析文章",
    )

    assert selected == ["logic-agent", "data-agent"]
    assert skipped[0]["reason_code"] == "CAPABILITY_UNAVAILABLE"
    assert captured == {
        "title": "文章",
        "content": "正文关系与数据",
        "instruction": "分析文章",
    }


def test_analysis_tools_are_registered_as_read_only_proposal_capabilities() -> None:
    from app.modules.agent.registry import tool_registry

    body_tool = tool_registry.get("posts.read_body")
    analysis_tool = tool_registry.get("content.extract_metadata")

    assert body_tool.type == analysis_tool.type == "read"
    assert "不写回" in analysis_tool.responsibility


def test_result_normalization_deduplicates_generated_terms_without_claiming_save() -> None:
    from app.modules.agent.service import normalize_analysis_value

    normalized = normalize_analysis_value(
        {
            "post_id": "post-1",
            "tags": [" Agent ", "agent", "", None],
            "keywords": ["并行", " 并行 ", "可靠性"],
            "summary": "  已生成  ",
        },
        expected_post_id="post-1",
    )

    assert normalized == {
        "post_id": "post-1",
        "tags": ["Agent"],
        "keywords": ["并行", "可靠性"],
        "summary": "已生成",
        "save_status": "generated_not_saved",
    }
