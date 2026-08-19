"""Execute one claimed plan step through registered tools and persist safe artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.db.session import session_scope
from app.models.agent import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentRun,
    AgentStepArtifact,
    AgentStepAttempt,
    AgentStepDependency,
    AgentTask,
)
from app.modules.agent.audit import write_execution_record
from app.modules.agent.registry import ToolContext, tool_registry
from app.modules.agent.runner import WorkItem, run_bounded
from app.modules.agent.status import publish_plan_event, publish_status


def _dependency_artifacts(session: Session, step: AgentPlanStep) -> list[AgentStepArtifact]:
    parent_ids = list(
        session.scalars(
            select(AgentStepDependency.depends_on_step_id).where(
                AgentStepDependency.step_id == step.id
            )
        ).all()
    )
    if not parent_ids:
        return []
    return list(
        session.scalars(
            select(AgentStepArtifact)
            .where(AgentStepArtifact.step_id.in_(parent_ids))
            .order_by(AgentStepArtifact.created_at)
        ).all()
    )


def _artifact(
    session: Session,
    *,
    step: AgentPlanStep,
    artifact_type: str,
    payload: dict | list,
    object_scope: dict | None = None,
) -> AgentStepArtifact:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    row = AgentStepArtifact(
        plan_id=step.plan_id,
        step_id=step.id,
        artifact_type=artifact_type,
        schema_version="agent-step-artifact.v1",
        payload_json=payload,
        object_scope_json=object_scope or {},
        content_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    session.add(row)
    session.flush()
    return row


def _scope_ids(task: AgentTask, artifacts: list[AgentStepArtifact]) -> list[str]:
    values: list[str] = []
    for artifact in artifacts:
        raw = artifact.object_scope_json.get("object_ids", [])
        if isinstance(raw, list):
            values.extend(str(value) for value in raw)
    if not values:
        raw = task.scope_json.get("object_ids", [])
        if isinstance(raw, list):
            values.extend(str(value) for value in raw)
    return list(dict.fromkeys(values))[:500]


def _execute_content_analysis(
    session: Session,
    *,
    task: AgentTask,
    step: AgentPlanStep,
    run: AgentRun,
    artifacts: list[AgentStepArtifact],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    object_ids = _scope_ids(task, artifacts)
    if not object_ids:
        raise ValidationError(
            "Analysis step has no object scope", code="agent_analysis_scope_required"
        )
    bodies = tool_registry.invoke(
        "posts.read_body",
        context=ToolContext(user_id=task.user_id, task_id=task.id, run_id=run.id, session=session),
        params={"post_ids": object_ids},
    )
    body_by_id = {str(post.get("id")): post for post in bodies if post.get("id")}
    items = [WorkItem(key=post_id, input_scope={"object_ids": [post_id]}) for post_id in body_by_id]
    task_user_id = task.user_id
    task_id = task.id
    run_id = run.id
    request_text = task.request_text

    def analyze(item: WorkItem) -> dict[str, Any]:
        # SQLAlchemy sessions are not thread-safe. Each independent analysis
        # gets its own transaction while the parent step keeps ownership of
        # aggregation and final status.
        with session_scope() as item_session:
            value = tool_registry.invoke(
                "content.extract_metadata",
                context=ToolContext(
                    user_id=task_user_id,
                    task_id=task_id,
                    run_id=run_id,
                    session=item_session,
                ),
                params={"post": body_by_id[item.key], "instruction": request_text},
            )
            if not isinstance(value, Mapping):
                raise ValidationError(
                    "Analysis result is not structured", code="agent_analysis_result_invalid"
                )
            return dict(value)

    outcome = run_bounded(
        items,
        analyze,
        max_concurrency=get_settings().agent_plan_max_concurrency,
        retry_once=True,
    )
    results = [dict(result.value) for result in outcome.succeeded]
    failures = [
        {
            "post_id": result.key,
            "error_code": result.error_code or "agent_analysis_failed",
        }
        for result in outcome.failed
    ]
    step.progress_current = len(outcome.results)
    step.progress_total = len(items)
    if not results:
        raise ValidationError("All analysis items failed", code="agent_analysis_failed")
    return results, {
        "object_type": "post",
        "object_ids": [str(item.get("post_id")) for item in results if item.get("post_id")],
        "failures": failures,
    }


def execute_step(session: Session, step_id: uuid.UUID) -> uuid.UUID:
    step = session.get(AgentPlanStep, step_id)
    if step is None:
        raise NotFoundError("Agent plan step not found")
    if step.status != "running":
        return step.plan_id
    plan = session.get(AgentExecutionPlan, step.plan_id)
    task = session.get(AgentTask, plan.task_id) if plan else None
    if plan is None or task is None:
        raise NotFoundError("Agent plan task not found")
    tool = tool_registry.get(step.tool_name)
    if not tool.available:
        raise ValidationError("Plan tool became unavailable", code="agent_tool_unavailable")
    run = AgentRun(
        task_id=task.id,
        agent_key=step.agent_key,
        agent_version=step.agent_version,
        agent_name=step.agent_name,
        responsibility=step.responsibility,
        current_task=step.title,
        input_scope_json={},
        allowed_tools=[step.tool_name],
        expected_output=step.expected_output,
        status="running",
        current_tool=step.tool_name,
        stage_label="正在执行计划步骤",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    step.run_id = run.id
    attempt = AgentStepAttempt(
        step_id=step.id,
        attempt_number=step.attempt_count,
        idempotency_key=f"agent-plan-step:{step.id}:{step.attempt_count}",
        status="running",
    )
    session.add(attempt)
    publish_status(session, task, run)
    session.flush()
    started = datetime.now(UTC)
    dependency_artifacts = _dependency_artifacts(session, step)
    context = ToolContext(user_id=task.user_id, task_id=task.id, run_id=run.id, session=session)

    if step.tool_name == "content.extract_metadata":
        result, scope = _execute_content_analysis(
            session, task=task, step=step, run=run, artifacts=dependency_artifacts
        )
        _artifact(
            session,
            step=step,
            artifact_type="analysis_proposals",
            payload=result,
            object_scope=scope,
        )
        failures = scope.get("failures", [])
        final_status = "partial_success" if failures else "success"
        summary = f"已完成 {len(result)} 篇文章分析"
        if failures:
            summary += f"，{len(failures)} 篇失败"
    elif tool.type == "write":
        from app.modules.agent import service as agent_service

        changes = [
            item
            for artifact in dependency_artifacts
            if artifact.artifact_type == "analysis_proposals"
            for item in (artifact.payload_json if isinstance(artifact.payload_json, list) else [])
            if isinstance(item, Mapping)
        ]
        if step.tool_name == "posts.apply_analysis":
            from app.models.posts import Post

            raw_ids = [str(item.get("post_id")) for item in changes if item.get("post_id")]
            versions = {
                str(post_id): version
                for post_id, version in session.execute(
                    select(Post.id, Post.version).where(
                        Post.user_id == task.user_id,
                        Post.id.in_([uuid.UUID(value) for value in raw_ids]),
                    )
                ).all()
            }
            targets = [
                {"id": value, "version": versions[value]} for value in raw_ids if value in versions
            ]
        else:
            targets = []
        pending = agent_service.create_pending_write(
            session,
            task=task,
            run=run,
            operation_type="update",
            target_type="post" if step.tool_name == "posts.apply_analysis" else "mcp_external",
            targets=targets,
            preview={
                "summary": step.expected_output,
                "changes": changes,
                "arguments": step.arguments_json,
            },
            reversible=bool(tool.risk.get("reversible", True)),
            tool_name=step.tool_name,
        )
        step.status = "waiting_confirmation"
        step.stage_label = "等待用户确认"
        step.result_summary = f"已生成修改预览，影响 {pending.affected_count} 项"
        plan.status = "waiting_user"
        plan.version += 1
        finished = datetime.now(UTC)
        attempt.status = "success"
        attempt.finished_at = finished
        attempt.duration_ms = max(0, int((finished - attempt.started_at).total_seconds() * 1000))
        _artifact(
            session,
            step=step,
            artifact_type="write_preview",
            payload={"confirmation_id": str(pending.id), "affected_count": pending.affected_count},
        )
        write_execution_record(
            session,
            task_id=task.id,
            run_id=run.id,
            step_id=step.step_key,
            agent_name=run.agent_name,
            step_label=step.title,
            tool_name=step.tool_name,
            operation_type=(
                "update" if step.operation_type == "external_effect" else step.operation_type
            ),
            params={"plan_step_id": str(step.id), "attempt": step.attempt_count},
            status="success",
            result_summary=step.result_summary,
            started_at=started,
            finished_at=finished,
        )
        publish_plan_event(session, plan)
        return plan.id
    else:
        result = tool_registry.invoke(step.tool_name, context=context, params=step.arguments_json)
        payload: dict | list = (
            result if isinstance(result, (dict, list)) else {"value": str(result)[:4000]}
        )
        object_ids = [
            str(item.get("id"))
            for item in result
            if isinstance(result, list) and isinstance(item, Mapping) and item.get("id")
        ]
        _artifact(
            session,
            step=step,
            artifact_type="tool_result",
            payload=payload,
            object_scope={"object_type": "post", "object_ids": object_ids} if object_ids else {},
        )
        final_status = "success"
        summary = f"已获得 {len(result)} 项结果" if isinstance(result, list) else "能力调用完成"
        if isinstance(result, dict) and result.get("is_error"):
            raise ValidationError("MCP tool returned an error", code="agent_mcp_tool_error")

    finished = datetime.now(UTC)
    step.status = final_status
    step.stage_label = "步骤完成" if final_status == "success" else "步骤部分完成"
    step.result_summary = summary[:1000]
    step.finished_at = finished
    run.status = final_status
    run.current_tool = None
    run.stage_label = step.stage_label
    run.result_summary = step.result_summary
    run.finished_at = finished
    attempt.status = "success"
    attempt.finished_at = finished
    attempt.duration_ms = max(0, int((finished - attempt.started_at).total_seconds() * 1000))
    write_execution_record(
        session,
        task_id=task.id,
        run_id=run.id,
        step_id=step.step_key,
        agent_name=run.agent_name,
        step_label=step.title,
        tool_name=step.tool_name,
        operation_type=(
            "analyze" if step.operation_type == "external_effect" else step.operation_type
        ),
        params={"plan_step_id": str(step.id), "attempt": step.attempt_count},
        status="success",
        result_summary=step.result_summary,
        started_at=started,
        finished_at=finished,
    )
    plan.version += 1
    publish_status(session, task, run)
    publish_plan_event(session, plan)
    session.flush()
    return plan.id
