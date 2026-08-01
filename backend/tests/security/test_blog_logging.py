"""Blog observability must correlate entities without leaking private content."""

from __future__ import annotations

import io
import json
import uuid

import pytest
import structlog
from app.core import observability

pytestmark = [pytest.mark.security]


def test_nested_blog_content_and_credentials_are_redacted() -> None:
    buffer = io.StringIO()
    observability.reset_metrics()
    observability.set_trace_id("a" * 32)
    structlog.configure(
        processors=[
            observability._redact_processor,
            observability._capture_blog_metric,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buffer),
        cache_logger_on_first_use=False,
    )
    logger = structlog.get_logger("test.blog")
    logger.info(
        "blog_optimize_completed",
        job_id="job-safe",
        post_id="post-safe",
        source_id="source-safe",
        skill_version_id="skill-safe",
        outcome="complete",
        payload={
            "markdown": "PRIVATE ARTICLE SENTINEL",
            "nested": {"prompt": "PRIVATE PROMPT SENTINEL"},
        },
        authorization="Bearer secret-credential",
        callback_url="https://example.test/x?token=secret-query&safe=1",
    )

    rendered = buffer.getvalue()
    record = json.loads(rendered)
    assert "PRIVATE ARTICLE SENTINEL" not in rendered
    assert "PRIVATE PROMPT SENTINEL" not in rendered
    assert "secret-credential" not in rendered
    assert "secret-query" not in rendered
    assert record["payload"] == "[redacted]"
    assert record["authorization"] == "[redacted]"
    assert record["job_id"] == "job-safe"
    assert record["post_id"] == "post-safe"
    assert record["source_id"] == "source-safe"
    assert record["skill_version_id"] == "skill-safe"
    assert record["trace_id"] == "a" * 32

    metrics = observability.metrics_snapshot()
    assert metrics == [
        {
            "name": "blog.events_total",
            "labels": {"event": "blog_optimize_completed", "outcome": "complete"},
            "value": 1,
        }
    ]


def test_safe_blog_context_keeps_only_hash_length_codes_and_ids() -> None:
    private = "正文里有个人信息和 https://example.test/?api_key=private"
    context = observability.safe_blog_context(
        job_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        post_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        source_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        skill_version_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        content=private,
        validation_codes=["protected_token_changed"],
    )
    serialized = json.dumps(context, ensure_ascii=False)
    assert private not in serialized
    assert context["content_chars"] == len(private)
    assert len(context["content_sha256"]) == 64
    assert context["validation_codes"] == ["protected_token_changed"]
    assert set(context) == {
        "job_id",
        "post_id",
        "source_id",
        "skill_version_id",
        "content_chars",
        "content_sha256",
        "validation_codes",
    }


def test_metrics_drop_entity_ids_and_reject_unbounded_names() -> None:
    observability.reset_metrics()
    observability.record_metric(
        "blog.jobs_total",
        operation="skill_test",
        outcome="failed",
        error_code="timeout",
        job_id="must-not-be-a-label",
    )
    metric = observability.metrics_snapshot()[0]
    assert metric["labels"] == {
        "error_code": "timeout",
        "operation": "skill_test",
        "outcome": "failed",
    }
    with pytest.raises(ValueError):
        observability.record_metric("Invalid Metric Name")
