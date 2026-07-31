from app.modules.posts.visuals import enhancements_markdown, execute_enhancements
from app.services.llm.schemas import (
    BlogAssessmentV1,
    BlogDecisionV1,
    BlogEnhancementResultV1,
    BlogOptimizedArticleV1,
    BlogQualityReportV1,
    BlogUsageV1,
)


def _result(enhancements):
    return BlogEnhancementResultV1(
        status="optimized",
        article_assessment=BlogAssessmentV1(
            information_density=2, logical_complexity=2, data_richness=2,
            scene_relevance=0, visual_potential=2, rewrite_value=1, evidence_quality=2,
        ),
        decision=BlogDecisionV1(
            should_optimize=True, reason="有价值", selected_agents=["logic-agent"], skipped_agents=[]
        ),
        optimized_article=BlogOptimizedArticleV1(title="t", summary="s", content_markdown="body"),
        enhancements=enhancements,
        quality_report=BlogQualityReportV1(
            author_intent_preserved=True, unsupported_claims=[],
            removed_low_value_enhancements=[], warnings=[],
        ),
        usage=BlogUsageV1(
            agents_called=1, skills_called=["visualize"], visual_items_created=1,
            estimated_input_tokens=1, estimated_output_tokens=1, estimated_cost=0,
        ),
    )


def test_mermaid_is_normalized_and_inserted():
    result = _result([
        {
            "id": "flow-1", "agent": "logic-agent", "capability": "visualize", "status": "executed",
            "insert_after": "body", "reason": "流程清晰", "content": {"mermaid": "flowchart TD\n A-->B"},
            "caption": "处理流程", "alt_text": "处理流程图",
        }
    ])
    items = execute_enhancements(result)
    assert items[0]["content"]["format"] == "mermaid"
    assert "```mermaid" in enhancements_markdown(items)


def test_chart_rejects_non_numeric_points():
    result = _result([
        {
            "id": "chart-1", "agent": "data-agent", "capability": "answers-charts", "status": "executed",
            "insert_after": "body", "reason": "数据对比", "content": {
                "chart_type": "bar", "data": [{"label": "A", "value": "not-a-number"}],
            }, "caption": "对比", "alt_text": "对比图表",
        }
    ])
    execute_enhancements(result)
    assert result.enhancements[0].status == "failed"
