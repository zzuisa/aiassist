"""100k Post deep-search p95 and timeline cursor stability acceptance."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from app.db.session import session_scope
from app.modules.posts import query_service
from app.workers.tasks.blog import run_wordcloud
from sqlalchemy import text

pytestmark = [pytest.mark.performance, pytest.mark.integration]
ROWS = int(os.environ.get("SEARCH_PERF_ROWS", "3000"))
FIRST_PAGE_BUDGET_SECONDS = 2.0
WORD_CLOUD_BUDGET_SECONDS = 10.0


def test_blog_search_p95_and_timeline_cursor_stability(make_user, record_property):
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
    search_p95 = durations[8]
    record_property("rows", ROWS)
    record_property("search_p95_seconds", round(search_p95, 6))
    assert search_p95 < FIRST_PAGE_BUDGET_SECONDS

    timeline_durations = []
    for _ in range(10):
        start = time.perf_counter()
        with session_scope() as session:
            page1 = query_service.timeline_posts(session, uid, year=2025, cursor=0, limit=50)
        timeline_durations.append(time.perf_counter() - start)
    timeline_durations.sort()
    timeline_p95 = timeline_durations[8]
    record_property("timeline_p95_seconds", round(timeline_p95, 6))
    assert timeline_p95 < FIRST_PAGE_BUDGET_SECONDS

    with session_scope() as session:
        page2 = query_service.timeline_posts(session, uid, year=2025, cursor=50, limit=50)
        again = query_service.timeline_posts(session, uid, year=2025, cursor=0, limit=50)
    assert page1["items"] == again["items"]
    assert {item["id"] for item in page1["items"]}.isdisjoint(item["id"] for item in page2["items"])

    keyword_ids = [uuid.uuid4() for _ in range(20)]
    with session_scope() as session:
        session.execute(
            text("""
                INSERT INTO post_keywords
                  (id,user_id,canonical_text,enabled,is_stop_word,created_at,updated_at)
                VALUES (:id,:uid,:term,true,false,now(),now())
            """),
            [
                {"id": keyword_id, "uid": uid, "term": f"性能关键词-{index:02d}"}
                for index, keyword_id in enumerate(keyword_ids)
            ],
        )
        session.execute(
            text("""
                INSERT INTO post_keyword_links
                  (post_id,keyword_id,user_id,source,created_at)
                VALUES (:post_id,:keyword_id,:uid,'recomputed',now())
            """),
            [
                {
                    "post_id": row["id"],
                    "keyword_id": keyword_ids[index % len(keyword_ids)],
                    "uid": uid,
                }
                for index, row in enumerate(payload)
            ],
        )
        job, _ = query_service.request_word_cloud_rebuild(
            session,
            uid,
            "keyword",
            {"year": 2025},
            min_frequency=2,
            max_terms=50,
        )
        snapshot_id = job.entity_id

    start = time.perf_counter()
    assert run_wordcloud(snapshot_id, 2, 50) == "completed"
    word_cloud_duration = time.perf_counter() - start
    record_property("word_cloud_seconds", round(word_cloud_duration, 6))
    assert word_cloud_duration < WORD_CLOUD_BUDGET_SECONDS
    with session_scope() as session:
        snapshot = query_service.get_word_cloud_snapshot(session, uid, "keyword", {"year": 2025})
        assert snapshot is not None
        assert snapshot.article_count == ROWS
        assert len(snapshot.terms_json) == 20
