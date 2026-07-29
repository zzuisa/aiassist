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
def test_url_capture_commits_when_broker_is_down(db_session, user_id, monkeypatch):
    """The durable rows persist even though the Celery enqueue raises."""
    from app.models.foundation import AsyncJob, OutboxEvent
    from app.models.blog import PostSource
    from app.modules.posts import capture_service
    from app.workers.tasks import blog as blog_task

    # Simulate a dead broker: .delay() raises. capture_service must swallow it.
    def _broker_down(*_a, **_k):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(blog_task.extract, "delay", _broker_down)

    post, src, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a", note="n"
    )
    db_session.commit()

    # Everything is durable despite the failed enqueue.
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
        url_extractor, "extract_article",
        lambda html, url: {"title": "T", "text": "body", "markdown": "body",
                           "author": None, "site": None},
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
