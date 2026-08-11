"""Celery Beat periodic schedule.

Beat only emits scheduling commands; all business generation uses database unique
keys/locks so repeated or overlapping runs never produce duplicates.
"""

from __future__ import annotations

from celery.schedules import crontab

from app.workers.celery_app import celery

celery.conf.beat_schedule = {
    # Due-reminder scan every minute.
    "scan-due-reminders": {
        "task": "app.workers.tasks.notifications.scan_due_reminders",
        "schedule": 60.0,
    },
    # Habit + recurring-task generation, hourly (covers all user timezones; the
    # per-user generator uses the user's local date and is idempotent).
    "generate-habits-and-recurrences": {
        "task": "app.workers.tasks.habits.scan_and_generate",
        "schedule": crontab(minute=5),
    },
    # Outbox reconciliation safety net (publisher runs continuously; this catches
    # stuck rows if the publisher was down).
    "outbox-reconcile": {
        "task": "app.workers.tasks.maintenance.reconcile_outbox",
        "schedule": 300.0,
    },
    # Retire orphaned/stale background jobs so the task center stays clean.
    "cleanup-stale-jobs": {
        "task": "app.workers.tasks.maintenance.cleanup_stale_jobs",
        "schedule": crontab(minute=15),
    },
    "repair-stalled-agent-turns": {
        "task": "app.workers.tasks.maintenance.repair_stalled_agent_turns",
        "schedule": 30.0,
    },
}
