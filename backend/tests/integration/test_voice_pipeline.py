"""Voice pipeline: upload-first, provider failure, retry, auto-confirm to task."""

from __future__ import annotations

import json
import uuid

import pytest
from app.db.session import session_scope
from app.modules.uploads import service as upload_service
from app.modules.voice import service as voice_service
from app.services.llm.gateway import FakeProvider, LLMGatewayImpl
from app.services.llm.schemas import VoiceTaskV1
from app.services.speech.base import SpeechError, TranscriptionRequest, TranscriptResult
from app.services.speech.gateway import SpeechGatewayImpl, TranscribeProvider
from app.services.storage.providers.local import reset_storage

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    from app.core.config import reload_settings

    reload_settings()
    reset_storage()
    yield
    reset_storage()


def _candidate_dict(**over) -> dict:
    base = {
        "title": "联系房东",
        "content_type": "reminder",
        "description": None,
        "local_date": "2026-07-24",
        "local_time": "15:00:00",
        "timezone": "Europe/Berlin",
        "duration_minutes": 20,
        "priority": 3,
        "important": True,
        "reminder": {"channel": "in_app", "offset_minutes": 30},
        "recurring": False,
        "recurrence_rule": None,
        "original_text": "明天下午三点提醒我联系房东",
    }
    base.update(over)
    return base


def _candidate_json() -> str:
    """A single VoiceTaskV1 candidate (used for the explicit confirm() path)."""
    return json.dumps(_candidate_dict())


def _tasks_json(*items: dict) -> str:
    """A voice-tasks.v1 payload the FakeProvider echoes back to run_pipeline."""
    return json.dumps({"tasks": list(items) or [_candidate_dict()]})


class _ScriptedSpeech(TranscribeProvider):
    def __init__(self, text: str, fail_times: int = 0) -> None:
        self.text = text
        self.fail_times = fail_times
        self.calls = 0

    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise SpeechError("timeout", "provider timeout")
        return TranscriptResult(text=self.text, language="zh")


def _make_voice(session, user_id, audio: bytes = b"placeholder audio"):
    upload = upload_service.create_session(
        session,
        user_id,
        purpose="voice",
        filename="a.webm",
        media_type="audio/webm",
        byte_size=len(audio),
    )
    upload_service.store_bytes(session, upload, __import__("io").BytesIO(audio))
    upload_service.complete(session, user_id, upload.id)
    record = voice_service.create_voice_record(session, user_id, upload.id)
    return record


def test_upload_first_returns_record_before_processing(make_user):
    user = make_user()
    with session_scope() as s:
        record = _make_voice(s, user.id)
        assert record.status == "uploaded"
        assert record.async_job_id is not None


def test_pipeline_auto_confirms_and_creates_task(make_user):
    user = make_user()
    transcript = f"明天下午三点提醒我联系房东 <<JSON>>{_tasks_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
        uid = user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "confirmed"
        assert record.parsed_payload_json["tasks"][0]["title"] == "联系房东"
        assert record.confirmed_entity_id is not None
    with session_scope() as s:
        from datetime import UTC, datetime

        from app.models.tasks import Task
        from sqlalchemy import func, select

        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 1
        # Dated candidate (2026-07-24 15:00 Europe/Berlin, 20 min) must land on the
        # calendar: start_at/due_at populated in UTC (CEST = UTC+2 in July).
        task = s.scalar(select(Task).where(Task.user_id == uid))
        assert task.start_at == datetime(2026, 7, 24, 13, 0, tzinfo=UTC)
        assert task.due_at == datetime(2026, 7, 24, 13, 20, tzinfo=UTC)


