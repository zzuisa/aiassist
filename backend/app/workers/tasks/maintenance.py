"""Low-priority maintenance tasks: outbox reconcile, orphan cleanup."""

from __future__ import annotations

from app.core.observability import get_logger
from app.db.session import get_session_factory
from app.services.outbox.publisher import OutboxPublisher
from app.workers.celery_app import celery

log = get_logger("worker.maintenance")


@celery.task(name="app.workers.tasks.maintenance.reconcile_outbox")
def reconcile_outbox() -> int:
    """Safety net: publish any pending outbox rows the publisher missed."""
    published = OutboxPublisher(get_session_factory()).process_once()
    if published:
        log.info("outbox_reconcile", published=published)
    return published
