"""Real-broker round trip: outbox publisher -> RabbitMQ -> consumer.

Marked ``broker``; runs against a real RabbitMQ (CI provides one). Verifies that
the publisher publishes a durable, confirmed message that a consumer receives on
the routed queue — i.e. reliability is not validated by Celery eager mode.
"""

from __future__ import annotations

import os
import uuid

import pytest
from app.db.session import get_session_factory, session_scope
from app.models.foundation import User
from app.modules.auth.service import hash_password
from app.services.outbox.publisher import OutboxPublisher, append_event

pytestmark = [pytest.mark.integration, pytest.mark.broker]

AMQP_URL = os.environ.get("AMQP_URL")


def _broker_available() -> bool:
    if not AMQP_URL:
        return False
    try:
        from kombu import Connection

        with Connection(AMQP_URL, connect_timeout=3) as conn:
            conn.connect()
        return True
    except Exception:
        return False


requires_broker = pytest.mark.skipif(
    not _broker_available(), reason="AMQP_URL RabbitMQ broker is not reachable"
)


@requires_broker
def test_publisher_delivers_to_routed_queue() -> None:
    from kombu import Connection, Exchange, Queue

    exchange = Exchange("aiassist.commands", type="topic", durable=True)
    queue_name = f"test.search.{uuid.uuid4().hex[:8]}"
    queue = Queue(
        queue_name,
        exchange=exchange,
        routing_key="search.index.#",
        durable=True,
        queue_arguments={"x-queue-type": "quorum"},
    )

    with Connection(AMQP_URL) as conn:
        queue(conn.channel()).declare()

    with session_scope() as s:
        user = User(
            email=f"b-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("correct horse battery staple"),
            display_name="Broker User",
            notification_preferences={},
        )
        s.add(user)
        s.flush()
        append_event(
            s,
            event_type="task.created",
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            routing_key="search.index.task",
            payload={"n": 1},
            user_id=user.id,
        )

    published = OutboxPublisher(get_session_factory()).process_once()
    assert published == 1

    received: list[dict] = []
    with Connection(AMQP_URL) as conn, conn.SimpleQueue(queue) as sq:
        msg = sq.get(block=True, timeout=10)
        received.append(msg.payload)
        msg.ack()

    assert received[0]["event_type"] == "task.created"
    assert received[0]["payload"]["n"] == 1

    # cleanup
    with Connection(AMQP_URL) as conn:
        conn.channel().queue_delete(queue_name)
