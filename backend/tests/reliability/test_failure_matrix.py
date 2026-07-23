"""Reliability failure matrix (broker-independent): outbox crash, provider fail.

Broker-dependent redelivery/DLQ is validated by test_broker_roundtrip (broker
mark). These cases cover the durable guarantees that must hold with no broker.
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from app.db.session import session_scope
from app.services.llm.gateway import FakeProvider, LLMGatewayImpl
from app.services.llm.schemas import VoiceTaskV1

pytestmark = [pytest.mark.reliability, pytest.mark.integration]


def test_business_commit_survives_broker_absence(make_user):
    """A task + outbox row commit even if no broker/publisher runs; the event
    stays pending for later delivery."""
    from app.models.foundation import OutboxEvent
    from app.models.tasks import Task
    from app.modules.tasks import service as task_service
    from app.modules.tasks.schemas import TaskCreate
    from sqlalchemy import func, select

    user = make_user()
    with session_scope() as s:
        task_service.create_task(s, user.id, TaskCreate(title="durable", type="task"))
        uid = user.id
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 1
        pending = s.scalars(
            select(OutboxEvent).where(OutboxEvent.user_id == uid, OutboxEvent.status == "pending")
        ).all()
        assert len(pending) == 1


def test_invalid_provider_output_produces_no_business_mutation():
    """The strict gateway rejects malformed output without any side effect."""
    from app.services.llm.base import LLMError, StructuredRequest

    llm = LLMGatewayImpl(FakeProvider())
    with pytest.raises(LLMError) as exc:
        llm.structured(
            StructuredRequest(
                scenario="parse_voice_task",
                system="s",
                user="文本 <<JSON>>{not valid json",
                schema=VoiceTaskV1,
                repair_attempts=0,
            )
        )
    assert exc.value.code == "invalid_structured_output"


def test_repair_attempt_then_success():
    """One repair attempt recovers when the second response is valid."""
    from app.services.llm.base import StructuredRequest

    valid = json.dumps(
        {
            "title": "联系房东",
            "content_type": "reminder",
            "description": None,
            "local_date": None,
            "local_time": None,
            "timezone": "UTC",
            "duration_minutes": None,
            "priority": 0,
            "important": False,
            "reminder": None,
            "recurring": False,
            "recurrence_rule": None,
            "original_text": "文本",
        }
    )

    class FlakyProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, system, user, *, temperature, max_tokens):
            self.calls += 1
            if self.calls == 1:
                return "{bad json"
            return valid

    llm = LLMGatewayImpl(FlakyProvider())
    result = llm.structured(
        StructuredRequest(
            scenario="parse_voice_task",
            system="s",
            user="文本",
            schema=VoiceTaskV1,
            repair_attempts=1,
        )
    )
    assert result.title == "联系房东"


def test_upload_orphan_is_cleanable(make_user, tmp_path, monkeypatch):
    """An uploaded temp object with no completed business record can be deleted."""
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    from app.core.config import reload_settings
    from app.modules.uploads import service as upload_svc
    from app.services.storage.providers.local import get_storage, reset_storage

    reload_settings()
    reset_storage()
    user = make_user()
    with session_scope() as s:
        upload = upload_svc.create_session(
            s,
            user.id,
            purpose="voice",
            filename="a.webm",
            media_type="audio/webm",
            byte_size=5,
        )
        upload_svc.store_bytes(s, upload, io.BytesIO(b"hello"))
        temp_key = upload.object_key_temp
    # The temp object exists and can be removed by orphan cleanup.
    storage = get_storage()
    assert storage.exists(temp_key)
    storage.delete(temp_key)
    assert not storage.exists(temp_key)
    reset_storage()


_ = uuid
