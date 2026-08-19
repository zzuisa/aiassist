"""Low-priority maintenance tasks: outbox reconcile, orphan cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.observability import get_logger
from app.db.session import get_session_factory, session_scope
from app.models.foundation import AsyncJob
from app.models.voice import VoiceRecord
from app.modules.jobs import service as jobs_service
from app.services.outbox.publisher import OutboxPublisher
from app.workers.celery_app import celery

log = get_logger("worker.maintenance")

# Non-terminal job states that can get orphaned (worker crash, old code paths).
_NON_TERMINAL = ("pending", "queued", "processing", "waiting_user")
# A non-terminal job untouched this long is considered stale and cancelled.
_STALE_AFTER = timedelta(hours=24)


@celery.task(name="app.workers.tasks.maintenance.reconcile_outbox")
def reconcile_outbox() -> int:
    """Safety net: publish any pending outbox rows the publisher missed."""
    published = OutboxPublisher(get_session_factory()).process_once()
    if published:
        log.info("outbox_reconcile", published=published)
    return published


@celery.task(name="app.workers.tasks.maintenance.cleanup_stale_jobs")
def cleanup_stale_jobs() -> int:
    """Retire background jobs that can never reach a terminal state on their own.

    Two cases the task center would otherwise show forever:
    1. Orphaned voice jobs: a `voice.transcribe` job left in `waiting_user` while
       its record already moved on (legacy pre-auto-confirm flow). We reconcile
       the job to the record's real outcome.
    2. Generic stale jobs: any non-terminal job untouched for >24h is cancelled.
    """
    cleaned = 0
    now = datetime.now(UTC)
    with session_scope() as s:
        jobs = list(s.scalars(select(AsyncJob).where(AsyncJob.status.in_(_NON_TERMINAL))).all())
        for job in jobs:
            # Case 1: reconcile voice jobs against their record.
            if job.job_type == "voice.transcribe" and job.entity_id is not None:
                record = s.get(VoiceRecord, job.entity_id)
                if record is not None and record.status in ("confirmed", "failed", "discarded"):
                    target = (
                        "completed"
                        if record.status == "confirmed"
                        else ("failed" if record.status == "failed" else "cancelled")
                    )
                    jobs_service.transition(s, job, status=target, current_step="已同步识别结果")
                    cleaned += 1
                    continue
            # Case 2: expire anything non-terminal that has gone quiet.
            if job.updated_at is not None and now - job.updated_at > _STALE_AFTER:
                jobs_service.transition(s, job, status="cancelled", current_step="已过期自动清理")
                cleaned += 1
    if cleaned:
        log.info("stale_jobs_cleaned", count=cleaned)
    return cleaned


@celery.task(name="app.workers.tasks.maintenance.repair_stalled_agent_turns")
def repair_stalled_agent_turns() -> int:
    from app.modules.agent.scheduler import repair_stalled_plans
    from app.modules.agent.watchdog import repair_stalled_turns

    with session_scope() as session:
        repaired_turns = repair_stalled_turns(session)
        repaired_steps = repair_stalled_plans(session)
        return repaired_turns + repaired_steps
