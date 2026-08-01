"""Quick-add planning: analyze a line into scheduled task candidates.

The user types one line ("明天上午喝咖啡，中午吃自助"); an LLM splits it into tasks,
assigns concrete times (vague parts default sensibly, or use the user's answers),
judges importance, considers the existing schedule to avoid clashes, and may ask a
few bounded questions. Nothing is created during analysis — the caller reviews the
plan, optionally answers, or saves as-is. `commit` then creates the tasks.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import User
from app.models.tasks import Task
from app.modules.voice.service import _calendar_bounds, _now_context
from app.services.llm.base import StructuredRequest
from app.services.llm.gateway import LLMGatewayImpl, get_llm_gateway
from app.services.llm.schemas import QuickPlanV1, VoiceTaskV1

_PLAN_SYSTEM = (
    "你是把用户一句话待办拆解并合理安排到日程的助手。请：\n"
    "1. 把输入拆成一个或多个相互独立、可执行的任务，title 只保留事件本身（去掉时间/日期词）。\n"
    "2. 结合“当前日期”把相对时间换算成具体 local_date(YYYY-MM-DD) 和 local_time(HH:MM)。"
    "模糊时段按常识给默认时刻：上午→09:00、中午→12:00、下午→15:00、傍晚→18:00、晚上→19:30，"
    "但若用户在“补充回答”里给了作息（如起床时间）或具体时间，则优先据此推算。\n"
    "3. 参考“已有日程”，尽量避免与已排事件时间冲突。\n"
    "4. 判断重要程度：把重要的事 important=true 并适当提高 priority(0-4)。\n"
    "5. 只有当缺少关键信息、且知道后能明显改善安排时，才提出问题；问题数量最多 2 个，"
    "要具体（例如“你一般几点起床？”）。信息足够时 questions 返回空列表，不要为追问而追问。\n"
    "6. summary 用一句中文说明你的安排（如“已安排 3 件事：喝咖啡 9:00、吃自助 12:00…”）。\n"
    "每个任务的 original_text 保留其对应的原始片段。缺失信息保持 null，不得编造。"
    "只输出符合 quick-plan.v1 的 JSON。"
)


def _upcoming_summary(session: Session, user_id: uuid.UUID, tz_name: str) -> str:
    now = datetime.now(UTC)
    horizon = now + timedelta(days=7)
    rows = session.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            Task.status.in_(["todo", "in_progress"]),
            Task.start_at.is_not(None),
            Task.start_at >= now,
            Task.start_at <= horizon,
        )
    ).all()
    if not rows:
        return "（无）"
    from zoneinfo import ZoneInfo

    try:
        tz: tzinfo = ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    parts = []
    for t in sorted(rows, key=lambda x: x.start_at or now)[:20]:
        start_at = t.start_at
        if start_at is None:
            continue
        local = start_at.astimezone(tz)
        parts.append(f"{local:%m-%d %H:%M} {t.title}")
    return "；".join(parts)


def analyze(
    session: Session,
    user_id: uuid.UUID,
    text: str,
    answers: list[tuple[str, str]] | None = None,
    llm: LLMGatewayImpl | None = None,
) -> QuickPlanV1:
    user = session.get(User, user_id)
    tz_name = user.timezone if user else "UTC"
    llm = llm or get_llm_gateway()
    schedule = _upcoming_summary(session, user_id, tz_name)
    answer_text = ""
    if answers:
        answer_text = "\n补充回答：" + "；".join(f"{q} → {a}" for q, a in answers)
    user_prompt = f"{_now_context(tz_name)}\n已有日程：{schedule}\n用户输入：{text}{answer_text}"
    return llm.structured(
        StructuredRequest(
            scenario="quick_plan",
            system=_PLAN_SYSTEM,
            user=user_prompt,
            schema=QuickPlanV1,
        )
    )


def commit(session: Session, user_id: uuid.UUID, tasks: list[VoiceTaskV1]) -> list[Task]:
    """Create the reviewed task candidates (calendar-synced), like voice auto-confirm."""
    user = session.get(User, user_id)
    tz_name = user.timezone if user else "UTC"
    created: list[Task] = []
    for item in tasks:
        entity_type = item.content_type
        start_at, due_at = _calendar_bounds(
            item.local_date, item.local_time, item.duration_minutes, tz_name
        )
        task = Task(
            id=uuid.uuid4(),
            user_id=user_id,
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
            source_type="quick_plan",
            source_id=None,
        )
        session.add(task)
        session.flush()
        # Important quick-plan tasks get the same 4h email reminder as the popover.
        from app.modules.notifications import reminder_service

        reminder_service.sync_important_reminder(session, task)
        created.append(task)
    return created


# --- Async orchestration: quick-add -> background job -> (optional) Q&A -> tasks ---
from app.core.errors import ConflictError, NotFoundError  # noqa: E402
from app.models.foundation import AsyncJob  # noqa: E402
from app.modules.jobs import service as jobs_service  # noqa: E402

_FACTS_KEY = "_profile"  # namespaced inside users.notification_preferences (no migration)
_MAX_ROUNDS = 2
_MAX_MEMORY_QA = 12


def get_user_facts(user: User) -> list[dict]:
    prefs = user.notification_preferences or {}
    return list((prefs.get(_FACTS_KEY) or {}).get("qa") or [])


def set_user_facts(user: User, items: list[dict]) -> None:
    """Replace the remembered Q&A (settings edit/delete). Each item is {q, a}."""
    clean = [
        {"q": str(i.get("q", "")).strip(), "a": str(i.get("a", "")).strip()}
        for i in items
        if str(i.get("q", "")).strip() and str(i.get("a", "")).strip()
    ][-_MAX_MEMORY_QA:]
    prefs = dict(user.notification_preferences or {})
    profile = dict(prefs.get(_FACTS_KEY) or {})
    profile["qa"] = clean
    prefs[_FACTS_KEY] = profile
    user.notification_preferences = prefs


def _remember(user: User, qa: list[tuple[str, str]]) -> None:
    """Persist answered Q&A so future quick-adds are smarter (加深记忆)."""
    prefs = dict(user.notification_preferences or {})
    profile = dict(prefs.get(_FACTS_KEY) or {})
    memory = list(profile.get("qa") or [])
    seen = {m["q"] for m in memory}
    for q, a in qa:
        if a and q not in seen:
            memory.append({"q": q, "a": a})
    profile["qa"] = memory[-_MAX_MEMORY_QA:]
    prefs[_FACTS_KEY] = profile
    user.notification_preferences = prefs


def create_plan_job(session: Session, user_id: uuid.UUID, text: str) -> AsyncJob:
    """Enqueue background analysis of a quick-add line. Creates nothing yet."""
    job = jobs_service.create_job(
        session, user_id=user_id, job_type="plan.analyze", entity_type="plan"
    )
    jobs_service.transition(
        session,
        job,
        status="queued",
        progress=10,
        current_step="正在后台分析安排",
        result={"text": text, "answers": [], "rounds": 0},
    )
    return job


def _job_answers(job: AsyncJob) -> list[tuple[str, str]]:
    return [(a["q"], a["a"]) for a in (job.result_json or {}).get("answers", [])]


def _commit_and_record(
    session: Session, user_id: uuid.UUID, task_dumps: list[dict], data: dict
) -> tuple[list[Task], dict]:
    candidates = [VoiceTaskV1.model_validate(t) for t in task_dumps]
    created = commit(session, user_id, candidates)
    data["created_ids"] = [str(t.id) for t in created]
    data["created"] = len(created)
    return created, data


def _delete_recorded(session: Session, user_id: uuid.UUID, data: dict) -> None:
    """Remove tasks previously auto-created for this plan (before re-analysis)."""
    from app.modules.tasks import service as task_service

    for tid in data.get("created_ids", []) or []:
        with suppress(Exception):
            task_service.delete_task(session, user_id, uuid.UUID(tid))
    data.pop("created_ids", None)
    data.pop("auto_committed", None)


def run_plan(session: Session, job_id: uuid.UUID, llm: LLMGatewayImpl | None = None) -> AsyncJob:
    """Worker step: analyze; ask (waiting_user) if needed, else create the tasks."""
    job = session.get(AsyncJob, job_id)
    if job is None or job.job_type != "plan.analyze":
        raise NotFoundError("Plan job not found")
    data = dict(job.result_json or {})
    text = data.get("text", "")
    rounds = int(data.get("rounds", 0))
    user = session.get(User, job.user_id)
    # Persistent memory + this job's answers both inform the analysis.
    answers = _job_answers(job) + [(m["q"], m["a"]) for m in get_user_facts(user)] if user else []
    jobs_service.transition(session, job, status="processing", progress=50, current_step="正在分析")
    try:
        plan = analyze(session, job.user_id, text, answers, llm=llm)
    except Exception as exc:
        jobs_service.transition(
            session,
            job,
            status="failed",
            error_code="analyze_failed",
            error_message="分析失败，可稍后重试或直接保存",
            error_retryable=True,
        )
        raise exc

    if plan.questions and rounds < _MAX_ROUNDS:
        # Park for answers, but keep a planned default so a 3-minute timeout can
        # auto-record it. Questions/tasks stay in the result so the client shows
        # the form and the user can still answer after it auto-commits.
        data.update(
            {
                "questions": list(plan.questions),
                "tasks": [t.model_dump(mode="json") for t in plan.tasks],
                "summary": plan.summary,
            }
        )
        jobs_service.transition(
            session,
            job,
            status="waiting_user",
            progress=70,
            current_step="需要你回答几个问题（3 分钟后按默认录入）",
            result=data,
        )
        return job

    created, data = _commit_and_record(
        session, job.user_id, [t.model_dump(mode="json") for t in plan.tasks], data
    )
    data["summary"] = plan.summary
    data.pop("questions", None)
    jobs_service.transition(
        session,
        job,
        status="completed",
        progress=100,
        current_step=f"已创建 {len(created)} 项",
        result=data,
    )
    return job


def expire_plan(session: Session, job_id: uuid.UUID) -> AsyncJob | None:
    """3-minute timeout: record the planned tasks with defaults, but keep the job
    answerable (status stays waiting_user) so the user can still refine later."""
    job = session.get(AsyncJob, job_id)
    if job is None or job.job_type != "plan.analyze" or job.status != "waiting_user":
        return job
    data = dict(job.result_json or {})
    if data.get("auto_committed"):
        return job
    created, data = _commit_and_record(session, job.user_id, data.get("tasks", []), data)
    data["auto_committed"] = True
    jobs_service.transition(
        session,
        job,
        status="waiting_user",
        progress=90,
        current_step=f"已按默认录入 {len(created)} 项，可补充回答后更新",
        result=data,
    )
    return job


def answer_plan(
    session: Session, user_id: uuid.UUID, job_id: uuid.UUID, answers: list[tuple[str, str]]
) -> AsyncJob:
    job = jobs_service.get_owned_job(session, user_id, job_id)
    if job.status != "waiting_user":
        raise ConflictError("Job is not awaiting answers", code="not_waiting")
    data = dict(job.result_json or {})
    # If a 3-minute default was already recorded, drop those tasks — the answer
    # re-plans and recreates them.
    if data.get("auto_committed"):
        _delete_recorded(session, user_id, data)
    stored = list(data.get("answers", []))
    stored.extend({"q": q, "a": a} for q, a in answers if a)
    data["answers"] = stored
    data["rounds"] = int(data.get("rounds", 0)) + 1
    user = session.get(User, user_id)
    if user is not None:
        _remember(user, answers)
    jobs_service.transition(
        session, job, status="queued", progress=40, current_step="根据你的回答重新分析", result=data
    )
    return job


def skip_plan(session: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> AsyncJob:
    """Save whatever was planned so far without answering the questions."""
    job = jobs_service.get_owned_job(session, user_id, job_id)
    if job.status != "waiting_user":
        raise ConflictError("Job is not awaiting answers", code="not_waiting")
    data = dict(job.result_json or {})
    if data.get("auto_committed"):  # already saved by the timeout; just finalize
        jobs_service.transition(
            session,
            job,
            status="completed",
            progress=100,
            current_step=f"已保存 {data.get('created', 0)} 项",
            result=data,
        )
        return job
    created, data = _commit_and_record(session, user_id, data.get("tasks", []), data)
    jobs_service.transition(
        session,
        job,
        status="completed",
        progress=100,
        current_step=f"已创建 {len(created)} 项",
        result=data,
    )
    return job
