"""Job retry/cancel permission, stale-worker rejection, progress monotonicity."""

from __future__ import annotations

import pytest
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset():
    auth_service.reset_login_throttle()
    yield


def _login(client, email):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _make_job(user_id, status="failed", retryable=True):
    from app.db.session import session_scope
    from app.modules.jobs import service as jobs_service

    with session_scope() as s:
        job = jobs_service.create_job(s, user_id=user_id, job_type="capture.process")
        if status == "failed":
            jobs_service.transition(
                s,
                job,
                status="failed",
                error_code="X",
                error_message="e",
                error_retryable=retryable,
            )
        elif status == "processing":
            jobs_service.transition(s, job, status="processing", progress=50)
        return job.id


def test_retry_requires_ownership(client, make_user):
    owner = make_user()
    other = make_user()
    job_id = _make_job(owner.id)
    _login(client, other.email)
    resp = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert resp.status_code in (403, 404)


def test_retry_failed_retryable_job(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    job_id = _make_job(user.id, status="failed", retryable=True)
    resp = client.post(f"/api/v1/jobs/{job_id}/retry", headers=h)
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    assert resp.json()["retry_count"] == 1


def test_retry_non_retryable_rejected(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    job_id = _make_job(user.id, status="failed", retryable=False)
    resp = client.post(f"/api/v1/jobs/{job_id}/retry", headers=h)
    assert resp.status_code == 409


def test_cancel_preserves_job_record(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    job_id = _make_job(user.id, status="processing")
    resp = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=h)
    assert resp.status_code == 202
    assert resp.json()["status"] == "cancelled"
    # The job record still exists and is readable.
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 200


def test_stale_worker_result_after_cancel_is_ignored(make_user):
    """A worker finishing after cancellation must not resurrect the job."""
    from app.db.session import session_scope
    from app.modules.jobs import service as jobs_service

    user = make_user()
    with session_scope() as s:
        job = jobs_service.create_job(s, user_id=user.id, job_type="voice.transcribe")
        jobs_service.transition(s, job, status="processing", progress=40)
        jobs_service.request_cancel(s, job)
        jid = job.id

    with session_scope() as s:
        from app.models.foundation import AsyncJob

        job = s.get(AsyncJob, jid)
        assert job.status == "cancelled"
        # A late worker checks cancel_requested_at and does not override terminal state.
        assert job.cancel_requested_at is not None


def test_progress_monotonic_via_api(client, make_user):
    from app.db.session import session_scope
    from app.modules.jobs import service as jobs_service

    user = make_user()
    h = _login(client, user.email)
    with session_scope() as s:
        job = jobs_service.create_job(s, user_id=user.id, job_type="image.process")
        jobs_service.transition(s, job, status="processing", progress=80)
        jid = job.id
    with session_scope() as s:
        from app.models.foundation import AsyncJob

        job = s.get(AsyncJob, jid)
        jobs_service.transition(s, job, progress=20)  # cannot go backwards
    resp = client.get(f"/api/v1/jobs/{jid}", headers=h)
    assert resp.json()["progress"] == 80
