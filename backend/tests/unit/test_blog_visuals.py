import io

from app.modules.posts.visuals import (
    enhancements_markdown,
    execute_enhancements,
    render_visual_plan_png,
)
from app.services.llm.schemas import (
    BlogAssessmentV1,
    BlogDecisionV1,
    BlogEnhancementResultV1,
    BlogOptimizedArticleV1,
    BlogQualityReportV1,
    BlogUsageV1,
)
from PIL import Image


def _result(enhancements):
    return BlogEnhancementResultV1(
        status="optimized",
        article_assessment=BlogAssessmentV1(
            information_density=2,
            logical_complexity=2,
            data_richness=2,
            scene_relevance=0,
            visual_potential=2,
            rewrite_value=1,
            evidence_quality=2,
        ),
        decision=BlogDecisionV1(
            should_optimize=True,
            reason="有价值",
            selected_agents=["logic-agent"],
            skipped_agents=[],
        ),
        optimized_article=BlogOptimizedArticleV1(title="t", summary="s", content_markdown="body"),
        enhancements=enhancements,
        quality_report=BlogQualityReportV1(
            author_intent_preserved=True,
            unsupported_claims=[],
            removed_low_value_enhancements=[],
            warnings=[],
        ),
        usage=BlogUsageV1(
            agents_called=1,
            skills_called=["visualize"],
            visual_items_created=1,
            estimated_input_tokens=1,
            estimated_output_tokens=1,
            estimated_cost=0,
        ),
    )


def test_mermaid_is_normalized_and_inserted():
    result = _result(
        [
            {
                "id": "flow-1",
                "agent": "logic-agent",
                "capability": "visualize",
                "status": "executed",
                "insert_after": "body",
                "reason": "流程清晰",
                "content": {"mermaid": "flowchart TD\n A-->B"},
                "caption": "处理流程",
                "alt_text": "处理流程图",
            }
        ]
    )
    items = execute_enhancements(result)
    assert items[0]["content"]["format"] == "mermaid"
    assert "```mermaid" in enhancements_markdown(items)


def test_visual_plan_is_normalized_and_rendered_as_reader_facing_block():
    result = _result(
        [
            {
                "id": "plan-1",
                "agent": "logic-agent",
                "capability": "visualize",
                "status": "executed",
                "insert_after": "body",
                "reason": "普通读者需要步骤图",
                "content": {
                    "visual_plan": {
                        "visual_type": "illustrated_steps",
                        "layout": "compact_horizontal",
                        "theme": "fresh",
                        "title": "建立早起习惯",
                        "nodes": [
                            {
                                "id": "prepare",
                                "label": "睡前准备",
                                "detail": "提前放下手机",
                                "icon": "moon",
                            },
                            {
                                "id": "wake",
                                "label": "固定起床",
                                "detail": "每天同一时间",
                                "icon": "sun",
                            },
                            {
                                "id": "reward",
                                "label": "即时奖励",
                                "detail": "安排喜欢的早餐",
                                "icon": "star",
                            },
                        ],
                        "edges": [
                            {"from": "prepare", "to": "wake", "label": "第二天"},
                            {"from": "wake", "to": "reward", "label": "起床后"},
                        ],
                    },
                },
                "caption": "早起步骤",
                "alt_text": "建立早起习惯的三个步骤",
            }
        ]
    )
    items = execute_enhancements(result)
    assert items[0]["content"]["format"] == "visual-plan"
    markdown = enhancements_markdown(items)
    assert "```visual-plan" in markdown
    assert "睡前准备" in markdown


def test_visual_plan_png_has_stable_dimensions_and_is_valid_png():
    plan = {
        "visual_type": "compact_flow",
        "layout": "compact_horizontal",
        "theme": "fresh",
        "title": "水循环关键步骤",
        "nodes": [
            {"id": "a", "label": "蒸发与蒸腾", "detail": "太阳加热水体", "icon": "step"},
            {"id": "b", "label": "上升与凝结", "detail": "水蒸气遇冷形成云", "icon": "step"},
            {"id": "c", "label": "降水", "detail": "雨雪回到地面", "icon": "step"},
            {"id": "d", "label": "汇流与回归", "detail": "最终回到河流和海洋", "icon": "step"},
        ],
        "edges": [
            {"from": "a", "to": "b", "label": "上升运输"},
            {"from": "b", "to": "c", "label": "冷却增大"},
            {"from": "c", "to": "d", "label": "落回地面"},
            {"from": "d", "to": "a", "label": "循环再次开始"},
        ],
    }
    image = Image.open(io.BytesIO(render_visual_plan_png(plan)))
    assert image.format == "PNG"
    assert image.width >= 1400
    assert image.height >= 300


def test_visual_plan_rejects_invalid_edges():
    result = _result(
        [
            {
                "id": "plan-1",
                "agent": "logic-agent",
                "capability": "visualize",
                "status": "executed",
                "insert_after": "body",
                "reason": "无效",
                "content": {
                    "visual_plan": {
                        "visual_type": "compact_flow",
                        "layout": "compact_horizontal",
                        "theme": "fresh",
                        "title": "无效图",
                        "nodes": [
                            {"id": "a", "label": "A"},
                            {"id": "b", "label": "B"},
                            {"id": "c", "label": "C"},
                        ],
                        "edges": [{"from": "a", "to": "missing"}],
                    },
                },
                "caption": "无效",
                "alt_text": "无效",
            }
        ]
    )
    execute_enhancements(result)
    assert result.enhancements[0].status == "failed"


def test_chart_rejects_non_numeric_points():
    result = _result(
        [
            {
                "id": "chart-1",
                "agent": "data-agent",
                "capability": "answers-charts",
                "status": "executed",
                "insert_after": "body",
                "reason": "数据对比",
                "content": {
                    "chart_type": "bar",
                    "data": [{"label": "A", "value": "not-a-number"}],
                },
                "caption": "对比",
                "alt_text": "对比图表",
            }
        ]
    )
    execute_enhancements(result)
    assert result.enhancements[0].status == "failed"
