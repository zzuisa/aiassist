"""Celery application: explicit queues, quorum/confirm settings, retry policy.

Queues mirror design.md §7. worker-fast consumes critical/notification/schedule/
search; worker-heavy consumes voice/image/llm/maintenance. Result backend is
disabled: business state lives in PostgreSQL (async_jobs), never in Celery.
"""

from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings

settings = get_settings()

celery = Celery("aiassist", broker=settings.amqp_dsn, backend=None)

# Exchanges (topic) per design.md §7.
commands_exchange = Exchange("aiassist.commands", type="topic", durable=True)

QUEUE_NAMES = [
    "critical",
    "notification",
    "schedule",
    "search",
    "voice",
    "image",
    "llm",
    "maintenance",
]

# Durable quorum queues with per-queue dead-letter routing.
task_queues = []
for name in QUEUE_NAMES:
    task_queues.append(
        Queue(
            name,
            exchange=commands_exchange,
            routing_key=f"{name}.#",
            durable=True,
            queue_arguments={
                "x-queue-type": "quorum",
                "x-dead-letter-exchange": "aiassist.dlx",
                "x-delivery-limit": 5,
            },
        )
    )

# Route command names (imperative) to their queue by prefix.
TASK_ROUTES = {
    "app.workers.tasks.notifications.send_critical_reminder": {"queue": "critical"},
    "app.workers.tasks.notifications.*": {"queue": "notification"},
    "app.workers.tasks.habits.*": {"queue": "schedule"},
    "app.workers.tasks.recurrence.*": {"queue": "schedule"},
    "app.workers.tasks.scheduling.*": {"queue": "schedule"},
    "app.workers.tasks.search.*": {"queue": "search"},
    "app.workers.tasks.voice.*": {"queue": "voice"},
    "app.workers.tasks.images.*": {"queue": "image"},
    "app.workers.tasks.capture_ai.*": {"queue": "llm"},
    "app.workers.tasks.blog.*": {"queue": "llm"},
    "app.workers.tasks.assistant.*": {"queue": "llm"},
    "app.workers.tasks.maintenance.*": {"queue": "maintenance"},
}

celery.conf.update(
    task_queues=task_queues,
    task_default_queue="notification",
    task_default_exchange="aiassist.commands",
    task_default_exchange_type="topic",
    task_routes=TASK_ROUTES,
    task_acks_late=True,
    task_reject_on_worker_lost=False,  # only idempotent tasks opt into requeue
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    task_ignore_result=True,
    broker_transport_options={"confirm_publish": True},
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    # Retry defaults; individual tasks refine countdown/backoff/jitter.
    task_default_retry_delay=10,
    task_annotations={"*": {"max_retries": 5}},
)

# Register task modules explicitly (autodiscover expects an app-per-package).
celery.conf.imports = (
    "app.workers.tasks.notifications",
    "app.workers.tasks.habits",
    "app.workers.tasks.maintenance",
)


# Load the Beat schedule (safe: celery is already configured above).
import app.workers.beat_schedule  # noqa: E402,F401
