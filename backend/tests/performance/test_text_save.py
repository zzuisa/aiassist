"""Text-save latency budget (SC-001: p95 < 2s for task creation)."""

from __future__ import annotations

import time

import pytest
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.performance, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset():
    auth_service.reset_login_throttle()
    yield


def test_task_create_p95_under_budget(client, make_user):
    user = make_user()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    h = {"X-CSRF-Token": login.json()["csrf_token"]}

    durations = []
    for i in range(30):
        start = time.perf_counter()
        resp = client.post("/api/v1/tasks", json={"title": f"任务 {i}", "type": "task"}, headers=h)
        durations.append(time.perf_counter() - start)
        assert resp.status_code == 201

    durations.sort()
    p95 = durations[int(len(durations) * 0.95) - 1]
    assert p95 < 2.0, f"task-create p95 too slow: {p95:.3f}s"
