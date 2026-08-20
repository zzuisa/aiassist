"""Database-backed coordination for bounded collaborative Agent plans."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.models.agent import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentRun,
    AgentStepArtifact,
    AgentStepAttempt,
    AgentStepDependency,
    AgentTask,
)
from app.models.agent_conversation import AgentConversation, AgentMessage, AgentTurn
from app.models.foundation import AsyncJob
from app.modules.agent.audit import write_execution_record
from app.modules.agent.status import (
    CONVERSATION_MESSAGE_CREATED,
    CONVERSATION_TURN_UPDATED,
    publish_conversation_event,
    publish_plan_event,
    publish_status,
)
from app.modules.jobs import service as jobs_service

_ACCEPTED_DEPENDENCY_STATUSES = {"success", "partial_success"}
_TERMINAL_STEP_STATUSES = {
    "success",
    "partial_success",
    "failed",
    "blocked",
    "skipped",
    "cancelled",
}
_TERMINAL_PLAN_STATUSES = {"success", "partial_success", "failed", "cancelled"}


def _load_plan_locked(session: Session, plan_id: uuid.UUID) -> AgentExecutionPlan:
    plan = session.scalar(
        select(AgentExecutionPlan).where(AgentExecutionPlan.id == plan_id).with_for_update()
    )
    if plan is None:
        raise NotFoundError("Agent plan not found")
    return plan


def _steps(session: Session, plan_id: uuid.UUID) -> list[AgentPlanStep]:
    return list(
        session.scalars(
            select(AgentPlanStep)
            .where(AgentPlanStep.plan_id == plan_id)
            .order_by(AgentPlanStep.position)
        ).all()
    )


def _dependency_map(session: Session, plan_id: uuid.UUID) -> dict[uuid.UUID, list[AgentPlanStep]]:
    rows = session.execute(
        select(AgentStepDependency.step_id, AgentPlanStep)
        .join(AgentPlanStep, AgentPlanStep.id == AgentStepDependency.depends_on_step_id)
        .where(AgentStepDependency.plan_id == plan_id)
    ).all()
    result: dict[uuid.UUID, list[AgentPlanStep]] = {}
    for step_id, dependency in rows:
        result.setdefault(step_id, []).append(dependency)
    return result


def _safe_final_summary(steps: list[AgentPlanStep]) -> str:
    completed = [step for step in steps if step.status in _ACCEPTED_DEPENDENCY_STATUSES]
    failed = [step for step in steps if step.status == "failed"]
    skipped = [step for step in steps if step.status in {"blocked", "skipped", "cancelled"}]
    parts = [f"计划已结束：完成 {len(completed)}/{len(steps)} 个步骤"]
    if failed:
        parts.append(f"失败 {len(failed)} 个")
    if skipped:
        parts.append(f"跳过或阻塞 {len(skipped)} 个")
    summaries = [step.result_summary for step in completed if step.result_summary]
    if summaries:
        parts.append("；".join(summaries[:4]))
    return "；".join(parts)[:4000]


def _finalize_turn(session: Session, plan: AgentExecutionPlan, task: AgentTask) -> None:
    if plan.turn_id is None:
        return
    turn = session.get(AgentTurn, plan.turn_id)
    if turn is None:
        return
    conversation = session.get(AgentConversation, turn.conversation_id)
    user_message = session.get(AgentMessage, turn.user_message_id)
    if conversation is None or user_message is None:
        return
    artifacts = list(
        session.scalars(
            select(AgentStepArtifact)
            .where(AgentStepArtifact.plan_id == plan.id)
            .order_by(AgentStepArtifact.created_at)
        ).all()
    )
    object_ids = list(
        dict.fromkeys(
            str(value)
            for artifact in artifacts
            for value in artifact.object_scope_json.get("object_ids", [])
        )
    )
    if object_ids:
        task.scope_json = {
            **task.scope_json,
            "object_ids": object_ids,
            "valid": True,
        }
        conversation.context_json = {
            **conversation.context_json,
            "object_type": "post",
            "object_ids": object_ids,
            "last_task_id": str(task.id),
            "last_plan_id": str(plan.id),
        }
    turn.status = plan.status
    turn.current_step = "任务处理完成" if plan.status != "failed" else "任务处理失败"
    turn.finished_at = plan.finished_at
    turn_job = session.get(AsyncJob, turn.job_id)
    if turn_job is not None:
        if plan.status == "failed":
            jobs_service.transition(
                session,
                turn_job,
                status="failed",
                current_step="协作任务失败",
                error_code="agent_plan_failed",
                error_message="没有计划步骤成功完成，请展开计划查看失败步骤。",
                error_retryable=any(step.error_retryable for step in _steps(session, plan.id)),
            )
        else:
            jobs_service.transition(
                session,
                turn_job,
                status="completed",
                progress=100,
                current_step="协作任务完成",
                result={"agent_task_id": str(task.id), "plan_id": str(plan.id)},
            )
    if turn.assistant_message_id is None:
        message = AgentMessage(
            conversation_id=conversation.id,
            user_id=plan.user_id,
            role="assistant",
            kind="result" if plan.status != "failed" else "error",
            content_json={
                "text": plan.result_summary or "任务处理完成。",
                "task_id": str(task.id),
                "plan_id": str(plan.id),
                "task_status": task.status,
            },
            reply_to_id=user_message.id,
        )
        session.add(message)
        session.flush()
        turn.assistant_message_id = message.id
        publish_conversation_event(
            session, turn, event_type=CONVERSATION_MESSAGE_CREATED, message_id=message.id
        )
    publish_conversation_event(
        session,
        turn,
        event_type=CONVERSATION_TURN_UPDATED,
        result_summary=plan.result_summary,
    )
    conversation.last_message_at = datetime.now(UTC)


def _finish_plan(
    session: Session, plan: AgentExecutionPlan, task: AgentTask, steps: list[AgentPlanStep]
) -> None:
    completed = sum(step.status in _ACCEPTED_DEPENDENCY_STATUSES for step in steps)
    failed = sum(step.status == "failed" for step in steps)
    skipped = sum(step.status in {"blocked", "skipped", "cancelled"} for step in steps)
    if completed == len(steps):
        status = "success"
    elif completed:
        status = "partial_success"
    else:
        status = "failed"
    now = datetime.now(UTC)
    plan.status = status
    plan.completed_count = completed
    plan.failed_count = failed
    plan.skipped_count = skipped
    plan.result_summary = _safe_final_summary(steps)
    plan.finished_at = now
    plan.version += 1
    task.status = status
    artifacts = list(
        session.scalars(
            select(AgentStepArtifact)
            .where(AgentStepArtifact.plan_id == plan.id)
            .order_by(AgentStepArtifact.created_at)
        ).all()
    )
    tool_results = [
        artifact.payload_json for artifact in artifacts if artifact.artifact_type == "tool_result"
    ]
    analyses = [
        item
        for artifact in artifacts
        if artifact.artifact_type == "analysis_proposals"
        for item in (artifact.payload_json if isinstance(artifact.payload_json, list) else [])
    ]
    public_result: object = (
        tool_results[0]
        if len(tool_results) == 1
        else tool_results
        if tool_results
        else {"已生成未保存": analyses, "失败": failed, "未处理": skipped}
        if analyses
        else plan.result_summary
    )
    task.result_summary = json.dumps(
        {
            "执行计划": {"plan_id": str(plan.id), "status": status},
            "处理结果": public_result,
            "执行记录": {
                "total": len(steps),
                "completed": completed,
                "failed": failed,
                "skipped": skipped,
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    task.finished_at = now
    if status == "failed":
        jobs_service.transition(
            session,
            task.job,
            status="failed",
            current_step="协作任务失败",
            error_code="agent_plan_failed",
            error_message="没有计划步骤成功完成，请展开计划查看失败步骤。",
            error_retryable=any(step.error_retryable for step in steps),
        )
    else:
        jobs_service.transition(
            session,
            task.job,
            status="completed",
            progress=100,
            current_step="协作任务完成",
            result={"agent_task_id": str(task.id), "plan_id": str(plan.id), "status": status},
        )
    _finalize_turn(session, plan, task)
    publish_plan_event(session, plan)


def coordinate_plan(session: Session, plan_id: uuid.UUID) -> list[uuid.UUID]:
    """Claim dependency-ready work and return step ids to enqueue after commit."""
    plan = _load_plan_locked(session, plan_id)
    if plan.status in _TERMINAL_PLAN_STATUSES:
        return []
    task = session.get(AgentTask, plan.task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    steps = _steps(session, plan.id)
    dependencies = _dependency_map(session, plan.id)
    changed = False

    for step in steps:
        if step.status != "pending":
            continue
        parents = dependencies.get(step.id, [])
        if any(
            parent.status in {"failed", "blocked", "skipped", "cancelled"} for parent in parents
        ):
            step.status = "blocked"
            step.stage_label = "前置步骤未成功，已阻塞"
            step.error_code = "agent_plan_dependency_failed"
            step.error_message = "依赖步骤未产生可用结果"
            step.finished_at = datetime.now(UTC)
            changed = True

    waiting = any(step.status == "waiting_confirmation" for step in steps)
    running_count = sum(step.status in {"queued", "running"} for step in steps)
    capacity = max(0, get_settings().agent_plan_max_concurrency - running_count)
    ready: list[AgentPlanStep] = []
    if not waiting and capacity:
        for step in steps:
            if step.status != "pending":
                continue
            parents = dependencies.get(step.id, [])
            if all(parent.status in _ACCEPTED_DEPENDENCY_STATUSES for parent in parents):
                ready.append(step)
                if len(ready) >= capacity:
                    break
    now = datetime.now(UTC)
    for step in ready:
        step.status = "queued"
        step.stage_label = "已排队，等待执行"
        step.queued_at = now
        changed = True

    if plan.started_at is None:
        plan.started_at = now
    turn = session.get(AgentTurn, plan.turn_id) if plan.turn_id else None
    if turn is not None:
        turn.last_heartbeat_at = now
    if waiting:
        plan.status = "waiting_user"
        task.status = "waiting_confirmation"
        if turn is not None:
            turn.status = "waiting_confirmation"
            turn.current_step = "等待用户确认写入"
            turn_job = session.get(AsyncJob, turn.job_id)
            if turn_job is not None and turn_job.status != "waiting_user":
                jobs_service.transition(
                    session,
                    turn_job,
                    status="waiting_user",
                    current_step="等待用户确认写入",
                )
    elif ready or running_count:
        plan.status = "running"
        task.status = "running"
        if task.job.status not in {"processing", "completed", "cancelled"}:
            jobs_service.transition(
                session, task.job, status="processing", current_step="正在执行协作计划"
            )
        if turn is not None:
            turn.status = "executing"
            turn.current_step = "正在执行协作计划"
            turn_job = session.get(AsyncJob, turn.job_id)
            if turn_job is not None and turn_job.status not in {
                "processing",
                "completed",
                "cancelled",
            }:
                jobs_service.transition(
                    session,
                    turn_job,
                    status="processing",
                    current_step="正在执行协作计划",
                )
    steps = _steps(session, plan.id)
    if steps and all(step.status in _TERMINAL_STEP_STATUSES for step in steps):
        _finish_plan(session, plan, task, steps)
        return []
    if changed:
        plan.version += 1
        publish_plan_event(session, plan)
    session.flush()
    return [step.id for step in ready]


def start_step(session: Session, step_id: uuid.UUID) -> AgentPlanStep | None:
    step = session.scalar(
        select(AgentPlanStep).where(AgentPlanStep.id == step_id).with_for_update()
    )
    if step is None:
        raise NotFoundError("Agent plan step not found")
    if step.status != "queued":
        return None
    plan = _load_plan_locked(session, step.plan_id)
    now = datetime.now(UTC)
    step.status = "running"
    step.stage_label = "正在执行"
    step.attempt_count += 1
    step.started_at = step.started_at or now
    plan.status = "running"
    plan.version += 1
    publish_plan_event(session, plan)
    session.flush()
    return step


def fail_step(session: Session, step_id: uuid.UUID, exc: Exception) -> uuid.UUID:
    step = session.scalar(
        select(AgentPlanStep).where(AgentPlanStep.id == step_id).with_for_update()
    )
    if step is None:
        raise NotFoundError("Agent plan step not found")
    plan = _load_plan_locked(session, step.plan_id)
    if step.status not in {"success", "partial_success", "waiting_confirmation"}:
        finished = datetime.now(UTC)
        step.status = "failed"
        step.stage_label = "执行失败"
        step.error_code = str(getattr(exc, "code", None) or type(exc).__name__)[:64]
        step.error_message = "步骤执行失败，可以展开查看并在安全时重试。"
        step.error_retryable = bool(getattr(exc, "retryable", False)) or isinstance(
            exc, (ConnectionError, TimeoutError)
        )
        step.finished_at = finished
        attempt = session.scalar(
            select(AgentStepAttempt).where(
                AgentStepAttempt.step_id == step.id,
                AgentStepAttempt.attempt_number == step.attempt_count,
            )
        )
        if attempt is not None and attempt.status == "running":
            attempt.status = "failed"
            attempt.error_code = step.error_code
            attempt.error_retryable = step.error_retryable
            attempt.finished_at = finished
            attempt.duration_ms = max(
                0, int((finished - attempt.started_at).total_seconds() * 1000)
            )
        run = session.get(AgentRun, step.run_id) if step.run_id else None
        if run is not None and run.status == "running":
            run.status = "failed"
            run.current_tool = None
            run.stage_label = step.stage_label
            run.error_message = step.error_message
            run.finished_at = finished
            task = session.get(AgentTask, plan.task_id)
            if task is not None:
                publish_status(session, task, run)
                write_execution_record(
                    session,
                    task_id=task.id,
                    run_id=run.id,
                    step_id=step.step_key,
                    agent_name=run.agent_name,
                    step_label=step.title,
                    tool_name=step.tool_name,
                    operation_type=(
                        "update"
                        if step.operation_type == "external_effect"
                        else step.operation_type
                    ),
                    params={"plan_step_id": str(step.id), "attempt": step.attempt_count},
                    status="failed",
                    result_summary=step.error_message,
                    started_at=run.started_at,
                    finished_at=finished,
                )
        plan.version += 1
        publish_plan_event(session, plan)
    session.flush()
    return plan.id


def retry_failed_chain(
    session: Session, *, user_id: uuid.UUID, plan_id: uuid.UUID
) -> AgentExecutionPlan:
    plan = _load_plan_locked(session, plan_id)
    if plan.user_id != user_id:
        raise NotFoundError("Agent plan not found")
    if plan.status not in {"failed", "partial_success", "stalled"}:
        raise ConflictError("Plan is not retryable", code="agent_plan_retry_conflict")
    steps = _steps(session, plan.id)
    roots = {
        step.id
        for step in steps
        if step.status in {"failed", "stalled"} and step.error_retryable and step.attempt_count < 2
    }
    if not roots:
        raise ConflictError("Plan has no failed step", code="agent_plan_retry_conflict")
    dependencies = session.execute(
        select(AgentStepDependency.step_id, AgentStepDependency.depends_on_step_id).where(
            AgentStepDependency.plan_id == plan.id
        )
    ).all()
    affected = set(roots)
    changed = True
    while changed:
        changed = False
        for child, parent in dependencies:
            if parent in affected and child not in affected:
                affected.add(child)
                changed = True
    for step in steps:
        if step.id not in affected:
            continue
        step.status = "pending"
        step.stage_label = "等待重试调度"
        step.error_code = None
        step.error_message = None
        step.error_retryable = False
        step.queued_at = None
        step.started_at = None
        step.finished_at = None
        step.result_summary = None
        step.run_id = None
    plan.status = "pending"
    plan.runtime_state = "checkpointed"
    plan.finished_at = None
    plan.result_summary = None
    plan.completed_count = 0
    plan.failed_count = 0
    plan.skipped_count = 0
    plan.error_code = None
    plan.error_message = None
    plan.error_retryable = False
    plan.version += 1
    task = session.get(AgentTask, plan.task_id)
    if task:
        task.status = "pending"
        task.finished_at = None
        if task.job.status == "failed":
            jobs_service.retry_job(session, task.job)
    publish_plan_event(session, plan)
    session.flush()
    return plan


def repair_stalled_plans(session: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=get_settings().agent_turn_heartbeat_timeout_seconds)
    steps = list(
        session.scalars(
            select(AgentPlanStep)
            .where(
                AgentPlanStep.status.in_(("queued", "running")),
                AgentPlanStep.updated_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        ).all()
    )
    plan_ids: set[uuid.UUID] = set()
    for step in steps:
        step.status = "stalled"
        step.stage_label = "执行已停滞"
        step.error_code = "agent_plan_step_stalled"
        step.error_message = "步骤长时间没有进展，可以安全重试。"
        step.error_retryable = True
        step.finished_at = current
        plan_ids.add(step.plan_id)
    for plan_id in plan_ids:
        plan = _load_plan_locked(session, plan_id)
        plan.status = "stalled"
        plan.runtime_state = "failed"
        plan.error_code = "agent_plan_stalled"
        plan.error_message = "部分步骤长时间没有进展，可以安全重试。"
        plan.error_retryable = True
        plan.version += 1
        task = session.get(AgentTask, plan.task_id)
        if task is not None:
            task.status = "failed"
            task.finished_at = current
            if task.job.status not in {"completed", "cancelled", "failed"}:
                jobs_service.transition(
                    session,
                    task.job,
                    status="failed",
                    current_step="协作计划已停滞",
                    error_code=plan.error_code,
                    error_message=plan.error_message,
                    error_retryable=True,
                )
        publish_plan_event(session, plan)
    session.flush()
    return len(steps)
