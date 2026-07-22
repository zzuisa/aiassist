"""Transactional outbox: atomic append, crash boundary, dedupe, lease recovery."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.db.session import get_session_factory, session_scope
from app.models.foundation import OutboxEvent, User
from app.modules.auth.service import hash_password
from app.services.outbox.publisher import OutboxPublisher, append_event
from sqlalchemy import text

pytestmark = [pytest.mark.integration]


def _make_user(session) -> User:
    user = User(
        email=f"o-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("correct horse battery staple"),
        display_name="Outbox User",
        notification_preferences={},
    )
    session.add(user)
    session.flush()
    return user


def test_append_is_atomic_with_business_write(db_session) -> None:
    user = _make_user(db_session)
    append_event(
        db_session,
        event_type="task.created",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        routing_key="search.index.task",
        payload={"hello": "world"},
        user_id=user.id,
    )
    db_session.commit()
    rows = db_session.scalars(select_outbox()).all()
    assert len(rows) == 1
    assert rows[0].status == "pending"


def select_outbox():
    from sqlalchemy import select

    return select(OutboxEvent)


def test_crash_before_commit_leaves_no_event(db_session) -> None:
    user = _make_user(db_session)
    append_event(
        db_session,
        event_type="task.created",
        aggregate_type="task",
        aggregate_id=uuid.uuid4(),
        routing_key="search.index.task",
        payload={},
        user_id=user.id,
    )
    db_session.rollback()  # simulate crash before commit
    assert db_session.scalars(select_outbox()).all() == []


def test_publisher_publishes_pending_and_marks_published() -> None:
    published: list[tuple[str, dict]] = []

    def fake_publish(routing_key: str, body: dict) -> None:
        published.append((routing_key, body))

    with session_scope() as s:
        user = _make_user(s)
        append_event(
            s,
            event_type="task.created",
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            routing_key="search.index.task",
            payload={"a": 1},
            user_id=user.id,
        )

    pub = OutboxPublisher(get_session_factory(), publish_fn=fake_publish)
    count = pub.process_once()
    assert count == 1
    assert published[0][0] == "search.index.task"
    assert published[0][1]["event_type"] == "task.created"

    with session_scope() as s:
        row = s.scalars(select_outbox()).one()
        assert row.status == "published"
        assert row.published_at is not None


def test_publish_failure_backs_off_and_stays_pending() -> None:
    def failing_publish(routing_key: str, body: dict) -> None:
        raise RuntimeError("broker down")

    with session_scope() as s:
        user = _make_user(s)
        append_event(
            s,
            event_type="task.created",
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            routing_key="search.index.task",
            payload={},
            user_id=user.id,
        )

    pub = OutboxPublisher(get_session_factory(), publish_fn=failing_publish)
    assert pub.process_once() == 0
    with session_scope() as s:
        row = s.scalars(select_outbox()).one()
        assert row.status == "pending"
        assert row.retry_count == 1
        assert row.next_attempt_at > datetime.now(UTC)


def test_duplicate_delivery_dedupes_via_consumer_receipt() -> None:
    """A consumer inserts (name,event_id); the second insert conflicts."""
    event_id = uuid.uuid4()
    with session_scope() as s:
        s.execute(
            text("INSERT INTO consumer_receipts (consumer_name, event_id) VALUES (:n, :e)"),
            {"n": "search-indexer", "e": event_id},
        )
    # Second delivery: conflict means already processed.
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), session_scope() as s:
        s.execute(
            text("INSERT INTO consumer_receipts (consumer_name, event_id) VALUES (:n, :e)"),
            {"n": "search-indexer", "e": event_id},
        )


def test_expired_lease_is_reclaimed() -> None:
    published: list[str] = []

    with session_scope() as s:
        user = _make_user(s)
        ev = append_event(
            s,
            event_type="task.created",
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            routing_key="search.index.task",
            payload={},
            user_id=user.id,
        )
        s.flush()
        # Simulate a stale lease from a crashed publisher.
        ev.status = "publishing"
        ev.locked_by = "dead-worker"
        ev.locked_until = datetime.now(UTC) - timedelta(minutes=5)

    pub = OutboxPublisher(get_session_factory(), publish_fn=lambda rk, body: published.append(rk))
    assert pub.process_once() == 1
    assert published == ["search.index.task"]
