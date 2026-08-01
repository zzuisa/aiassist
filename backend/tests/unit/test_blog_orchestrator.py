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


def test_explicit_board_request_allows_visual_agent_for_essay(monkeypatch):
    from app.core.config import reload_settings
    from app.modules.posts import orchestrator

    monkeypatch.setenv("BLOG_CAPABILITIES_JSON", json.dumps([{"name": "visualize", "enabled": True}]))
    reload_settings()
    content = (
        "很多选择看似是效率问题，其实先取决于目标。\n\n"
        "当目标不清晰时，继续增加工具只会制造更多噪音。\n\n"
        "因此应先确认目标，再判断是否需要工具，最后复盘结果。"
    )
    plan = orchestrator.build_plan("一个关于选择的道理", content, instruction="请用板书式流程图梳理这段话的脉络")

    assert "logic-agent" in plan.selected_agents
    assert any("板书式" in item for item in plan.recommended_actions)


def test_reader_explainer_is_detected_without_user_prompt(monkeypatch):
    from app.core.config import reload_settings
    from app.modules.posts import orchestrator

    monkeypatch.setenv("BLOG_CAPABILITIES_JSON", json.dumps([{"name": "visualize", "enabled": True}]))
    reload_settings()
    content = (
        "水循环是水在海洋、陆地和大气之间不断移动的过程。\n\n"
        "1. 蒸发：太阳加热水体，液态水变成水蒸气。\n"
        "2. 凝结：水蒸气遇冷形成云。\n"
        "3. 降水：云中的水回到地面。\n"
        "4. 汇流：地表水最终回到河流和海洋。"
    )
    plan = orchestrator.build_plan("水循环：水如何在海洋、天空与陆地之间旅行", content)

    assert plan.reader_explainer is True
    assert plan.candidate_node_count == 4
    assert "logic-agent" in plan.selected_agents
    fallback = orchestrator.build_default_reader_visual(
        "水循环：水如何在海洋、天空与陆地之间旅行", content, plan
    )
    assert fallback is not None
    assert fallback["content"]["visual_plan"]["nodes"][0]["label"] == "蒸发"
    assert fallback["content"]["visual_plan"]["edges"][-1]["to"] == "step1"


def test_prose_analysis_gets_compact_reader_visual_without_instruction(monkeypatch):
    from app.core.config import reload_settings
    from app.modules.posts import orchestrator

    monkeypatch.setenv("BLOG_CAPABILITIES_JSON", json.dumps([{"name": "visualize", "enabled": True}]))
    reload_settings()
    content = (
        "美国试图通过人工智能投资吸引全球资金，但这也意味着资本市场对未来收益有很高预期。"
        "如果收益无法兑现，泡沫就可能面临重新定价。\n\n"
        "地缘冲突可能导致能源价格上升，进而增加进口国的通胀和外汇压力。"
        "一方面日本依赖进口能源，另一方面汇率下跌会提高进口成本。\n\n"
        "这些因素叠加后，作者认为风险可能从局部市场传导到美国金融市场，最终形成更大的危机。"
    )
    plan = orchestrator.build_plan("全球金融风险分析", content)

    assert plan.reader_explainer is True
    assert plan.candidate_node_count >= 1
    fallback = orchestrator.build_default_reader_visual("全球金融风险分析", content, plan)
    assert fallback is not None
    assert len(fallback["content"]["visual_plan"]["nodes"]) == plan.candidate_node_count
    assert fallback["content"]["visual_plan"]["nodes"][0]["detail"]
