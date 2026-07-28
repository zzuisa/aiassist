"""Async quick-add planning: background job, Q&A round-trip, memory, skip."""

from __future__ import annotations

import json
import uuid

import pytest
from app.db.session import session_scope
from app.models.foundation import AsyncJob, User
from app.models.tasks import Task
from app.modules.tasks import plan_service
from app.services.llm.gateway import FakeProvider, LLMGatewayImpl
from sqlalchemy import func, select

pytestmark = [pytest.mark.integration]


def _cand(title):
    return {
        "title": title, "content_type": "task", "description": None,
        "local_date": "2026-07-29", "local_time": "09:00:00", "timezone": "Europe/Berlin",
        "duration_minutes": 30, "priority": 1, "important": False, "reminder": None,
        "recurring": False, "recurrence_rule": None, "original_text": title,
    }


def _plan_json(questions):
    return json.dumps({"tasks": [_cand("喝咖啡")], "questions": questions, "summary": "安排 1 项"})


def _fake():
    return LLMGatewayImpl(FakeProvider())


def test_run_plan_waits_when_questions(make_user):
    user = make_user()
    text = f"明天上午喝咖啡 <<JSON>>{_plan_json(['几点起床？'])}"
    with session_scope() as s:
        job = plan_service.create_plan_job(s, user.id, text)
        jid = job.id
    with session_scope() as s:
        job = plan_service.run_plan(s, jid, llm=_fake())
        assert job.status == "waiting_user"
        assert job.result_json["questions"] == ["几点起床？"]
        assert len(job.result_json["tasks"]) == 1
    with session_scope() as s:  # nothing created yet
        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id)) == 0


def test_run_plan_creates_tasks_when_no_questions(make_user):
    user = make_user()
    text = f"明天上午喝咖啡 <<JSON>>{_plan_json([])}"
    with session_scope() as s:
        jid = plan_service.create_plan_job(s, user.id, text).id
    with session_scope() as s:
        job = plan_service.run_plan(s, jid, llm=_fake())
        assert job.status == "completed"
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id)) == 1


def test_answer_records_memory_and_requeues(make_user):
    user = make_user()
    text = f"明天上午喝咖啡 <<JSON>>{_plan_json(['你一般几点起床？'])}"
    with session_scope() as s:
        jid = plan_service.create_plan_job(s, user.id, text).id
    with session_scope() as s:
        plan_service.run_plan(s, jid, llm=_fake())  # -> waiting_user
    with session_scope() as s:
        job = plan_service.answer_plan(s, user.id, jid, [("你一般几点起床？", "07:00")])
        assert job.status == "queued"
        assert job.result_json["rounds"] == 1
    with session_scope() as s:
        user_row = s.get(User, user.id)
        facts = plan_service.get_user_facts(user_row)
        assert any(f["a"] == "07:00" for f in facts)  # remembered


def test_skip_commits_partial_plan(make_user):
    user = make_user()
    text = f"明天上午喝咖啡 <<JSON>>{_plan_json(['几点起床？'])}"
    with session_scope() as s:
        jid = plan_service.create_plan_job(s, user.id, text).id
    with session_scope() as s:
        plan_service.run_plan(s, jid, llm=_fake())  # waiting_user, stored tasks
    with session_scope() as s:
        job = plan_service.skip_plan(s, user.id, jid)
        assert job.status == "completed"
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id)) == 1


_ = AsyncJob


def test_memory_set_get_and_settings_preserves(make_user):
    from app.models.foundation import User
    from app.modules.settings import service as settings_service

    user = make_user()
    with session_scope() as s:
        u = s.get(User, user.id)
        plan_service.set_user_facts(u, [{"q": "几点起床？", "a": "07:00"}, {"q": "", "a": "x"}])
    with session_scope() as s:
        u = s.get(User, user.id)
        facts = plan_service.get_user_facts(u)
        assert facts == [{"q": "几点起床？", "a": "07:00"}]  # blanks dropped
    # Updating notification preferences must NOT wipe the _profile memory.
    with session_scope() as s:
        settings_service.update_settings(
            s, user.id, {"notification_preferences": {"in_app_enabled": True, "email_enabled": False}}
        )
    with session_scope() as s:
        u = s.get(User, user.id)
        assert plan_service.get_user_facts(u) == [{"q": "几点起床？", "a": "07:00"}]
