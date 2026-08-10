"""Progress values remain truthful when total work is unknown."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def test_unknown_total_does_not_fabricate_numeric_progress() -> None:
    from app.modules.agent.status import progress_payload

    assert progress_payload(None, None, "正在分析可用能力") is None


def test_known_total_includes_stage_label() -> None:
    from app.modules.agent.status import progress_payload

    assert progress_payload(2, 5, "正在查询") == {
        "current": 2,
        "total": 5,
        "stage_label": "正在查询",
    }
