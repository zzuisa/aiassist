"""Article management: triage derivation + ordered merge (spec 005, US6, T113).

Covers the triage reason projection (quick/failed/stale/draft) and the
transactional ordered merge that concatenates two bodies in order, re-parents the
secondary's capture sources so none are lost, and keeps the secondary as a
recoverable discarded record.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


def _source(session, user_id, post_id, url):
    from app.models.blog import PostSource

    s = PostSource(
        id=uuid.uuid4(),
        user_id=user_id,
        post_id=post_id,
        source_type="url",
        status="completed",
        original_url=url,
        captured_at=datetime.now(UTC),
    )
    session.add(s)
    session.flush()
    return s


@requires_db
def test_triage_reason_derivation(db_session, make_user):
    from app.models.posts import Post
    from app.modules.posts import query_service, service

    uid = make_user().id
    quick = service.create_post(db_session, uid, title="q", markdown="随手记")
    quick.content_class = "quick"
    failed = service.create_post(db_session, uid, title="f", markdown="失败")
    failed.latest_ai_status = "failed"
    stale = service.create_post(db_session, uid, title="s", markdown="很久没动")
    plain = service.create_post(db_session, uid, title="d", markdown="草稿")
    db_session.commit()

    # Force the stale item's updated_at back beyond the threshold.
    db_session.execute(
        update(Post)
        .where(Post.id == stale.id)
        .values(updated_at=datetime.now(UTC) - timedelta(days=30))
    )
    db_session.commit()

    out = query_service.triage_items(db_session, uid)
    by_id = {i["id"]: i["reason"] for i in out["items"]}
    assert by_id[str(quick.id)] == "quick"
    assert by_id[str(failed.id)] == "failed"
    assert by_id[str(stale.id)] == "stale"
    assert by_id[str(plain.id)] == "draft"
    assert out["counts_by_reason"]["quick"] == 1

    # Reason filter narrows the list.
    only_quick = query_service.triage_items(db_session, uid, reason="quick")
    assert [i["id"] for i in only_quick["items"]] == [str(quick.id)]


@requires_db
def test_ordered_merge_keeps_sources_and_retains_secondary(db_session, make_user):
    from app.models.blog import PostSource
    from app.models.posts import Post
    from app.models.relations import EntityRelation
    from app.modules.posts import service
    from sqlalchemy import select

    uid = make_user().id
    primary = service.create_post(db_session, uid, title="主", markdown="正文A")
    secondary = service.create_post(db_session, uid, title="副", markdown="正文B")
    _source(db_session, uid, primary.id, "https://a.example")
    _source(db_session, uid, secondary.id, "https://b.example")
    db_session.commit()
    pv = primary.version

    merged = service.merge_posts(
        db_session,
        uid,
        primary.id,
        secondary.id,
        order="primary_first",
        current_version=pv,
    )
    db_session.commit()

    # Body concatenated in order.
    assert merged.markdown.index("正文A") < merged.markdown.index("正文B")
    assert merged.version == pv + 1

    # Both sources now belong to the merged (primary) article — none lost.
    src_posts = db_session.scalars(
        select(PostSource.post_id).where(PostSource.user_id == uid)
    ).all()
    assert all(pid == primary.id for pid in src_posts)
    assert len(src_posts) == 2

    # Secondary retained but discarded (recoverable), not hard-deleted.
    sec = db_session.get(Post, secondary.id)
    assert sec is not None
    assert sec.content_status == "discarded"
    assert sec.deleted_at is None

    # Provenance relation recorded (a merge-tagged derived_from).
    rel = db_session.scalar(
        select(EntityRelation).where(
            EntityRelation.source_id == primary.id,
            EntityRelation.relation_type == "derived_from",
        )
    )
    assert rel is not None and rel.target_id == secondary.id
    assert rel.metadata_json.get("merge") is True


@requires_db
def test_merge_rejects_self_and_stale_version(db_session, make_user):
    from app.core.errors import ValidationError, VersionConflictError
    from app.modules.posts import service

    uid = make_user().id
    a = service.create_post(db_session, uid, title="a", markdown="x")
    b = service.create_post(db_session, uid, title="b", markdown="y")
    db_session.commit()

    with pytest.raises(ValidationError):
        service.merge_posts(db_session, uid, a.id, a.id, current_version=a.version)
    with pytest.raises(VersionConflictError):
        service.merge_posts(db_session, uid, a.id, b.id, current_version=a.version + 9)


@requires_db
def test_list_filters_and_counts(db_session, make_user):
    from app.modules.posts import query_service, service

    uid = make_user().id
    p1 = service.create_post(db_session, uid, title="技术", markdown="hello")
    p1.content_class = "technical"
    p2 = service.create_post(db_session, uid, title="生活", markdown="world")
    p2.content_class = "life"
    archived = service.create_post(db_session, uid, title="旧", markdown="z")
    archived.content_status = "archived"
    db_session.commit()

    out = query_service.list_posts(db_session, uid)
    ids = {i["id"] for i in out["items"]}
    assert str(p1.id) in ids and str(p2.id) in ids
    assert str(archived.id) not in ids  # archived excluded by default

    tech = query_service.list_posts(db_session, uid, content_class="technical")
    assert [i["id"] for i in tech["items"]] == [str(p1.id)]

    found = query_service.list_posts(db_session, uid, search="hello")
    assert [i["id"] for i in found["items"]] == [str(p1.id)]
