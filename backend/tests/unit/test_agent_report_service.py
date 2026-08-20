from __future__ import annotations


def test_deterministic_markdown_reconciles_read_only_results() -> None:
    from app.modules.agent.report_service import render_markdown

    markdown = render_markdown(
        objective="查询一篇关于情感的博客",
        executed_steps=[{"title": "搜索博客", "status": "success", "summary": "命中 1 篇"}],
        totals={
            "matched": 1,
            "processed": 1,
            "applied": 0,
            "verified": 0,
            "conflicted": 0,
            "failed": 0,
            "skipped": 0,
            "unprocessed": 0,
            "manual_review": 0,
        },
        results=[{"id": "post-1", "title": "关于情感的文章", "link": "/blog/post-1/view"}],
        verified_changes=[],
        conflicts=[],
        failures=[],
        skipped=[],
        unprocessed=[],
        next_actions=[],
    )

    assert "# 查询一篇关于情感的博客" in markdown
    assert "关于情感的文章" in markdown
    assert "匹配：1" in markdown
    assert "执行计划" in markdown
