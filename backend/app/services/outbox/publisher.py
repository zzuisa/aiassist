"""Transactional outbox: append (in business tx) + standalone publisher process.

``append_event`` is called inside a business transaction so the event is atomic
with the data change. The publisher claims pending rows with ``FOR UPDATE SKIP
LOCKED`` under a lease, publishes durable confirmed messages to RabbitMQ, then
marks them published. Delivery is at least once; consumers dedupe by event ID.
"""

from __future__ import annotations

import socket
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.observability import get_logger, get_trace_id
from app.models.foundation import OutboxEvent

log = get_logger("outbox")

LEASE_SECONDS = 30
BATCH_SIZE = 100
MAX_RETRY = 10


def append_event(
    session: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    routing_key: str,
    payload: dict,
    user_id: uuid.UUID | None = None,
    event_version: int = 1,
) -> OutboxEvent:
    """Add an outbox row to the current (business) transaction. No commit here."""
    event = OutboxEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        event_version=event_version,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        user_id=user_id,
        routing_key=routing_key,
        payload_json=payload,
        status="pending",
        trace_id=get_trace_id(),
    )
    session.add(event)
    return event


def _envelope(event: OutboxEvent) -> dict:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_version": event.event_version,
        "occurred_at": event.created_at.astimezone(UTC).isoformat()
        if event.created_at
        else datetime.now(UTC).isoformat(),
        "user_id": str(event.user_id) if event.user_id else None,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "trace_id": event.trace_id,
        "payload": event.payload_json,
    }


class OutboxPublisher:
    """Claims and publishes pending outbox events. Broker access is injected so
    tests can assert publish behavior without a live RabbitMQ."""

    def __init__(self, session_factory, publish_fn=None) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._publish_fn = publish_fn or self._publish_to_broker

    def _publish_to_broker(self, routing_key: str, body: dict) -> None:
        # Lazy import so the module is usable without a broker in unit tests.
        from kombu import Connection, Exchange

        from app.core.config import get_settings

        exchange = Exchange("aiassist.commands", type="topic", durable=True)
        with Connection(get_settings().amqp_dsn) as conn:
            producer = conn.Producer(serializer="json", confirm_publish=True)
            producer.publish(
                body,
                exchange=exchange,
                routing_key=routing_key,
                declare=[exchange],
                delivery_mode=2,
            )

    def claim_batch(self, session: Session, limit: int = BATCH_SIZE) -> list[OutboxEvent]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=LEASE_SECONDS)
        rows = (
            session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status.in_(["pending", "publishing"]),
                    OutboxEvent.next_attempt_at <= now,
                    (OutboxEvent.locked_until.is_(None)) | (OutboxEvent.locked_until < now),
                )
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = "publishing"
            row.locked_by = self._worker_id
            row.locked_until = lease_until
        session.flush()
        return list(rows)

    def process_once(self, limit: int = BATCH_SIZE) -> int:
        """Claim and publish one batch. Returns the number published."""
        published = 0
        session: Session = self._session_factory()
        try:
            batch = self.claim_batch(session, limit)
            session.commit()
            for event in batch:
                body = _envelope(event)
                try:
                    self._publish_fn(event.routing_key, body)
                except Exception as exc:  # broker/publish failure: back off
                    self._mark_failed(session, event.id, str(exc))
                    continue
                self._mark_published(session, event.id)
                published += 1
            return published
        finally:
            session.close()

    def _mark_published(self, session: Session, event_id: uuid.UUID) -> None:
        session.execute(
            text(
                "UPDATE outbox_events SET status='published', published_at=now(), "
                "locked_by=NULL, locked_until=NULL WHERE id=:id"
            ),
            {"id": event_id},
        )
        session.commit()

    def _mark_failed(self, session: Session, event_id: uuid.UUID, err: str) -> None:
        row = session.get(OutboxEvent, event_id)
        if row is None:
            return
        row.retry_count += 1
        row.last_error = err[:500]
        row.locked_by = None
        row.locked_until = None
        backoff = min(2**row.retry_count, 300)
        row.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff)
        row.status = "failed" if row.retry_count >= MAX_RETRY else "pending"
        session.commit()

    def run_forever(self, poll_interval: float = 1.0) -> None:  # pragma: no cover
        log.info("outbox_publisher_start", worker=self._worker_id)
        while True:
            try:
                count = self.process_once()
                if count == 0:
                    time.sleep(poll_interval)
            except Exception as exc:  # keep the loop alive
                log.error("outbox_publisher_error", error=str(exc))
                time.sleep(poll_interval)


def run_publisher() -> None:  # pragma: no cover
    from app.db.session import get_session_factory

    OutboxPublisher(get_session_factory()).run_forever()
