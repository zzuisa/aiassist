"""US9 word-cloud filtering, aggregation and fallback integration coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


@requires_db
def test_filter_hash_stop_words_threshold_limit_and_last_success(db_session, make_user):
    from app.models.blog import PostKeywordLink
    from app.modules.posts import query_service, service, taxonomy_service
    from app.workers.tasks import blog as blog_task

    user_id = make_user().id
    primary = taxonomy_service.create_item(db_session, user_id, "keyword", name="数据库")
    secondary = taxonomy_service.create_item(db_session, user_id, "keyword", name="性能")
    stop = taxonomy_service.create_item(db_session, user_id, "keyword", name="以及", stop_word=True)
    for index in range(3):
        post = service.create_post(db_session, user_id, title=f"文章 {index}", markdown="正文")
        post.occurred_at = datetime(2026, 5, index + 1, tzinfo=UTC)
        for keyword in (primary, stop):
            db_session.add(
                PostKeywordLink(
                    post_id=post.id,
                    keyword_id=uuid.UUID(keyword["id"]),
                    user_id=user_id,
                    source="user",
                )
            )
        if index == 0:
            db_session.add(
                PostKeywordLink(
                    post_id=post.id,
                    keyword_id=uuid.UUID(secondary["id"]),
                    user_id=user_id,
                    source="user",
                )
            )
    job, previous = query_service.request_word_cloud_rebuild(
        db_session,
        user_id,
        "keyword",
        {"month": "5", "year": "2026", "ignored": "x"},
        min_frequency=2,
        max_terms=1,
    )
    snapshot_id = job.entity_id
    assert snapshot_id is not None
    db_session.commit()

    assert previous is None
    assert blog_task.run_wordcloud(snapshot_id, 2, 1) == "completed"
    db_session.expire_all()
    snapshot = query_service.get_word_cloud_snapshot(
        db_session, user_id, "keyword", {"year": 2026, "month": 5}
    )
    assert snapshot is not None
    assert snapshot.filter_hash == query_service.word_cloud_filter_hash({"year": 2026, "month": 5})
    assert snapshot.terms_json == [{"id": primary["id"], "term": "数据库", "count": 3}]
    assert snapshot.article_count == 3 and snapshot.status == "ready"

    _job, previous = query_service.request_word_cloud_rebuild(
        db_session, user_id, "keyword", {"year": 2026, "month": 5}
    )
    assert previous is snapshot
    assert previous.terms_json[0]["term"] == "数据库"
