"""Voice pipeline: upload-first, provider failure, retry, waiting_user, confirm."""

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


def _candidate_json() -> str:
    return json.dumps(
        {
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
    )


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


def test_pipeline_reaches_waiting_user_with_candidate(make_user):
    user = make_user()
    # The transcript embeds the JSON the fake LLM should echo.
    transcript = f"明天下午三点提醒我联系房东 <<JSON>>{_candidate_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "waiting_user"
        assert record.parsed_payload_json["title"] == "联系房东"


def test_transcription_failure_preserves_audio_and_allows_retry(make_user):
    user = make_user()
    transcript = f"文本 <<JSON>>{_candidate_json()}"
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
        assert record.status == "waiting_user"


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


def test_confirm_creates_one_entity_and_source_relation(make_user):
    user = make_user()
    transcript = f"文本 <<JSON>>{_candidate_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
        uid = user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        voice_service.run_pipeline(s, vid, speech=speech, llm=llm)

    candidate = VoiceTaskV1.model_validate(json.loads(_candidate_json()))
    with session_scope() as s:
        entity_type, _entity_id = voice_service.confirm(s, uid, vid, candidate)
        assert entity_type == "reminder"

    with session_scope() as s:
        from app.models.relations import EntityRelation
        from app.models.tasks import Task
        from sqlalchemy import func, select

        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 1
        rel = s.scalars(select(EntityRelation).where(EntityRelation.user_id == uid)).one()
        assert rel.source_type == "voice_record"
        assert rel.relation_type == "converted_to"


def test_from_transcript_parses_without_audio(make_user):
    """Real-time recognition path: text -> parse -> waiting_user, no audio asset."""
    user = make_user()
    transcript = f"明天下午三点提醒我联系房东 <<JSON>>{_candidate_json()}"
    speech = SpeechGatewayImpl(_ScriptedSpeech("unused"))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        record = voice_service.create_from_transcript(s, user.id, transcript)
        assert record.asset_key == "text-input"
        assert record.transcript == transcript
        vid = record.id

    with session_scope() as s:
        record = voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
        assert record.status == "waiting_user"
        assert record.parsed_payload_json["title"] == "联系房东"


def test_double_confirm_rejected(make_user):
    from app.core.errors import ConflictError

    user = make_user()
    transcript = f"文本 <<JSON>>{_candidate_json()}"
    with session_scope() as s:
        record = _make_voice(s, user.id, audio=transcript.encode())
        vid = record.id
        uid = user.id
    speech = SpeechGatewayImpl(_ScriptedSpeech(transcript))
    llm = LLMGatewayImpl(FakeProvider())
    with session_scope() as s:
        voice_service.run_pipeline(s, vid, speech=speech, llm=llm)
    candidate = VoiceTaskV1.model_validate(json.loads(_candidate_json()))
    with session_scope() as s:
        voice_service.confirm(s, uid, vid, candidate)
    with session_scope() as s, pytest.raises(ConflictError):
        voice_service.confirm(s, uid, vid, candidate)


_ = uuid
