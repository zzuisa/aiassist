"""Quick-add planning: analyze (LLM) + commit (create scheduled tasks)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from app.db.session import session_scope
from app.models.tasks import Task
from app.modules.tasks import plan_service
from app.services.llm.gateway import FakeProvider, LLMGatewayImpl
from app.services.llm.schemas import VoiceTaskV1
from sqlalchemy import func, select

pytestmark = [pytest.mark.integration]


def _cand(title, date, time, important=False):
    return {
        "title": title,
        "content_type": "task",
        "description": None,
        "local_date": date,
        "local_time": time,
        "timezone": "Europe/Berlin",
        "duration_minutes": 30,
        "priority": 3 if important else 1,
        "important": important,
        "reminder": None,
        "recurring": False,
        "recurrence_rule": None,
        "original_text": title,
    }


def test_analyze_with_fake_provider_returns_plan(make_user):
    user = make_user()
    plan_json = json.dumps(
        {
            "tasks": [_cand("喝咖啡", "2026-07-28", "09:00:00")],
            "questions": ["你一般几点起床？"],
            "summary": "已安排 1 件事：喝咖啡 09:00",
        }
    )
    text = f"明天上午喝咖啡 <<JSON>>{plan_json}"
    with session_scope() as s:
        plan = plan_service.analyze(s, user.id, text, llm=LLMGatewayImpl(FakeProvider()))
        assert len(plan.tasks) == 1 and plan.tasks[0].title == "喝咖啡"
        assert plan.questions == ["你一般几点起床？"]
        assert "喝咖啡" in plan.summary


def test_commit_creates_scheduled_tasks(make_user):
    user = make_user()
    tasks = [
        VoiceTaskV1.model_validate(_cand("喝咖啡", "2026-07-28", "09:00:00")),
        VoiceTaskV1.model_validate(_cand("吃自助", "2026-07-28", "12:00:00", important=True)),
    ]
    with session_scope() as s:
        created = plan_service.commit(s, user.id, tasks)
        assert len(created) == 2
    with session_scope() as s:
        rows = s.scalars(select(Task).where(Task.user_id == user.id)).all()
        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id)) == 2
        by = {t.title: t for t in rows}
        # 09:00 Europe/Berlin (CEST) -> 07:00 UTC
        assert by["喝咖啡"].start_at == datetime(2026, 7, 28, 7, 0, tzinfo=UTC)
        assert by["吃自助"].importance == 4  # important -> importance 4
        assert by["喝咖啡"].source_type == "quick_plan"
