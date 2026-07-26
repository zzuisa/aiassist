"""Voice service: register record, run pipeline, auto-confirm to a task.

Audio is saved first (via the upload session). The pipeline transcribes and
parses asynchronously through the gateways, then auto-confirms directly to a
Task with status='todo' without waiting for user review.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.foundation import AsyncJob
from app.models.relations import EntityRelation
from app.models.tasks import Task
from app.models.voice import UploadSession, VoiceRecord
from app.modules.jobs import service as jobs_service
from app.services.llm.base import LLMError, StructuredRequest
from app.services.llm.gateway import LLMGatewayImpl, get_llm_gateway
from app.services.llm.schemas import VoiceTaskV1
from app.services.speech.base import SpeechError, TranscriptionRequest
from app.services.speech.gateway import SpeechGatewayImpl, get_speech_gateway
from app.services.storage.providers.local import get_storage

VOICE_SCHEMA_VERSION = "voice-task.v1"

_PARSE_SYSTEM = (
    "你是把中文自然语言转成结构化任务候选的助手。"
    "输入文本来自浏览器实时语音识别（ASR），可能存在识别错误，"
    "请先按中文语境纠正后再解析：\n"
    "1. 同音字/近音字：结合任务管理语境纠正（如“会以”→“会议”、“提醒我”而非“提行我”、"
    "“联系房东”而非“联系房洞”、“预定”/“预订”按语义择一）。\n"
    "2. 数字、日期、时间：把口语与误听规范化（如“两点半”→14:30、“明天”按 local_date、"
    "“下礼拜三”→具体日期、“半个小时”→30 分钟）。\n"
    "3. 缺失的词边界与标点按语义补齐，但不得改变原意、不得新增未提及的信息。\n"
    "纠正只用于 title、description 等结构化字段；original_text 必须保留未经改动的原始识别文本。\n"
    "缺失信息保持为 null，不得编造。只输出符合 voice-task.v1 的 JSON。"
)


def create_voice_record(session: Session, user_id: uuid.UUID, upload_id: uuid.UUID) -> VoiceRecord:
    upload = session.get(UploadSession, upload_id)
    if upload is None or upload.user_id != user_id:
        raise NotFoundError("Upload not found")
    if upload.status != "completed":
        raise ValidationError("Upload is not completed", code="upload_incomplete")
    record = VoiceRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        asset_key=upload.object_key_temp,  # final key after complete()
        media_type=upload.expected_media_type,
        status="uploaded",
    )
    session.add(record)
    session.flush()
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="voice.transcribe",
        entity_type="voice_record",
        entity_id=record.id,
        idempotency_key=f"voice:{record.id}",
    )
    record.async_job_id = job.id
    return record


def create_from_transcript(session: Session, user_id: uuid.UUID, transcript: str) -> VoiceRecord:
    """Create a voice record from client-side real-time recognition.

    The browser performs live ASR (Web Speech API); we skip the audio-upload and
    transcription checkpoints and go straight to structured parsing via the LLM
    gateway. There is no audio asset, so `asset_key` is a text sentinel.
    """
    if not transcript.strip():
        raise ValidationError("Empty transcript", code="empty_transcript")
    record = VoiceRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        asset_key="text-input",  # no audio object; parse-only path
        media_type=None,
        status="parsing",
        transcript=transcript.strip(),
    )
    session.add(record)
    session.flush()
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="voice.transcribe",
        entity_type="voice_record",
        entity_id=record.id,
        idempotency_key=f"voice:{record.id}",
    )
    record.async_job_id = job.id
    return record


def get_record(session: Session, user_id: uuid.UUID, voice_id: uuid.UUID) -> VoiceRecord:
    record = session.get(VoiceRecord, voice_id)
    if record is None or record.user_id != user_id:
        raise NotFoundError("Voice record not found")
    return record


def run_pipeline(
    session: Session,
    voice_id: uuid.UUID,
    *,
    speech: SpeechGatewayImpl | None = None,
    llm: LLMGatewayImpl | None = None,
) -> VoiceRecord:
    """Transcribe -> strict parse -> waiting_user, with checkpoints.

    Retries resume from the last successful checkpoint (transcript preserved).
    On provider failure the record is marked failed but audio/transcript survive.
    """
    record = session.get(VoiceRecord, voice_id)
    if record is None:
        raise NotFoundError("Voice record not found")
    speech = speech or get_speech_gateway()
    llm = llm or get_llm_gateway()
    job = session.get(AsyncJob, record.async_job_id) if record.async_job_id else None

    # Checkpoint 1: transcription (skip if already have transcript).
    if not record.transcript:
        record.status = "transcribing"
        if job:
            jobs_service.transition(
                session, job, status="processing", progress=30, current_step="正在转写"
            )
        try:
            audio = b"".join(get_storage().open_stream(record.asset_key))
            result = speech.transcribe(
                TranscriptionRequest(
                    object_key=record.asset_key, media_type=record.media_type or "audio/webm"
                ),
                audio,
            )
        except SpeechError as exc:
            record.status = "failed"
            record.error_code = exc.code
            record.error_message = "转写失败，可稍后重试"
            if job:
                jobs_service.transition(
                    session,
                    job,
                    status="failed",
                    error_code=exc.code,
                    error_message="转写失败，可稍后重试",
                    error_retryable=exc.retryable,
                )
            return record
        record.transcript = result.text
        record.transcript_language = result.language

    # Checkpoint 2: strict structured parse.
    record.status = "parsing"
    if job:
        jobs_service.transition(
            session, job, status="processing", progress=70, current_step="正在解析"
        )
    try:
        candidate = llm.structured(
            StructuredRequest(
                scenario="parse_voice_task",
                system=_PARSE_SYSTEM,
                user=record.transcript or "",
                schema=VoiceTaskV1,
            )
        )
    except LLMError as exc:
        record.status = "failed"
        record.error_code = exc.code
        record.error_message = "解析失败，可编辑或重试"
        if job:
            jobs_service.transition(
                session,
                job,
                status="failed",
                error_code=exc.code,
                error_message="解析失败，可编辑或重试",
                error_retryable=exc.retryable,
            )
        return record

    record.parsed_payload_json = candidate.model_dump(mode="json")
    record.schema_version = VOICE_SCHEMA_VERSION
    record.error_code = None
    record.error_message = None

    # Auto-confirm: create the task directly without user review.
    entity_type = candidate.content_type
    task = Task(
        id=uuid.uuid4(),
        user_id=record.user_id,
        type="task" if entity_type == "reminder" else entity_type,
        title=candidate.title,
        description=candidate.description,
        status="todo",
        priority=candidate.priority,
        importance=4 if candidate.important else 0,
        is_fixed=entity_type == "fixed_event",
        is_ai_adjustable=entity_type != "fixed_event",
        source_type="voice",
        source_id=record.id,
    )
    session.add(task)
    session.flush()
    session.add(
        EntityRelation(
            id=uuid.uuid4(),
            user_id=record.user_id,
            source_type="voice_record",
            source_id=record.id,
            target_type="task",
            target_id=task.id,
            relation_type="converted_to",
        )
    )
    record.status = "confirmed"
    record.confirmed_entity_type = entity_type
    record.confirmed_entity_id = task.id
    record.confirmed_at = datetime.now(UTC)
    if job:
        jobs_service.transition(
            session,
            job,
            status="completed",
            progress=100,
            current_step="任务已创建",
        )
    return record


def confirm(
    session: Session, user_id: uuid.UUID, voice_id: uuid.UUID, candidate: VoiceTaskV1
) -> tuple[str, uuid.UUID]:
    """Create exactly one formal entity from the edited candidate."""
    record = get_record(session, user_id, voice_id)
    if record.status != "waiting_user":
        raise ConflictError("Only a waiting record can be confirmed", code="not_waiting")
    if record.confirmed_entity_id is not None:
        raise ConflictError("Already confirmed", code="already_confirmed")

    entity_type = candidate.content_type
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        type="task" if entity_type == "reminder" else entity_type,
        title=candidate.title,
        description=candidate.description,
        status="todo",
        priority=candidate.priority,
        importance=4 if candidate.important else 0,
        is_fixed=entity_type == "fixed_event",
        is_ai_adjustable=entity_type != "fixed_event",
        source_type="voice",
        source_id=record.id,
    )
    session.add(task)
    session.flush()

    session.add(
        EntityRelation(
            id=uuid.uuid4(),
            user_id=user_id,
            source_type="voice_record",
            source_id=record.id,
            target_type="task",
            target_id=task.id,
            relation_type="converted_to",
        )
    )
    record.status = "confirmed"
    record.confirmed_entity_type = entity_type
    record.confirmed_entity_id = task.id
    record.confirmed_at = datetime.now(UTC)
    return entity_type, task.id


def retry(session: Session, user_id: uuid.UUID, voice_id: uuid.UUID) -> VoiceRecord:
    record = get_record(session, user_id, voice_id)
    if record.status not in ("failed",):
        raise ConflictError("Only a failed record can be retried", code="not_failed")
    record.status = "uploaded"
    record.error_code = None
    record.error_message = None
    return record


def list_pending(session: Session, user_id: uuid.UUID) -> list[VoiceRecord]:
    return list(
        session.scalars(
            select(VoiceRecord).where(
                VoiceRecord.user_id == user_id,
                VoiceRecord.status.in_(["uploaded", "transcribing", "parsing", "waiting_user"]),
            )
        ).all()
    )
