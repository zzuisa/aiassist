"""Search performance smoke: seed many rows and check p95 stays well under budget.

The full 100k acceptance runs in CI/perf environments; here we use a bounded seed
(configurable via SEARCH_PERF_ROWS) so the suite stays fast by default while still
exercising the query path against real PostgreSQL indexes.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from app.db.session import session_scope
from app.modules.search import service as search_service
from sqlalchemy import text

pytestmark = [pytest.mark.performance, pytest.mark.integration]

ROWS = int(os.environ.get("SEARCH_PERF_ROWS", "3000"))


def test_search_p95_under_budget(make_user):
    user = make_user()
    uid = user.id
    # Bulk-insert tasks with a searchable needle in a fraction of rows.
    with session_scope() as s:
        rows = []
        for i in range(ROWS):
            title = f"任务 {i}" + (" 独特针" if i % 500 == 0 else "")
            rows.append({"id": uuid.uuid4(), "u": uid, "t": title})
        s.execute(
            text(
                "INSERT INTO tasks (id, user_id, type, title, status, priority, importance, "
                "is_fixed, is_ai_adjustable, is_splittable, version, created_at, updated_at) "
                "VALUES (:id, :u, 'task', :t, 'todo', 0, 0, false, true, false, 1, now(), now())"
            ),
            rows,
        )

    durations = []
    for _ in range(20):
        start = time.perf_counter()
        with session_scope() as s:
            result = search_service.search(s, uid, "独特针", types=["task"])
        durations.append(time.perf_counter() - start)
        assert result["groups"]

    durations.sort()
    p95 = durations[int(len(durations) * 0.95) - 1]
    # Generous budget for a bounded seed; the real 100k budget is 2s (SC-008).
    assert p95 < 2.0, f"search p95 too slow: {p95:.3f}s for {ROWS} rows"
