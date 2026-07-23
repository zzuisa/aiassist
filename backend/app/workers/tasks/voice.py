"""Voice pipeline worker: transcribe -> parse -> waiting_user.

Delegates to the voice service so the same logic is exercised by integration
tests without a live broker. Safe retries resume from the transcript checkpoint.
"""

from __future__ import annotations

import uuid

from app.db.session import session_scope
from app.modules.voice import service
from app.workers.celery_app import celery


@celery.task(name="app.workers.tasks.voice.process_voice", bind=True, max_retries=3)
def process_voice(self, voice_id: str) -> str:  # type: ignore[no-untyped-def]
    with session_scope() as s:
        record = service.run_pipeline(s, uuid.UUID(voice_id))
        return record.status
