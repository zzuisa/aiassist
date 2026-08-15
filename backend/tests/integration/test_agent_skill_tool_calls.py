from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


class _Gateway:
    def __init__(self, limit: int | None):
        self.limit = limit

    def structured(self, _request):
        from app.modules.agent.conversation_schemas import ConversationRoute

        arguments = {} if self.limit is None else {"limit": self.limit}
        return ConversationRoute.model_validate(
            {
                "route_kind": "task",
                "objective": "查询最近文章",
                "operation_type": "query",
                "target_scope": {
                    "source": "current_message",
                    "object_type": "post",
                    "object_ids": [],
                },
                "semantic_arguments": {},
                "candidate_tool_keys": ["posts.list_recent"],
                "tool_call": {"name": "posts.list_recent", "arguments": arguments},
                "requires_confirmation": False,
                "confidence": 0.95,
            }
        )


def test_skill_default_is_merged_into_model_tool_call(db_session, make_user) -> None:
    from app.modules.agent.conversation_router import route_message
    from app.modules.ai_config import service

    user = make_user()
    skill = service.save_skill(
        db_session,
        user.id,
        "conversation_route",
        "文章查询",
        "缺失参数时使用默认值。",
        {"posts.list_recent": {"limit": 17}},
    )
    service.activate(db_session, user.id, "conversation_route", None, skill.id)

    outcome = route_message(
        "查一下最近文章", session=db_session, user_id=user.id, gateway=_Gateway(None)
    )

    assert outcome.selected_tool == "posts.list_recent"
    assert outcome.route.semantic_arguments == {"limit": 17}
    assert outcome.route.tool_call is not None
    assert outcome.route.tool_call.arguments == {"limit": 17}


def test_explicit_model_argument_overrides_skill_default(db_session, make_user) -> None:
    from app.modules.agent.conversation_router import route_message

    user = make_user()
    outcome = route_message(
        "给我最近 3 篇文章", session=db_session, user_id=user.id, gateway=_Gateway(3)
    )
    assert outcome.selected_tool == "posts.list_recent"
    assert outcome.route.semantic_arguments == {"limit": 3}


def test_invalid_model_argument_is_rejected_before_tool_execution(db_session, make_user) -> None:
    from app.modules.agent.conversation_router import route_message

    user = make_user()
    outcome = route_message(
        "给我最近 999 篇文章", session=db_session, user_id=user.id, gateway=_Gateway(999)
    )
    assert outcome.selected_tool is None
    assert outcome.route.route_kind == "clarification"
    assert outcome.validation_errors == ("tool_arguments_invalid",)
