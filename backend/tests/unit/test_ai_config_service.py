from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def test_article_query_skill_default_is_versioned_and_user_scoped(db_session, make_user) -> None:
    from app.modules.ai_config import service

    owner = make_user()
    other = make_user()
    skill = service.save_skill(
        db_session,
        owner.id,
        "conversation_route",
        "文章查询默认值",
        "未指定数量时展示更多结果。",
        {"posts.list_recent": {"limit": 25}},
    )
    service.activate(db_session, owner.id, "conversation_route", None, skill.id)
    db_session.commit()

    assert service.resolve(db_session, owner.id, "conversation_route").tool_defaults == {
        "posts.list_recent": {"limit": 25}
    }
    resolved = service.resolve(db_session, owner.id, "conversation_route")
    assert resolved.system_instruction.startswith("平台强制规则：")
    assert "当前 Skill：未指定数量时展示更多结果。" in resolved.system_instruction
    assert service.resolve(db_session, other.id, "conversation_route").tool_defaults == {
        "posts.list_recent": {"limit": 10}
    }


def test_skill_rejects_tools_outside_module_contract(db_session, make_user) -> None:
    from app.modules.ai_config import service

    with pytest.raises(ValueError, match="invalid_skill_tool_defaults"):
        service.save_skill(
            db_session,
            make_user().id,
            "conversation_route",
            "越权工具",
            "",
            {"posts.apply_analysis": {"limit": 10}},
        )


def test_article_query_skill_rejects_invalid_limit(db_session, make_user) -> None:
    from app.modules.ai_config import service

    with pytest.raises(ValueError, match="invalid_recent_article_limit"):
        service.save_skill(
            db_session,
            make_user().id,
            "conversation_route",
            "错误数量",
            "",
            {"posts.list_recent": {"limit": "all"}},
        )
