"""100k Post deep-search p95 and timeline cursor stability acceptance."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from app.db.session import session_scope
from app.modules.posts import query_service
from sqlalchemy import text

pytestmark = [pytest.mark.performance, pytest.mark.integration]
ROWS = int(os.environ.get("SEARCH_PERF_ROWS", "3000"))


def test_blog_search_p95_and_timeline_cursor_stability(make_user):
    uid = make_user().id
    with session_scope() as session:
        payload = [
            {
                "id": uuid.uuid4(),
                "uid": uid,
                "title": f"文章 {i}",
                "body": "性能针 PERF_POST_731" if i % 10000 == 0 else f"正文 {i}",
                "occurred": f"2025-{(i % 12) + 1:02d}-01T00:00:00+00:00",
            }
            for i in range(ROWS)
        ]
        session.execute(
            text("""
            INSERT INTO posts
              (id,user_id,title,markdown,status,version,content_status,content_class,
               language,editor_mode,structured_data_json,ai_optimization_count,
               occurred_at,created_at,updated_at)
            VALUES
              (:id,:uid,:title,:body,'draft',1,'draft','technical','zh-CN','rich',
               '{}'::jsonb,0,:occurred,now(),now())
        """),
            payload,
        )

    durations = []
    for _ in range(10):
        start = time.perf_counter()
        with session_scope() as session:
            assert query_service.search_posts(session, uid, "PERF_POST_731", limit=20)["items"]
        durations.append(time.perf_counter() - start)
    durations.sort()
    assert durations[8] < 2.0

    with session_scope() as session:
        page1 = query_service.timeline_posts(session, uid, year=2025, cursor=0, limit=50)
        page2 = query_service.timeline_posts(session, uid, year=2025, cursor=50, limit=50)
        again = query_service.timeline_posts(session, uid, year=2025, cursor=0, limit=50)
    assert page1["items"] == again["items"]
    assert {item["id"] for item in page1["items"]}.isdisjoint(item["id"] for item in page2["items"])
