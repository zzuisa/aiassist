"""Agent batches remain bounded on personal-server deployments."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def test_batch_over_limit_reports_actual_scope_and_requests_narrowing() -> None:
    from app.modules.agent.runner import BatchLimitExceededError, enforce_batch_limit

    with pytest.raises(BatchLimitExceededError) as caught:
        enforce_batch_limit(501, maximum=200)

    assert caught.value.requested == 501
    assert caught.value.maximum == 200
    assert "200" in str(caught.value)
    assert "缩小" in str(caught.value)
