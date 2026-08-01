"""Blog capture failure matrix (US1, T032): survival with no broker/Worker.

These cover the durable guarantees that must hold when intelligence and
background processing are unavailable:

* broker down  — a URL capture still commits Post + PostSource + Job + Outbox
  even though the Celery enqueue fails;
* duplicate command — running extraction twice is idempotent;
* worker crash — an uncaught fetch error rolls back cleanly, leaving the source
  re-runnable (never a lost or half-written state);
* timeout — a fetch timeout is recorded as a retryable failure, not a crash.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from tests.conftest import requires_db

pytestmark = [pytest.mark.reliability, pytest.mark.integration]


@pytest.fixture
def user_id(make_user):
    return make_user().id


@requires_db
def test_url_capture_uses_outbox_only_after_commit(db_session, user_id, monkeypatch):
    """Capture never dispatches directly from inside the business transaction."""
    from app.models.blog import PostSource
    from app.models.foundation import AsyncJob, OutboxEvent
    from app.modules.posts import capture_service
    from app.workers.tasks import blog as blog_task

    def _premature_dispatch(*_a, **_k):
        raise AssertionError("Celery must not be called before commit")

    monkeypatch.setattr(blog_task.extract, "delay", _premature_dispatch)

    _post, src, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a", note="n"
    )
    db_session.commit()

    # Everything is durable and the Outbox publisher is the sole dispatcher.
    assert db_session.get(PostSource, src.id).status == "pending"
    assert db_session.get(AsyncJob, job.id) is not None
    outbox_count = db_session.scalar(
        select(func.count()).select_from(OutboxEvent).where(OutboxEvent.aggregate_id == src.id)
    )
    assert outbox_count == 1  # Outbox row survives as the durable driver.


@requires_db
def test_extraction_is_idempotent_on_duplicate_delivery(db_session, user_id, monkeypatch):
    from app.models.blog import PostSource
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    _post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a"
    )
    db_session.commit()

    calls = {"n": 0}

    def _fetch(url, **kw):
        calls["n"] += 1
        return url_extractor.FetchResult(
            final_url=url, status_code=200, content_type="text/html", text="<html/>"
        )

    monkeypatch.setattr(url_extractor, "fetch_url", _fetch)
    monkeypatch.setattr(
        url_extractor,
        "extract_article",
        lambda html, url: {
            "title": "T",
            "text": "body",
            "markdown": "body",
            "author": None,
            "site": None,
        },
    )

    assert blog_task.extract_source(src.id) == "completed"
    # A duplicate delivery of the same command must not fetch again or change state.
    assert blog_task.extract_source(src.id) == "skipped"
    assert calls["n"] == 1
    db_session.expire_all()
    assert db_session.get(PostSource, src.id).status == "completed"


@requires_db
def test_worker_crash_midway_leaves_source_rerunnable(db_session, user_id, monkeypatch):
    """An uncaught error during fetch rolls back; the source is never lost."""
    from app.models.blog import PostSource
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    _post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a"
    )
    db_session.commit()

    def _crash(url, **kw):
        raise MemoryError("worker OOM")

    monkeypatch.setattr(url_extractor, "fetch_url", _crash)

    with pytest.raises(MemoryError):
        blog_task.extract_source(src.id)

    # session_scope rolled the whole attempt back — the source is still pending
    # (re-runnable), never stuck half-written.
    db_session.expire_all()
    reloaded = db_session.get(PostSource, src.id)
    assert reloaded.status == "pending"
    assert reloaded.original_text is None


@requires_db
def test_timeout_is_recorded_as_retryable_failure(db_session, user_id, monkeypatch):
    from app.models.blog import PostSource
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    _post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a"
    )
    db_session.commit()

    def _timeout(url, **kw):
        raise url_extractor.UrlSecurityError("request timed out", code="timeout")

    monkeypatch.setattr(url_extractor, "fetch_url", _timeout)
    assert blog_task.extract_source(src.id) == "failed"
    db_session.expire_all()
    failed = db_session.get(PostSource, src.id)
    assert failed.status == "failed"
    assert failed.error_code == "timeout"
    # And it can be retried exactly once into a fresh pending attempt.
    capture_service.retry_source(db_session, user_id, src.id)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(PostSource, src.id).status == "pending"


@requires_db
def test_taxonomy_merge_duplicate_delivery_is_idempotent(db_session, user_id):
    from app.models.blog import TaxonomyMerge
    from app.modules.posts import service, taxonomy_service
    from app.workers.tasks import blog as blog_task

    source = taxonomy_service.create_item(db_session, user_id, "category", name="源")
    target = taxonomy_service.create_item(db_session, user_id, "category", name="目标")
    post = service.create_post(db_session, user_id, title="文章", markdown="正文")
    post.category_id = uuid.UUID(source["id"])
    audit = TaxonomyMerge(
        id=uuid.uuid4(),
        user_id=user_id,
        kind="category",
        source_id=uuid.UUID(source["id"]),
        target_id=uuid.UUID(target["id"]),
        status="pending",
    )
    db_session.add(audit)
    db_session.commit()
    assert blog_task.run_taxonomy_merge(audit.id) == "completed"
    assert blog_task.run_taxonomy_merge(audit.id) == "completed"
    db_session.expire_all()
    assert db_session.get(TaxonomyMerge, audit.id).status == "completed"


@requires_db
def test_large_taxonomy_merge_request_is_durable_and_deduplicated(db_session, user_id, monkeypatch):
    from app.models.blog import TaxonomyMerge
    from app.models.foundation import OutboxEvent
    from app.modules.posts import taxonomy_service

    source = taxonomy_service.create_item(db_session, user_id, "tag", name="旧标签")
    target = taxonomy_service.create_item(db_session, user_id, "tag", name="新标签")
    monkeypatch.setattr(taxonomy_service, "BACKGROUND_MERGE_THRESHOLD", 0)

    first_status, first_job = taxonomy_service.request_merge(
        db_session,
        user_id,
        "tag",
        uuid.UUID(source["id"]),
        uuid.UUID(target["id"]),
    )
    second_status, second_job = taxonomy_service.request_merge(
        db_session,
        user_id,
        "tag",
        uuid.UUID(source["id"]),
        uuid.UUID(target["id"]),
    )
    db_session.commit()

    assert first_status == second_status == "queued"
    assert first_job.id == second_job.id
    assert db_session.query(TaxonomyMerge).count() == 1
    assert db_session.query(OutboxEvent).filter_by(event_type="blog.taxonomy_merge").count() == 1


@requires_db
def test_keyword_recompute_redelivery_preserves_manual_links(db_session, user_id):
    from app.models.blog import PostKeywordLink
    from app.modules.posts import service, taxonomy_service
    from app.workers.tasks import blog as blog_task

    keyword = taxonomy_service.create_item(db_session, user_id, "keyword", name="数据库")
    post = service.create_post(db_session, user_id, title="文章", markdown="数据库")
    manual = PostKeywordLink(
        post_id=post.id, keyword_id=uuid.UUID(keyword["id"]), user_id=user_id, source="user"
    )
    db_session.add(manual)
    job = taxonomy_service.request_keyword_recompute(db_session, user_id)
    db_session.commit()

    assert blog_task.run_keyword_recompute(job.id, user_id) == "completed"
    assert blog_task.run_keyword_recompute(job.id, user_id) == "completed"
    db_session.expire_all()
    # Recompute is idempotent and never replaces manually maintained links.
    assert db_session.get(PostKeywordLink, (post.id, uuid.UUID(keyword["id"]))) is not None


# ---------------------------------------------------------------------------
# US3: AI pipeline failure matrix (T067)
# ---------------------------------------------------------------------------


def _seed_skill(session, user_id):
    import uuid as _u

    from app.models.blog import BlogSkill, BlogSkillDefault, BlogSkillVersion

    config = {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "x",
        "content_rules": [],
        "title_rules": [],
        "summary_rules": [],
        "body_structure": [],
        "taxonomy_rules": [],
        "keyword_rules": [],
        "prohibitions": ["p"],
        "field_policies": {"title": "allow_overwrite"},
        "output_fields": ["title"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [],
        "recommended_model": "m",
        "max_content_chars": 200000,
        "long_content_strategy": "reject",
    }
    skill = BlogSkill(id=_u.uuid4(), user_id=user_id, name="s", enabled=True)
    session.add(skill)
    session.flush()
    v = BlogSkillVersion(
        id=_u.uuid4(),
        user_id=user_id,
        skill_id=skill.id,
        version_number=1,
        config_json=config,
        schema_version="blog-skill-config.v1",
        recommended_model="m",
        max_content_chars=200000,
        long_content_strategy="reject",
    )
    session.add(v)
    session.flush()
    skill.current_version_id = v.id
    session.add(
        BlogSkillDefault(
            id=_u.uuid4(),
            user_id=user_id,
            scope_type="global",
            scope_key="*",
            skill_id=skill.id,
        )
    )
    session.flush()


def _opt_result(**over):
    from app.services.llm.schemas import BlogOptimizationV1

    data = {
        "schema_version": "blog-optimization.v1",
        "title": "T",
        "subtitle": None,
        "summary": None,
        "markdown": "body",
        "content_class_suggestion": None,
        "content_type_suggestion": None,
        "category_suggestions": [],
        "tag_suggestions": [],
        "keyword_suggestions": [],
        "occurred_at": None,
        "location": None,
        "project": None,
        "source_summary": None,
        "structured_fields": {},
        "related_post_suggestions": [],
        "claims": [],
        "warnings": [],
    }
    data.update(over)
    return BlogOptimizationV1.model_validate(data)


class _GW:
    def __init__(self, result=None, error=None):
        self._r, self._e = result, error

    def structured(self, request):
        if self._e:
            raise self._e
        return self._r


@requires_db
def test_provider_timeout_fails_run_without_candidate(db_session, user_id, monkeypatch):
    import app.services.llm.gateway as gw
    from app.models.blog import PostAICandidate, PostAIRun
    from app.modules.posts import ai_service, service
    from app.services.llm.base import LLMError
    from app.workers.tasks import blog as blog_task

    _seed_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()
    _j, run, _ = ai_service.submit_optimization(
        db_session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="full",
        provider_key="aiassist",
    )
    db_session.commit()

    monkeypatch.setattr(gw, "get_llm_gateway", lambda: _GW(error=LLMError("timeout", "slow")))
    assert blog_task.optimize_run(run.id, "all", [], None) == "failed"
    db_session.expire_all()
    assert db_session.get(PostAIRun, run.id).outcome == "failed"
    from sqlalchemy import select

    assert (
        db_session.scalar(select(PostAICandidate).where(PostAICandidate.ai_run_id == run.id))
        is None
    )


@requires_db
def test_cancellation_before_generation_is_honored(db_session, user_id, monkeypatch):
    import app.services.llm.gateway as gw
    from app.models.blog import PostAICandidate
    from app.modules.posts import ai_service, service
    from app.workers.tasks import blog as blog_task

    _seed_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()
    _j, run, _ = ai_service.submit_optimization(
        db_session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="full",
        provider_key="aiassist",
    )
    # User cancels before the worker runs.
    ai_service.cancel_run(db_session, user_id, run.id)
    db_session.commit()

    # The gateway must never be called once cancelled.
    def _boom():
        raise AssertionError("gateway called after cancel")

    monkeypatch.setattr(gw, "get_llm_gateway", _boom)
    assert blog_task.optimize_run(run.id, "all", [], None) == "cancelled"
    db_session.expire_all()
    from sqlalchemy import select

    assert (
        db_session.scalar(select(PostAICandidate).where(PostAICandidate.ai_run_id == run.id))
        is None
    )


@requires_db
def test_duplicate_worker_delivery_is_idempotent(db_session, user_id, monkeypatch):
    import app.services.llm.gateway as gw
    from app.models.blog import PostAICandidate
    from app.modules.posts import ai_service, service
    from app.workers.tasks import blog as blog_task
    from sqlalchemy import func, select

    _seed_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()
    _j, run, _ = ai_service.submit_optimization(
        db_session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="full",
        provider_key="aiassist",
    )
    db_session.commit()

    monkeypatch.setattr(gw, "get_llm_gateway", lambda: _GW(result=_opt_result()))
    assert blog_task.optimize_run(run.id, "all", [], None) == "complete"
    # A redelivered command for a finished run must not create a second candidate.
    assert blog_task.optimize_run(run.id, "all", [], None) == "skipped"
    db_session.expire_all()
    count = db_session.scalar(
        select(func.count()).select_from(PostAICandidate).where(PostAICandidate.ai_run_id == run.id)
    )
    assert count == 1


# ---------------------------------------------------------------------------
# Candidate decision race + duplicate + staleness (spec 005, US4, T082)
# ---------------------------------------------------------------------------


def _seed_candidate(session, user_id):
    from app.modules.posts import ai_service, service

    _seed_skill(session, user_id)
    post = service.create_post(session, user_id, title="V1标题", markdown="V1正文")
    post.summary = "V1摘要"
    session.flush()
    _j, run, _ = ai_service.submit_optimization(
        session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="full",
        provider_key="aiassist",
    )
    candidate = ai_service.save_candidate(
        session,
        run,
        candidate_markdown="AI正文",
        field_diff={
            "summary": {"from": "V1摘要", "to": "AI摘要", "classification": "allow_overwrite"},
            "markdown": {"from": "V1正文", "to": "AI正文", "classification": "allow_overwrite"},
        },
        validation={"outcome": "complete"},
        outcome="complete",
    )
    session.commit()
    return post, candidate


def test_duplicate_decision_is_rejected(db_session, user_id):
    """A second terminal decision on the same candidate must fail, not double-apply."""
    from app.core.errors import ConflictError
    from app.models.posts import Post
    from app.modules.posts import ai_service

    post, candidate = _seed_candidate(db_session, user_id)
    ai_service.decide_candidate(
        db_session,
        user_id,
        candidate.id,
        action="apply_all",
        current_version=post.version,
    )
    db_session.commit()
    p = db_session.get(Post, post.id)
    with pytest.raises(ConflictError):
        ai_service.decide_candidate(
            db_session,
            user_id,
            candidate.id,
            action="reject",
            current_version=p.version,
        )


def test_apply_after_user_edit_never_clobbers_body(db_session, user_id):
    """Apply-vs-save race: user edits body, then applies only metadata → body kept."""
    from app.models.posts import Post
    from app.modules.posts import ai_service

    post, candidate = _seed_candidate(db_session, user_id)
    post.markdown = "用户并发编辑V2"
    post.version += 1
    db_session.commit()

    ai_service.decide_candidate(
        db_session,
        user_id,
        candidate.id,
        action="apply_fields",
        selected_fields=["summary"],
        current_version=post.version,
    )
    db_session.commit()
    p = db_session.get(Post, post.id)
    assert p.markdown == "用户并发编辑V2"  # concurrent edit survives
    assert p.summary == "AI摘要"


def test_stale_version_blocks_decision(db_session, user_id):
    from app.core.errors import VersionConflictError
    from app.modules.posts import ai_service

    post, candidate = _seed_candidate(db_session, user_id)
    with pytest.raises(VersionConflictError):
        ai_service.decide_candidate(
            db_session,
            user_id,
            candidate.id,
            action="apply_all",
            current_version=post.version - 1,
        )


# ---------------------------------------------------------------------------
# Batch partial failure + archive/discard recoverability (spec 005, US6, T114)
# ---------------------------------------------------------------------------


def test_batch_partial_failure_does_not_roll_back_successes(db_session, user_id):
    """One bad item must not undo the others (per-item SAVEPOINT isolation)."""

    from app.models.posts import Post
    from app.modules.posts import service

    a = service.create_post(db_session, user_id, title="a", markdown="x")
    b = service.create_post(db_session, user_id, title="b", markdown="y")
    db_session.commit()
    bogus = uuid.uuid4()

    results = service.batch_operation(
        db_session, user_id, [a.id, bogus, b.id], "set_class", {"content_class": "life"}
    )
    db_session.commit()

    ok = {r["id"]: r["ok"] for r in results}
    assert ok[str(a.id)] is True and ok[str(b.id)] is True
    assert ok[str(bogus)] is False
    # The successful items persisted despite the failure in between.
    assert db_session.get(Post, a.id).content_class == "life"
    assert db_session.get(Post, b.id).content_class == "life"


def test_archive_and_discard_are_recoverable_states(db_session, user_id):
    """Archive/discard change status only — the row and its data survive."""
    from app.models.posts import Post
    from app.modules.posts import service

    a = service.create_post(db_session, user_id, title="a", markdown="keep me")
    b = service.create_post(db_session, user_id, title="b", markdown="keep me too")
    db_session.commit()

    service.batch_operation(db_session, user_id, [a.id], "archive", {})
    service.batch_operation(db_session, user_id, [b.id], "discard", {})
    db_session.commit()

    ra = db_session.get(Post, a.id)
    rb = db_session.get(Post, b.id)
    assert ra.content_status == "archived" and ra.deleted_at is None and ra.markdown == "keep me"
    assert rb.content_status == "discarded" and rb.deleted_at is None
