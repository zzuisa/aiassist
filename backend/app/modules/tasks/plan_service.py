"""Quick-add planning: analyze a line into scheduled task candidates.

The user types one line ("明天上午喝咖啡，中午吃自助"); an LLM splits it into tasks,
assigns concrete times (vague parts default sensibly, or use the user's answers),
judges importance, considers the existing schedule to avoid clashes, and may ask a
few bounded questions. Nothing is created during analysis — the caller reviews the
plan, optionally answers, or saves as-is. `commit` then creates the tasks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC
    parts = []
    for t in sorted(rows, key=lambda x: x.start_at)[:20]:
        local = t.start_at.astimezone(tz)
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
    user_prompt = (
        f"{_now_context(tz_name)}\n已有日程：{schedule}\n用户输入：{text}{answer_text}"
    )
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
