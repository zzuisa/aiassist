"""Durable jobs: transitions, event log, snapshot cursor, user isolation."""

from __future__ import annotations

import uuid

import pytest
from app.db.session import session_scope
from app.models.foundation import User
from app.modules.auth.service import hash_password
from app.modules.jobs import service as jobs_service

pytestmark = [pytest.mark.integration]


def _make_user(session) -> User:
    user = User(
        email=f"j-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("correct horse battery staple"),
        display_name="Job User",
        notification_preferences={},
    )
    session.add(user)
    session.flush()
    return user


def test_transition_appends_event_in_same_transaction() -> None:
    with session_scope() as s:
        user = _make_user(s)
        job = jobs_service.create_job(s, user_id=user.id, job_type="capture.analyze")
        jobs_service.transition(s, job, status="queued")
        jobs_service.transition(s, job, status="processing", progress=40, current_step="分析中")
        uid = user.id
        jid = job.id

    with session_scope() as s:
        events = jobs_service.events_after(s, uid, 0)
        # create(1) + queued + processing = 3 events, monotonically increasing ids
        assert len(events) == 3
        assert [e.id for e in events] == sorted(e.id for e in events)
        job = jobs_service.get_owned_job(s, uid, jid)
        assert job.status == "processing"
        assert job.progress == 40
        assert job.version == 3


def test_progress_never_decreases() -> None:
    with session_scope() as s:
        user = _make_user(s)
        job = jobs_service.create_job(s, user_id=user.id, job_type="image.process")
        jobs_service.transition(s, job, status="processing", progress=70)
        jobs_service.transition(s, job, progress=30)  # attempt to go backwards
        assert job.progress == 70


def test_failed_job_retry_requires_retryable() -> None:
    from app.core.errors import ConflictError

    with session_scope() as s:
        user = _make_user(s)
        job = jobs_service.create_job(s, user_id=user.id, job_type="llm.blog")
        jobs_service.transition(
            s, job, status="failed", error_code="X", error_message="no", error_retryable=False
        )
        with pytest.raises(ConflictError):
            jobs_service.retry_job(s, job)

    with session_scope() as s:
        user = _make_user(s)
        job = jobs_service.create_job(s, user_id=user.id, job_type="llm.blog")
        jobs_service.transition(
            s,
            job,
            status="failed",
            error_code="TIMEOUT",
            error_message="slow",
            error_retryable=True,
        )
        job = jobs_service.retry_job(s, job)
        assert job.status == "queued"
        assert job.retry_count == 1


def test_events_are_user_isolated() -> None:
    with session_scope() as s:
        a = _make_user(s)
        b = _make_user(s)
        ja = jobs_service.create_job(s, user_id=a.id, job_type="x")
        jobs_service.transition(s, ja, status="processing", progress=10)
        jb = jobs_service.create_job(s, user_id=b.id, job_type="y")
        jobs_service.transition(s, jb, status="processing", progress=10)
        aid, bid = a.id, b.id

    with session_scope() as s:
        a_events = jobs_service.events_after(s, aid, 0)
        b_events = jobs_service.events_after(s, bid, 0)
        a_jobs = {e.payload_json["job_id"] for e in a_events}
        b_jobs = {e.payload_json["job_id"] for e in b_events}
        assert a_jobs.isdisjoint(b_jobs)


def test_cross_user_job_access_is_404() -> None:
    from app.core.errors import NotFoundError

    with session_scope() as s:
        a = _make_user(s)
        b = _make_user(s)
        ja = jobs_service.create_job(s, user_id=a.id, job_type="x")
        jid = ja.id
        bid = b.id

    with session_scope() as s, pytest.raises(NotFoundError):
        jobs_service.get_owned_job(s, bid, jid)
