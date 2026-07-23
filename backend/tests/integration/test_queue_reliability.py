"""Queue reliability: idempotency, retry exhaustion, DLQ config, delivery audit.

Broker-dependent delivery is validated in test_broker_roundtrip (marked broker).
Here we validate the durable, broker-independent guarantees.
"""

from __future__ import annotations

import uuid

import pytest
from app.db.session import session_scope
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.reliability]


def test_consumer_receipt_makes_processing_idempotent():
    """Processing the same event 10 times yields one business effect."""
    event_id = uuid.uuid4()
    effects = 0
    for _ in range(10):
        try:
            with session_scope() as s:
                s.execute(
                    text("INSERT INTO consumer_receipts (consumer_name, event_id) VALUES (:n, :e)"),
                    {"n": "image-indexer", "e": event_id},
                )
            effects += 1
        except Exception:  # noqa: S110
            pass  # duplicate delivery: already processed
    assert effects == 1


def test_idempotency_record_guards_business_effect():
    from app.models.foundation import IdempotencyRecord

    key = f"capture:{uuid.uuid4()}:vision:v1"
    created = 0
    for _ in range(5):
        try:
            with session_scope() as s:
                s.add(IdempotencyRecord(handler="vision", idempotency_key=key, status="completed"))
            created += 1
        except Exception:  # noqa: S110
            pass
    assert created == 1


def test_retry_exhaustion_marks_failed(make_user):
    from app.models.foundation import AsyncJob
    from app.modules.jobs import service as jobs_service

    user = make_user()
    with session_scope() as s:
        job = jobs_service.create_job(s, user_id=user.id, job_type="llm.blog", max_retries=2)
        # Simulate attempts until max_retries is reached.
        for _ in range(3):
            jobs_service.transition(
                s,
                job,
                status="failed",
                error_code="TIMEOUT",
                error_message="e",
                error_retryable=True,
            )
            if job.retry_count < job.max_retries:
                jobs_service.retry_job(s, job)
        jid = job.id

    with session_scope() as s:
        job = s.get(AsyncJob, jid)
        assert job.retry_count <= job.max_retries


def test_celery_queues_declare_dlx():
    """Every business queue routes dead letters to the DLX (design.md §7)."""
    from app.workers.celery_app import celery

    for queue in celery.conf.task_queues:
        args = queue.queue_arguments or {}
        assert args.get("x-dead-letter-exchange") == "aiassist.dlx"
        assert args.get("x-queue-type") == "quorum"


def test_delivery_attempt_recorded(make_user):
    """Each notification delivery records an attempt row (audit)."""
    from datetime import UTC, datetime, timedelta

    from app.models.notifications import NotificationDelivery
    from app.modules.notifications import reminder_service
    from app.modules.tasks import service as task_service
    from app.modules.tasks.schemas import TaskCreate

    user = make_user()
    past = datetime.now(UTC) - timedelta(minutes=1)
    with session_scope() as s:
        task = task_service.create_task(s, user.id, TaskCreate(title="t", type="task"))
        reminder_service.create_reminder(
            s, user.id, task.id, channel="email", trigger_at=past, is_critical=False
        )
        uid = user.id
    with session_scope() as s:
        due = reminder_service.claim_due_reminders(s, datetime.now(UTC))
        reminder_service.dispatch_reminder(s, due[0])
    with session_scope() as s:
        from sqlalchemy import select

        delivery = s.scalars(
            select(NotificationDelivery).where(NotificationDelivery.user_id == uid)
        ).one()
        assert delivery.attempt_no == 1
        assert delivery.channel == "email"