def test_pipeline_decomposes_message_into_multiple_tasks(make_user):
    """One message -> several tasks, each with its own date/time (or undated)."""
    user = make_user()
    items = [
        _candidate_dict(
            title="买菜", content_type="task", local_date="2026-07-27",
            local_time="09:00:00", duration_minutes=None, original_text="明天买菜",
        ),
        _candidate_dict(
            title="交报告", content_type="task", local_date="2026-07-31",
            local_time="18:00:00", duration_minutes=60, original_text="周五交报告",
        ),
        _candidate_dict(
            title="缴房租", content_type="reminder", local_date=None,
            local_time=None, duration_minutes=None, original_text="提醒我缴房租",
        ),
    ]
    transcript = f"明天买菜、周五交报告、提醒我缴房租 <<JSON>>{_tasks_json(*items)}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid, uid = record.id, user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "confirmed"
        assert len(record.parsed_payload_json["tasks"]) == 3
    with session_scope() as s:
        from datetime import UTC, datetime

        from app.models.tasks import Task
        from sqlalchemy import func, select

        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 3
        by_title = {t.title: t for t in s.scalars(select(Task).where(Task.user_id == uid)).all()}
        # 09:00 Europe/Berlin (CEST) -> 07:00 UTC, default 30 min.
        assert by_title["买菜"].start_at == datetime(2026, 7, 27, 7, 0, tzinfo=UTC)
        assert by_title["买菜"].due_at == datetime(2026, 7, 27, 7, 30, tzinfo=UTC)
        # 18:00 Europe/Berlin -> 16:00 UTC, explicit 60 min.
        assert by_title["交报告"].due_at == datetime(2026, 7, 31, 17, 0, tzinfo=UTC)
        # Undated reminder stays a plain todo.
        assert by_title["缴房租"].start_at is None


def test_transcription_failure_preserves_audio_and_allows_retry(make_user):
    user = make_user()
    transcript = f"文本 <<JSON>>{_tasks_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id

    failing = _ScriptedSpeech(transcript, fail_times=1)
    speech = SpeechGatewayImpl(failing)
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "failed"
        assert record.error_code == "timeout"

    # Audio still exists; retry resumes and succeeds.
    with session_scope() as s:
        voice_service.retry(s, user.id, vid)
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "confirmed"


def test_invalid_llm_output_fails_without_creating_task(make_user):
    user = make_user()
    transcript = "文本 <<JSON>>{not valid json"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
        uid = user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "failed"
        assert record.error_code == "invalid_structured_output"
    with session_scope() as s:
        from app.models.tasks import Task
        from sqlalchemy import func, select

        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 0


def test_pipeline_creates_entity_and_source_relation(make_user):
    user = make_user()
    transcript = f"文本 <<JSON>>{_tasks_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
        uid = user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "confirmed"
        assert record.confirmed_entity_type == "reminder"

    with session_scope() as s:
        from app.models.relations import EntityRelation
        from app.models.tasks import Task
        from sqlalchemy import func, select

        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 1
        rel = s.scalars(select(EntityRelation).where(EntityRelation.user_id == uid)).one()
        assert rel.source_type == "voice_record"
        assert rel.relation_type == "converted_to"


def test_from_transcript_auto_confirms_without_audio(make_user):
    """Real-time recognition path: text -> parse -> auto-confirm, no audio asset."""
    user = make_user()
    transcript = f"明天下午三点提醒我联系房东 <<JSON>>{_tasks_json()}"
    speech = SpeechGatewayImpl(_ScriptedSpeech("unused"))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.create_from_transcript(s, user.id, transcript)
        assert record.asset_key == "text-input"
        assert record.transcript == transcript
        vid = record.id

    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "confirmed"
        assert record.parsed_payload_json["tasks"][0]["title"] == "联系房东"
        assert record.confirmed_entity_id is not None


def test_explicit_confirm_after_auto_confirm_rejected(make_user):
    """Pipeline auto-confirms; calling confirm() again raises ConflictError."""
    from app.core.errors import ConflictError

    user = make_user()
    transcript = f"文本 <<JSON>>{_tasks_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
        uid = user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
    candidate = VoiceTaskV1.model_validate(json.loads(_candidate_json()))
    with session_scope() as s, pytest.raises(ConflictError):
        voice_service.confirm(s, uid, vid, candidate)


_ = uuid
