"""US7 direct/derived deep search and timeline integration coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


@requires_db
def test_direct_search_covers_cjk_code_structured_source_and_combined_filters(
    db_session, make_user
):
    from app.models.blog import PostSource
    from app.models.foundation import Category
    from app.modules.posts import query_service, service

    uid = make_user().id
    category = Category(user_id=uid, name="生产事故", kind="post")
    db_session.add(category)
    db_session.flush()
    post = service.create_post(
        db_session, uid, title="支付网关", markdown="```python\nraise RuntimeError('E731')\n```"
    )
    post.content_class = "technical"
    post.category_id = category.id
    post.structured_data_json = {"root_cause": "连接池耗尽"}
    db_session.add(
        PostSource(
            id=uuid.uuid4(),
            user_id=uid,
            post_id=post.id,
            source_type="url",
            status="completed",
            original_url="https://example.test/incident-731",
        )
    )
    db_session.commit()

    for needle in ("连接池耗尽", "RuntimeError", "incident-731"):
        out = query_service.search_posts(
            db_session, uid, needle, content_class="technical", category_id=category.id
        )
        assert [item["id"] for item in out["items"]] == [str(post.id)]
    assert (
        query_service.search_posts(db_session, uid, "连接池耗尽", content_class="life")["items"]
        == []
    )


@requires_db
def test_post_derived_document_refresh_is_complete_and_idempotent(db_session, make_user):
    from app.models.foundation import Category, Tag
    from app.models.posts import PostTag
    from app.models.search import SearchDocument
    from app.modules.posts import service
    from app.workers.tasks.search import refresh_post_document

    uid = make_user().id
    category = Category(user_id=uid, name="后端", kind="post")
    tag = Tag(user_id=uid, name="PostgreSQL")
    db_session.add_all([category, tag])
    db_session.flush()
    post = service.create_post(db_session, uid, title="索引刷新", markdown="正文 NeedleBody")
    post.summary = "摘要 NeedleSummary"
    post.category_id = category.id
    post.structured_data_json = {"error": "NeedleMetadata"}
    db_session.add(PostTag(post_id=post.id, tag_id=tag.id, user_id=uid))
    db_session.commit()

    assert refresh_post_document(str(uid), str(post.id)) == "refreshed"
    assert refresh_post_document(str(uid), str(post.id)) == "refreshed"
    db_session.expire_all()
    docs = db_session.scalars(
        select(SearchDocument).where(
            SearchDocument.user_id == uid, SearchDocument.entity_id == post.id
        )
    ).all()
    assert len(docs) == 1
    doc = docs[0]
    assert "NeedleSummary" in (doc.body or "")
    assert doc.tags_text == "PostgreSQL"
    assert doc.category_text == "后端"
    assert "NeedleMetadata" in (doc.metadata_text or "")


@requires_db
def test_timeline_occurrence_and_creation_fallback_with_stable_pages(db_session, make_user):
    from app.modules.posts import query_service, service

    uid = make_user().id
    occurred = service.create_post(db_session, uid, title="发生时间", markdown="a")
    occurred.occurred_at = datetime(2025, 6, 2, tzinfo=UTC)
    fallback = service.create_post(db_session, uid, title="创建时间回退", markdown="b")
    fallback.created_at = datetime(2025, 5, 1, tzinfo=UTC)
    db_session.commit()

    first = query_service.timeline_posts(db_session, uid, year=2025, cursor=0, limit=1)
    second = query_service.timeline_posts(db_session, uid, year=2025, cursor=1, limit=1)
    repeated = query_service.timeline_posts(db_session, uid, year=2025, cursor=0, limit=1)
    assert first["items"][0]["time_basis"] == "occurred_at"
    assert second["items"][0]["time_basis"] == "created_at"
    assert first["items"] == repeated["items"]
    assert first["items"][0]["id"] != second["items"][0]["id"]
