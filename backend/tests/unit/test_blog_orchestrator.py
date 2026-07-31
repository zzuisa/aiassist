from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _reload_settings_after_test(monkeypatch):
    yield
    from app.core.config import reload_settings

    reload_settings()


def test_short_article_does_not_start_visual_agents(monkeypatch):
    from app.core.config import reload_settings
    from app.modules.posts import orchestrator

    monkeypatch.setenv("BLOG_CAPABILITIES_JSON", json.dumps([
        {"name": "visualize", "enabled": True},
        {"name": "answers-charts", "enabled": True},
    ]))
    reload_settings()
    plan = orchestrator.build_plan("一句话", "这是一个结论。")

    assert plan.selected_agents == []
    assert all(item["reason_code"] == "LOW_REWRITE_VALUE" for item in plan.skipped_agents[:1])
    assert plan.assessment.visual_potential == 0


def test_rich_article_uses_shared_diagnosis_and_respects_capabilities(monkeypatch):
    from app.core.config import reload_settings
    from app.modules.posts import orchestrator

    monkeypatch.setenv("BLOG_CAPABILITIES_JSON", json.dumps([
        {"name": "visualize", "enabled": True},
        {"name": "answers-charts", "enabled": False},
    ]))
    reload_settings()
    content = (
        "# 背景\n\n"
        "首先记录 10 个样本，然后比较 20 个样本，最后达到 30%。\n"
        "补充记录 40、50、60 个样本。\n\n"
        "如果输入稳定，因此输出稳定；相比旧流程，新流程减少等待。\n\n"
        "## 结论\n\n建议按步骤执行。"
    )
    plan = orchestrator.build_plan("流程复盘", content)

    assert "logic-agent" in plan.selected_agents
    assert any(item["agent"] == "data-agent" and item["reason_code"] == "CAPABILITY_UNAVAILABLE" for item in plan.skipped_agents)
    assert plan.as_dict()["article_assessment"]["logical_complexity"] >= 2


def test_prompt_is_provider_neutral_and_payload_reuses_plan(monkeypatch):
    from app.core.config import reload_settings
    from app.modules.posts import orchestrator

    monkeypatch.setenv("BLOG_CAPABILITIES_JSON", "[]")
    reload_settings()
    plan = orchestrator.build_plan("标题", "一段足够长的正文。" * 50)
    system = orchestrator.build_system_prompt({}, plan, None)
    payload = orchestrator.build_user_payload(
        title="标题",
        content="正文",
        language="zh-CN",
        category="essay",
        target_audience=None,
        author_intent=None,
        options={},
        skill_config={},
        plan=plan,
    )

    assert "Claude CLI" in system
    assert "shared_analysis" in payload
    assert json.loads(payload)["available_capabilities"]
