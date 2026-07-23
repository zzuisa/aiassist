"""Server-Sent Events for job/notification updates.

The durable source is PostgreSQL ``async_job_events``. Redis is only a wakeup
hint; when it is unavailable the stream degrades to bounded DB polling with no
loss of correctness. Reconnect uses ``Last-Event-ID`` to replay; a missing or
expired cursor gets a ``jobs.snapshot`` first.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.db.session import session_scope
from app.modules.jobs import service as jobs_service

HEARTBEAT_SECONDS = 20
POLL_INTERVAL_SECONDS = 1.0
# Events older than the retained window force a snapshot resync.
SNAPSHOT_ON_MISSING_CURSOR = True


def _sse(event: str, data: dict, event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False, default=str)}")
    return "\n".join(lines) + "\n\n"


def _snapshot_payload(user_id: uuid.UUID) -> tuple[dict, int]:
    with session_scope() as s:
        jobs = jobs_service.list_jobs(
            s, user_id, statuses=["pending", "queued", "processing", "waiting_user"], limit=100
        )
        cursor = jobs_service.latest_event_id(s, user_id)
        payload = {
            "snapshot_at": datetime.now(UTC).isoformat(),
            "jobs": [
                {
                    "job_id": str(j.id),
                    "job_version": j.version,
                    "job_type": j.job_type,
                    "status": j.status,
                    "progress": j.progress,
                    "current_step": j.current_step,
                    "retry_count": j.retry_count,
                    "updated_at": (j.updated_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
                }
                for j in jobs
            ],
            "notifications": _unread_notifications(s, user_id),
        }
        return payload, cursor


def _unread_notifications(session, user_id: uuid.UUID) -> list[dict]:  # type: ignore[no-untyped-def]
    from app.modules.notifications import service as notif_service

    items = notif_service.list_notifications(session, user_id, limit=20)
    return [
        {
            "notification_id": str(n.id),
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "status": n.status,
            "created_at": n.created_at.isoformat(),
        }
        for n in items
        if n.status == "unread"
    ]


def _cursor_valid(user_id: uuid.UUID, cursor: int) -> bool:
    if cursor <= 0:
        return False
    with session_scope() as s:
        # Cursor is valid if there is at least one retained event <= cursor for
        # this user (i.e. it has not been pruned past).
        oldest = jobs_service.events_after(s, user_id, cursor - 1, limit=1)
        # If the very next event id after (cursor-1) exists and is <= cursor,
        # or the cursor equals the latest, treat as valid.
        latest = jobs_service.latest_event_id(s, user_id)
        if cursor > latest:
            return False
        return bool(oldest) or cursor == latest


async def event_stream(user_id: uuid.UUID, last_event_id: str | None) -> AsyncIterator[str]:
    # Establish the starting cursor.
    cursor = 0
    send_snapshot = True
    if last_event_id and last_event_id.isdigit():
        candidate = int(last_event_id)
        if _cursor_valid(user_id, candidate):
            cursor = candidate
            send_snapshot = False

    if send_snapshot:
        payload, cursor = _snapshot_payload(user_id)
        yield _sse("jobs.snapshot", payload, cursor)
        yield "retry: 3000\n\n"

    last_beat = asyncio.get_event_loop().time()
    while True:
        with session_scope() as s:
            events = jobs_service.events_after(s, user_id, cursor, limit=200)
        if events:
            for ev in events:
                yield _sse(ev.event_type, ev.payload_json, ev.id)
                cursor = ev.id
            last_beat = asyncio.get_event_loop().time()
        else:
            now = asyncio.get_event_loop().time()
            if now - last_beat >= HEARTBEAT_SECONDS:
                yield f": heartbeat {datetime.now(UTC).isoformat()}\n\n"
                last_beat = now
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
