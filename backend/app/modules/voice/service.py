"""Voice service: register record, run pipeline, auto-confirm to a task.

Audio is saved first (via the upload session). The pipeline transcribes and
parses asynchronously through the gateways, then auto-confirms directly to a
Task with status='todo' without waiting for user review.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.foundation import AsyncJob, User
from app.models.relations import EntityRelation
from app.models.tasks import Task
from app.models.voice import UploadSession, VoiceRecord
from app.modules.ai_config.service import bind as resolve_ai_config
from app.modules.jobs import service as jobs_service
from app.services.llm.base import LLMError, StructuredRequest
from app.services.llm.gateway import LLMGatewayImpl, get_llm_gateway
from app.services.llm.schemas import VoiceTasksV1, VoiceTaskV1
from app.services.speech.base import SpeechError, TranscriptionRequest
from app.services.speech.gateway import SpeechGatewayImpl, get_speech_gateway
from app.services.storage.providers.local import get_storage

VOICE_SCHEMA_VERSION = "voice-tasks.v1"

_PARSE_SYSTEM = (
    "你是把中文自然语言转成结构化任务候选的助手。"
    "输入文本来自语音识别（ASR），可能存在识别错误，"
    "请先按中文语境纠正后再解析：\n"
    "1. 同音字/近音字：结合任务管理语境纠正（如“会以”→“会议”、“提醒我”而非“提行我”、"
    "“联系房东”而非“联系房洞”、“预定”/“预订”按语义择一）。\n"
    "2. 数字、日期、时间：把口语与误听规范化，并结合下方给出的“当前日期”把相对时间换算成"
    "具体日期（如“明天”“下礼拜三”→ local_date 的 YYYY-MM-DD，“两点半”→ local_time 14:30，"
    "“半个小时”→ duration_minutes 30）。时间/日期只放进 local_date/local_time/duration_minutes，"
    "title 里不得再出现任何时间或日期词。\n"
    "5. title 只保留事件本身（动作+对象），去掉时间、日期、"
    "“提醒我/记得”等提示词，"
    "例如“10点去健身房”→ title=“去健身房”且 local_time=10:00，“明天下午三点和房东开会”→"
    "title=“和房东开会”。\n"
    "3. 缺失的词边界与标点按语义补齐，但不得改变原意、不得新增未提及的信息。\n"
    "4. 一段留言可能包含多件事（如“明天买菜、周五交报告、月底提醒我缴房租”），"
    "请拆解为多个相互独立、各自可执行的任务，每个任务单独带自己的日期/时间/时长；"
    "若只有一件事就只输出一个任务；无法判断为独立事项时不要强行拆分。\n"
    "纠正只用于 title、description 等结构化字段；每个任务的 original_text "
    "保留其对应的原始识别片段。\n"
    "缺失信息保持为 null，不得编造。只输出符合 voice-tasks.v1 的 JSON"
    '（顶层是 {"tasks": [...]}）。'
)


def _now_context(tz_name: str) -> str:
    """Give the model 'today' so relative dates like 明天/下周三 resolve correctly."""
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:  # unknown tz -> fall back to UTC
        now = datetime.now(UTC)
        tz_name = "UTC"
    weekday = "一二三四五六日"[now.weekday()]
    return f"（当前日期：{now:%Y-%m-%d} 星期{weekday}，时区：{tz_name}）"


def _calendar_bounds(
    local_date: str | None,
    local_time: str | None,
    duration_minutes: int | None,
    tz_name: str,
) -> tuple[datetime | None, datetime | None]:
    """Map a parsed local date/time/duration to timezone-aware UTC start/due.

    Undated items -> (None, None) (a plain todo). A date without a time anchors to the
    start of that day. A timed item defaults to a 30-minute duration when none is given.
    """
    if not local_date:
        return None, None
    try:
        d = date.fromisoformat(local_date)
    except ValueError:
        return None, None
    try:
        tz: tzinfo = ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    t = time(0, 0)
    timed = False
    if local_time:
        try:
            t = time.fromisoformat(local_time)
            timed = True
        except ValueError:
            timed = False
    start_local = datetime.combine(d, t, tzinfo=tz)
    start_utc = start_local.astimezone(UTC)
    if not timed:
        return start_utc, None
    minutes = duration_minutes if duration_minutes and duration_minutes > 0 else 30
    return start_utc, start_utc + timedelta(minutes=minutes)


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
    user = session.get(User, record.user_id)
    tz_name = user.timezone if user else "UTC"
    try:
        parsed = llm.structured(
            StructuredRequest(
                scenario="parse_voice_task",
                system=resolve_ai_config(
                    session,
                    record.user_id,
                    "voice_task_parse",
                    run_reference=f"voice-record:{record.id}",
                ).system_instruction,
                user=f"{_now_context(tz_name)}\n{record.transcript or ''}",
                schema=VoiceTasksV1,
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

    record.parsed_payload_json = parsed.model_dump(mode="json")
    record.schema_version = VOICE_SCHEMA_VERSION
    record.error_code = None
    record.error_message = None

    # Auto-confirm: create every decomposed task directly, without user review.
    # Each item carries its own date/time so it lands on the calendar independently.
    first_task: Task | None = None
    for item in parsed.tasks:
        entity_type = item.content_type
        start_at, due_at = _calendar_bounds(
            item.local_date, item.local_time, item.duration_minutes, tz_name
        )
        task = Task(
            id=uuid.uuid4(),
            user_id=record.user_id,
            type="task" if entity_type == "reminder" else entity_type,
            title=item.title,
            description=item.description,
            status="todo",
            priority=item.priority,
            importance=4 if item.important else 0,
            is_fixed=entity_type == "fixed_event",
            is_ai_adjustable=entity_type != "fixed_event",
            start_at=start_at,
            due_at=due_at,
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
        if first_task is None:
            first_task = task

    record.status = "confirmed"
    # confirmed_entity_* points at the first task for display; EntityRelations hold
    # the full set when a message decomposed into several tasks.
    if first_task is not None:
        record.confirmed_entity_type = parsed.tasks[0].content_type
        record.confirmed_entity_id = first_task.id
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
