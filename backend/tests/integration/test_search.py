"""Search: grouping, ownership isolation, fresh-record findability, highlight safety."""

from __future__ import annotations

import pytest
from app.db.session import session_scope
from app.modules.captures import service as capture_service
from app.modules.habits import service as habit_service
from app.modules.search import service as search_service
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskCreate

pytestmark = [pytest.mark.integration]


def _seed(session, user_id, keyword: str):
    task_service.create_task(session, user_id, TaskCreate(title=f"{keyword} 任务", type="task"))
    habit_service.create_habit(
        session, user_id, {"name": f"{keyword} 习惯", "recurrence_rule": "FREQ=DAILY"}
    )
    capture_service.create_capture(
        session,
        user_id,
        capture_type="item",
        title=f"{keyword} 收藏",
        description=None,
        upload_ids=[],
    )


def test_results_grouped_by_type(make_user):
    user = make_user()
    with session_scope() as s:
        _seed(s, user.id, "房东")
        uid = user.id
    with session_scope() as s:
        result = search_service.search(s, uid, "房东")
        types = {g["type"] for g in result["groups"]}
        assert {"task", "habit", "capture"}.issubset(types)


def test_fresh_record_is_immediately_searchable(make_user):
    """Direct committed-data search finds a record with no index-lag gap."""
    user = make_user()
    with session_scope() as s:
        task_service.create_task(s, user.id, TaskCreate(title="立即可搜关键词", type="task"))
        uid = user.id
    with session_scope() as s:
        result = search_service.search(s, uid, "立即可搜关键词", types=["task"])
        assert result["groups"]
        assert result["groups"][0]["items"][0]["title"] == "立即可搜关键词"


def test_cross_user_isolation(make_user):
    owner = make_user()
    other = make_user()
    with session_scope() as s:
        _seed(s, owner.id, "私密关键词")
        oid = owner.id
        xid = other.id
    with session_scope() as s:
        owner_res = search_service.search(s, oid, "私密关键词")
        other_res = search_service.search(s, xid, "私密关键词")
        assert owner_res["groups"]
        assert other_res["groups"] == []


def test_highlight_is_html_escaped(make_user):
    user = make_user()
    with session_scope() as s:
        task_service.create_task(
            s, user.id, TaskCreate(title="<script>危险</script>关键", type="task")
        )
        uid = user.id
    with session_scope() as s:
        result = search_service.search(s, uid, "关键", types=["task"])
        highlights = result["groups"][0]["items"][0]["highlights"]
        joined = " ".join(highlights)
        assert "<script>" not in joined
        assert "&lt;script&gt;" in joined


def test_ocr_text_is_searchable(make_user):
    user = make_user()
    with session_scope() as s:
        capture = capture_service.create_capture(
            s, user.id, capture_type="item", title="工具", description=None, upload_ids=[]
        )
        capture.ocr_text = "型号 ABC123 序列号"
        uid = user.id
    with session_scope() as s:
        result = search_service.search(s, uid, "ABC123", types=["capture"])
        assert result["groups"]


def test_empty_result_returns_no_groups(make_user):
    user = make_user()
    with session_scope() as s:
        result = search_service.search(s, user.id, "不存在的词xyz")
        assert result["groups"] == []
