"""US8 taxonomy governance integration coverage."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


@requires_db
def test_category_depth_cycle_ownership_disable_and_history(db_session, make_user):
    from app.core.errors import ValidationError
    from app.modules.posts import service, taxonomy_service

    uid, other = make_user().id, make_user().id
    root = taxonomy_service.create_item(db_session, uid, "category", name="根")
    child = taxonomy_service.create_item(
        db_session, uid, "category", name="子", parent_id=uuid.UUID(root["id"])
    )
    leaf = taxonomy_service.create_item(
        db_session, uid, "category", name="叶", parent_id=uuid.UUID(child["id"])
    )
    with pytest.raises(ValidationError, match="depth"):
        taxonomy_service.create_item(
            db_session, uid, "category", name="过深", parent_id=uuid.UUID(leaf["id"])
        )
    with pytest.raises(ValidationError, match="cycle"):
        taxonomy_service.update_item(
            db_session,
            uid,
            "category",
            uuid.UUID(root["id"]),
            parent_id=uuid.UUID(child["id"]),
        )
    with pytest.raises(ValidationError, match="parent"):
        taxonomy_service.create_item(
            db_session, other, "category", name="越权", parent_id=uuid.UUID(root["id"])
        )
    post = service.create_post(db_session, uid, title="历史", markdown="正文")
    post.category_id = uuid.UUID(root["id"])
    taxonomy_service.update_item(db_session, uid, "category", uuid.UUID(root["id"]), enabled=False)
    db_session.commit()
    assert "根" not in {
        item["name"]
        for item in taxonomy_service.list_items(db_session, uid, "category", enabled=True)
    }
    assert (
        taxonomy_service.get_item(db_session, uid, "category", uuid.UUID(root["id"]))["enabled"]
        is False
    )
    assert post.category_id == uuid.UUID(root["id"])


@requires_db
def test_alias_uniqueness_resolution_and_keyword_sources(db_session, make_user):
    from app.core.errors import ConflictError
    from app.models.blog import PostKeywordLink
    from app.modules.posts import service, taxonomy_service

    uid = make_user().id
    tag = taxonomy_service.create_item(
        db_session, uid, "tag", name="Kubernetes", aliases=["k8s"], color="blue"
    )
    assert taxonomy_service.resolve_name(db_session, uid, "tag", "K8S")["id"] == tag["id"]
    with pytest.raises(ConflictError):
        taxonomy_service.create_item(db_session, uid, "tag", name="k8s")
    keyword = taxonomy_service.create_item(
        db_session, uid, "keyword", name="PostgreSQL", aliases=["pg"], stop_word=False
    )
    taxonomy_service.create_item(db_session, uid, "keyword", name="以及", stop_word=True)
    assert [
        i["id"]
        for i in taxonomy_service.normalize_recommendations(
            db_session, uid, "keyword", ["PG", "以及", "未知"]
        )
    ] == [keyword["id"]]
    post = service.create_post(db_session, uid, title="数据库", markdown="PostgreSQL 调优")
    db_session.add(
        PostKeywordLink(
            post_id=post.id,
            keyword_id=uuid.UUID(keyword["id"]),
            user_id=uid,
            source="ai",
            weight=0.8,
        )
    )
    db_session.commit()
    link = db_session.scalar(select(PostKeywordLink).where(PostKeywordLink.post_id == post.id))
    assert link.source == "ai"


@requires_db
def test_atomic_merge_redirects_relations_disables_source_and_audits(db_session, make_user):
    from app.models.blog import TaxonomyMerge
    from app.modules.posts import service, taxonomy_service

    uid = make_user().id
    source = taxonomy_service.create_item(db_session, uid, "category", name="旧分类")
    target = taxonomy_service.create_item(db_session, uid, "category", name="新分类")
    post = service.create_post(db_session, uid, title="文章", markdown="正文")
    post.category_id = uuid.UUID(source["id"])
    db_session.flush()
    status, merged = taxonomy_service.request_merge(
        db_session, uid, "category", uuid.UUID(source["id"]), uuid.UUID(target["id"])
    )
    db_session.commit()
    assert status == "completed" and merged["usage_count"] == 1
    assert post.category_id == uuid.UUID(target["id"])
    assert (
        taxonomy_service.get_item(db_session, uid, "category", uuid.UUID(source["id"]))["enabled"]
        is False
    )
    audit = db_session.scalar(select(TaxonomyMerge))
    assert audit.status == "completed" and audit.affected_count == 1
