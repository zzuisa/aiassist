"""Validated planning, persistence and public serialization for collaborative Agent work."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.agent import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentStepDependency,
    AgentTask,
)
from app.models.agent_conversation import AgentTurn
from app.modules.agent.planning_schemas import (
    AgentPlanView,
    AgentTaskPlanProposal,
    PlanAgentView,
    PlanCounts,
    PlanErrorView,
    PlanProgress,
    PlanStepProposal,
    PlanStepView,
)
from app.modules.agent.registry import ToolDefinition, tool_registry
from app.modules.jobs import service as jobs_service
from app.services.llm.base import LLMError, StructuredRequest

_WRITE_OPERATIONS = {"create", "update", "delete", "publish", "rollback", "external_effect"}
_TERMINAL_STEP_STATUSES = {
    "success",
    "partial_success",
    "failed",
    "blocked",
    "skipped",
    "cancelled",
}


def validate_plan_graph(proposal: AgentTaskPlanProposal, *, max_depth: int) -> None:
    """Reject missing references, cycles and graphs deeper than policy allows."""
    keys = {step.step_key for step in proposal.steps}
    parents = {step.step_key: list(step.depends_on) for step in proposal.steps}
    for step in proposal.steps:
        if step.step_key in step.depends_on:
            raise ValidationError("Plan contains a self cycle", code="agent_plan_cycle")
        missing = [key for key in step.depends_on if key not in keys]
        if missing:
            raise ValidationError(
                "Plan dependency does not exist",
                code="agent_plan_dependency_missing",
                extensions={"step_key": step.step_key},
            )

    visiting: set[str] = set()
    visited: set[str] = set()
    depths: dict[str, int] = {}

    def visit(key: str) -> int:
        if key in visiting:
            raise ValidationError("Plan contains a cycle", code="agent_plan_cycle")
        if key in visited:
            return depths[key]
        visiting.add(key)
        depth = 1 + max((visit(parent) for parent in parents[key]), default=0)
        visiting.remove(key)
        visited.add(key)
        depths[key] = depth
        if depth > max_depth:
            raise ValidationError("Plan exceeds maximum depth", code="agent_plan_too_deep")
        return depth

    for key in keys:
        visit(key)


def _agent_for_tool(tool_name: str) -> tuple[str, str, str]:
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    tool = tool_registry.get(tool_name)
    agent_key = (
        "article-query-agent"
        if tool_name in {"posts.list_recent", "taxonomy.categories", "taxonomy.tags"}
        else "editor-agent"
        if tool_name == "content.extract_metadata"
        else "coordinator-agent"
    )
    if tool.source == "mcp":
        return "mcp-tool-agent", "外部能力 Agent", "agent-task-plan.v1"
    binding = resolve_builtin_agent(agent_key)
    return binding.agent_key, binding.agent_name, binding.version_ref


def _validate_step_tool(
    step: PlanStepProposal,
    *,
    available_tools: Mapping[str, ToolDefinition],
) -> dict[str, Any]:
    tool = available_tools.get(step.tool_name)
    if tool is None or not tool.available:
        raise ValidationError(
            "Plan selected an unavailable tool",
            code="agent_plan_tool_unavailable",
            extensions={"step_key": step.step_key, "tool_name": step.tool_name},
        )
    expects_write = step.operation_type.value in _WRITE_OPERATIONS
    if (tool.type == "write") != expects_write:
        raise ValidationError(
            "Plan operation type does not match tool type",
            code="agent_plan_tool_type_mismatch",
        )
    if tool.type == "write" and not step.requires_confirmation:
        raise ValidationError("Plan write requires confirmation", code="agent_plan_confirmation")
    if tool.type == "read" and step.requires_confirmation:
        raise ValidationError(
            "Read step cannot require write confirmation", code="agent_plan_confirmation"
        )
    arguments = dict(step.arguments)
    # Dependency-driven analysis receives the post payload at execution time.
    # Static arguments are still restricted to an object and bounded by the
    # tool schema where the complete call is already available.
    if step.tool_name != "content.extract_metadata" or step.input_source != "dependency":
        tool.validate_arguments(arguments)
    return arguments


def validate_plan_proposal(
    proposal: AgentTaskPlanProposal,
    *,
    available_tools: Mapping[str, ToolDefinition],
) -> list[tuple[PlanStepProposal, dict[str, Any]]]:
    settings = get_settings()
    if len(proposal.steps) > settings.agent_plan_max_steps:
        raise ValidationError("Plan has too many steps", code="agent_plan_too_large")
    validate_plan_graph(proposal, max_depth=settings.agent_plan_max_depth)
    return [
        (step, _validate_step_tool(step, available_tools=available_tools))
        for step in proposal.steps
    ]


def _validate_scope_flow(proposal: AgentTaskPlanProposal, *, has_context_scope: bool) -> None:
    """Require explicit upstream object scope and analysis before article writes."""
    by_key = {step.step_key: step for step in proposal.steps}

    def upstream_tools(step: PlanStepProposal, visited: set[str] | None = None) -> set[str]:
        seen = set(visited or ())
        if step.step_key in seen:
            return set()
        seen.add(step.step_key)
        tools: set[str] = set()
        for parent_key in step.depends_on:
            parent = by_key.get(parent_key)
            if parent is None:
                continue
            tools.add(parent.tool_name)
            tools.update(upstream_tools(parent, seen))
        return tools

    for step in proposal.steps:
        upstream = upstream_tools(step)
        if (
            step.tool_name == "content.extract_metadata"
            and not has_context_scope
            and not {"posts.list_recent", "posts.filter_missing_tags"}.intersection(upstream)
        ):
            raise ValidationError(
                "Analysis step has no authorized object scope",
                code="agent_plan_analysis_scope_missing",
            )
        if step.tool_name == "posts.apply_analysis" and "content.extract_metadata" not in upstream:
            raise ValidationError(
                "Write step has no analysis proposal dependency",
                code="agent_plan_write_input_missing",
            )


def _seed_proposal(
    *,
    objective: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    tool: ToolDefinition,
    has_context_scope: bool,
    can_analyze: bool = True,
    can_query: bool = True,
    query_arguments: Mapping[str, Any] | None = None,
) -> AgentTaskPlanProposal:
    query_step = PlanStepProposal(
        step_key="step_query",
        title="查询目标文章",
        responsibility="查询当前用户授权范围内的轻量文章元数据",
        tool_name="posts.list_recent",
        operation_type="query",
        arguments=dict(query_arguments or {"limit": 10}),
        depends_on=[],
        input_source="current_message",
        expected_output="明确的文章 ID 范围",
        requires_confirmation=False,
    )
    analysis_step = PlanStepProposal(
        step_key="step_analyze",
        title="分析文章内容",
        responsibility="读取明确范围内的文章并生成标签、关键词与摘要提案",
        tool_name="content.extract_metadata",
        operation_type="analyze",
        arguments={},
        depends_on=[] if has_context_scope else ["step_query"],
        input_source="conversation_context" if has_context_scope else "dependency",
        expected_output="文章元数据分析提案",
        requires_confirmation=False,
    )
    if tool_name == "content.extract_metadata" and not has_context_scope and can_query:
        return AgentTaskPlanProposal(
            objective=objective[:500] or "查询并分析文章",
            steps=[query_step, analysis_step],
        )
    if tool_name == "posts.apply_analysis" and can_analyze and (has_context_scope or can_query):
        prefix = [analysis_step] if has_context_scope else [query_step, analysis_step]
        return AgentTaskPlanProposal(
            objective=objective[:500] or "分析并保存文章元数据",
            steps=[
                *prefix,
                PlanStepProposal(
                    step_key="step_apply",
                    title="确认并保存分析结果",
                    responsibility=tool.responsibility[:300],
                    tool_name=tool_name,
                    operation_type="update",
                    arguments=dict(arguments),
                    depends_on=["step_analyze"],
                    input_source="dependency",
                    expected_output="待用户确认的写入预览",
                    requires_confirmation=True,
                ),
            ],
        )
    operation = (
        "update"
        if tool.type == "write"
        else ("analyze" if tool_name == "content.extract_metadata" else "query")
    )
    return AgentTaskPlanProposal(
        objective=objective[:500] or "执行用户任务",
        steps=[
            PlanStepProposal(
                step_key="step_execute",
                title=tool.responsibility[:120],
                responsibility=tool.responsibility[:300],
                tool_name=tool_name,
                operation_type=operation,
                arguments=dict(arguments),
                depends_on=[],
                input_source=("conversation_context" if has_context_scope else "current_message"),
                expected_output="生成该能力的结构化结果"[:300],
                requires_confirmation=tool.type == "write",
            )
        ],
    )


def propose_plan(
    session: Session,
    *,
    user_id: uuid.UUID,
    request_text: str,
    objective: str,
    seed_tool_name: str,
    seed_arguments: Mapping[str, Any],
    context: Mapping[str, Any],
    gateway: Any | None = None,
    run_reference: str | None = None,
) -> AgentTaskPlanProposal:
    """Ask the versioned planner for a DAG, with a safe one-step fallback."""
    manifest = tool_registry.safe_manifest_v2(session=session, user_id=user_id)
    available_entries = [item for item in manifest["tools"] if item.get("available")]
    available = {
        str(item["key"]): tool_registry.get(str(item["key"])) for item in available_entries
    }
    seed_tool = available.get(seed_tool_name)
    if seed_tool is None:
        raise ValidationError("Seed tool is unavailable", code="agent_plan_tool_unavailable")
    from app.modules.ai_config.service import bind

    config = bind(session, user_id, "agent_task_plan", run_reference=run_reference)
    query_arguments = dict(config.tool_defaults.get("posts.list_recent", {"limit": 10}))
    requested_limit = seed_arguments.get("limit")
    if isinstance(requested_limit, int) and not isinstance(requested_limit, bool):
        query_arguments["limit"] = min(max(requested_limit, 1), 100)
    fallback = _seed_proposal(
        objective=objective,
        tool_name=seed_tool_name,
        arguments={**config.tool_defaults.get(seed_tool_name, {}), **seed_arguments},
        tool=seed_tool,
        has_context_scope=bool(context.get("object_ids")),
        can_analyze="content.extract_metadata" in available,
        can_query="posts.list_recent" in available,
        query_arguments=query_arguments,
    )
    if gateway is None:
        from app.services.llm.gateway import get_llm_gateway

        gateway = get_llm_gateway()
    payload = {
        "request": request_text,
        "objective": objective,
        "conversation_scope": {
            "object_type": context.get("object_type"),
            "object_ids": list(context.get("object_ids", []))[:500],
        },
        "candidate_tools": available_entries,
        "skill_tool_defaults": config.tool_defaults,
        "limits": {
            "max_steps": get_settings().agent_plan_max_steps,
            "max_depth": get_settings().agent_plan_max_depth,
        },
    }
    try:
        proposal = gateway.structured(
            StructuredRequest(
                scenario="agent_task_plan",
                system=config.system_instruction,
                user=json.dumps(payload, ensure_ascii=False),
                schema=AgentTaskPlanProposal,
                temperature=0.0,
                max_tokens=2400,
                repair_attempts=1,
                reasoning_budget=1024,
            )
        )
    except LLMError:
        # A real one-step execution remains possible and truthful; no synthetic
        # multi-step output or tool result is invented when planning degrades.
        proposal = fallback
    with_defaults = proposal.model_copy(
        update={
            "steps": [
                step.model_copy(
                    update={
                        "arguments": {
                            **config.tool_defaults.get(step.tool_name, {}),
                            **step.arguments,
                        }
                    }
                )
                for step in proposal.steps
            ]
        }
    )
    try:
        _validate_scope_flow(with_defaults, has_context_scope=bool(context.get("object_ids")))
        validate_plan_proposal(with_defaults, available_tools=available)
    except (ValidationError, ValueError):
        _validate_scope_flow(fallback, has_context_scope=bool(context.get("object_ids")))
        validate_plan_proposal(fallback, available_tools=available)
        return fallback
    return with_defaults


def persist_plan(
    session: Session,
    *,
    task: AgentTask,
    proposal: AgentTaskPlanProposal,
    turn: AgentTurn | None = None,
) -> AgentExecutionPlan:
    existing = session.scalar(
        select(AgentExecutionPlan).where(AgentExecutionPlan.task_id == task.id)
    )
    if existing is not None:
        return existing
    from app.modules.agent.capability_snapshot_service import create_snapshot

    capability_snapshot = create_snapshot(session, task=task)
    plan = AgentExecutionPlan(
        user_id=task.user_id,
        task_id=task.id,
        turn_id=turn.id if turn else None,
        schema_version=proposal.schema_version,
        objective=proposal.objective,
        status="pending",
        version=1,
        step_count=len(proposal.steps),
        capability_snapshot_id=capability_snapshot.id,
        phase="planning",
    )
    session.add(plan)
    session.flush()
    # LangGraph uses the durable plan identity as its resumable thread key.
    plan.graph_thread_id = str(plan.id)
    plan.runtime_state = "checkpointed"
    plan.phase = "executing"
    step_rows: dict[str, AgentPlanStep] = {}
    for position, step in enumerate(proposal.steps, start=1):
        agent_key, agent_name, agent_version = _agent_for_tool(step.tool_name)
        row = AgentPlanStep(
            plan_id=plan.id,
            step_key=step.step_key,
            position=position,
            title=step.title,
            responsibility=step.responsibility,
            agent_key=agent_key,
            agent_name=agent_name,
            agent_version=agent_version,
            tool_name=step.tool_name,
            operation_type=step.operation_type.value,
            arguments_json=step.arguments,
            input_source=step.input_source.value,
            expected_output=step.expected_output,
            requires_confirmation=step.requires_confirmation,
            status="pending",
            stage_label="等待依赖" if step.depends_on else "等待调度",
        )
        session.add(row)
        session.flush()
        step_rows[step.step_key] = row
    for step in proposal.steps:
        for dependency_key in step.depends_on:
            session.add(
                AgentStepDependency(
                    plan_id=plan.id,
                    step_id=step_rows[step.step_key].id,
                    depends_on_step_id=step_rows[dependency_key].id,
                    accepted_statuses_json=["success", "partial_success"],
                )
            )
    session.flush()
    return plan


def persist_legacy_task_plan(session: Session, task: AgentTask) -> AgentExecutionPlan:
    """Build the same durable plan representation for the legacy task entry point."""
    existing = session.scalar(
        select(AgentExecutionPlan).where(AgentExecutionPlan.task_id == task.id)
    )
    if existing is not None:
        return existing

    if task.intent_key == "llm.route":
        from app.modules.agent.conversation_router import route_message
        from app.modules.agent.conversation_service import sync_mcp_connections

        sync_mcp_connections(session, user_id=task.user_id)
        outcome = route_message(
            task.request_text,
            session=session,
            user_id=task.user_id,
            context=task.scope_json,
            run_reference=f"agent-task-route:{task.id}",
        )
        selected_tool = outcome.selected_tool or "agent.capabilities"
        arguments = outcome.route.semantic_arguments if outcome.selected_tool else {}
        task.scope_json = {
            **task.scope_json,
            "llm_selected_tool": selected_tool,
            "tool_parameters": dict(arguments),
        }
        proposal = propose_plan(
            session,
            user_id=task.user_id,
            request_text=task.request_text,
            objective=outcome.route.objective,
            seed_tool_name=selected_tool,
            seed_arguments=arguments,
            context=task.scope_json,
            run_reference=f"agent-task:{task.id}",
        )
        return persist_plan(session, task=task, proposal=proposal)

    from app.modules.agent.intents import IntentPlan, dispatch_intent

    intent = dispatch_intent(task.intent_key, task.request_text)
    if not isinstance(intent, IntentPlan):
        raise ValidationError("Intent produced an invalid plan", code="agent_intent_plan_invalid")
    proposal = propose_plan(
        session,
        user_id=task.user_id,
        request_text=task.request_text,
        objective=task.request_text[:500],
        seed_tool_name=intent.tool_name,
        seed_arguments=intent.params,
        context=task.scope_json,
        run_reference=f"agent-task:{task.id}",
    )
    return persist_plan(session, task=task, proposal=proposal)


def get_owned_plan(session: Session, user_id: uuid.UUID, plan_id: uuid.UUID) -> AgentExecutionPlan:
    plan = session.scalar(
        select(AgentExecutionPlan).where(
            AgentExecutionPlan.id == plan_id, AgentExecutionPlan.user_id == user_id
        )
    )
    if plan is None:
        raise NotFoundError("Agent plan not found")
    return plan


def cancel_plan(session: Session, *, user_id: uuid.UUID, plan_id: uuid.UUID) -> AgentExecutionPlan:
    """Cooperatively cancel future Graph work while preserving applied effects."""
    plan = session.scalar(
        select(AgentExecutionPlan)
        .where(AgentExecutionPlan.id == plan_id, AgentExecutionPlan.user_id == user_id)
        .with_for_update()
    )
    if plan is None:
        raise NotFoundError("Agent plan not found")
    if plan.status in {"success", "partial_success", "failed", "cancelled"}:
        if plan.status == "cancelled":
            return plan
        raise ConflictError("Plan is already terminal", code="agent_plan_cancel_conflict")

    now = datetime.now(UTC)
    steps = list(
        session.scalars(
            select(AgentPlanStep)
            .where(AgentPlanStep.plan_id == plan.id)
            .order_by(AgentPlanStep.position)
        ).all()
    )
    for step in steps:
        if step.status in {"pending", "queued", "waiting_confirmation"}:
            step.status = "cancelled"
            step.stage_label = "已取消"
            step.finished_at = now
    plan.status = "cancelled"
    plan.runtime_state = "checkpointed"
    plan.skipped_count = sum(step.status in {"blocked", "skipped", "cancelled"} for step in steps)
    plan.finished_at = now
    plan.version += 1
    task = session.get(AgentTask, plan.task_id)
    if task is not None:
        task.status = "cancelled"
        task.finished_at = now
        if task.job.status not in {"completed", "failed", "cancelled"}:
            jobs_service.transition(
                session,
                task.job,
                status="cancelled",
                current_step="协作计划已取消",
            )
    from app.modules.agent.status import publish_plan_event

    publish_plan_event(session, plan)
    session.flush()
    return plan


def plan_for_turn(session: Session, user_id: uuid.UUID, turn_id: uuid.UUID) -> AgentExecutionPlan:
    plan = session.scalar(
        select(AgentExecutionPlan).where(
            AgentExecutionPlan.turn_id == turn_id, AgentExecutionPlan.user_id == user_id
        )
    )
    if plan is None:
        raise NotFoundError("Agent plan not found")
    return plan


def list_conversation_plans(
    session: Session, user_id: uuid.UUID, conversation_id: uuid.UUID, *, limit: int = 20
) -> list[AgentExecutionPlan]:
    return list(
        session.scalars(
            select(AgentExecutionPlan)
            .join(AgentTurn, AgentTurn.id == AgentExecutionPlan.turn_id)
            .where(
                AgentExecutionPlan.user_id == user_id,
                AgentTurn.conversation_id == conversation_id,
            )
            .order_by(AgentExecutionPlan.created_at.desc())
            .limit(min(max(limit, 1), 50))
        ).all()
    )


def serialize_plan(session: Session, plan: AgentExecutionPlan) -> AgentPlanView:
    steps = list(
        session.scalars(
            select(AgentPlanStep)
            .where(AgentPlanStep.plan_id == plan.id)
            .order_by(AgentPlanStep.position)
        ).all()
    )
    dependencies = session.execute(
        select(AgentStepDependency.step_id, AgentPlanStep.step_key)
        .join(AgentPlanStep, AgentPlanStep.id == AgentStepDependency.depends_on_step_id)
        .where(AgentStepDependency.plan_id == plan.id)
    ).all()
    deps: dict[uuid.UUID, list[str]] = {}
    for step_id, key in dependencies:
        deps.setdefault(step_id, []).append(key)
    turn = session.get(AgentTurn, plan.turn_id) if plan.turn_id else None
    now = plan.finished_at or datetime.now(UTC)
    elapsed = None
    if plan.started_at:
        elapsed = max(0, int((now - plan.started_at).total_seconds() * 1000))
    step_views: list[PlanStepView] = []
    for step in steps:
        step_elapsed = None
        if step.started_at:
            step_elapsed = max(
                0,
                int(
                    ((step.finished_at or datetime.now(UTC)) - step.started_at).total_seconds()
                    * 1000
                ),
            )
        progress = (
            PlanProgress(
                current=step.progress_current,
                total=step.progress_total,
                stage_label=step.stage_label,
            )
            if step.progress_current is not None and step.progress_total is not None
            else None
        )
        error = (
            PlanErrorView(
                code=step.error_code,
                message=(step.error_message or "步骤执行失败")[:1000],
                retryable=step.error_retryable,
            )
            if step.error_code
            else None
        )
        step_views.append(
            PlanStepView(
                step_id=step.id,
                step_key=step.step_key,
                position=step.position,
                title=step.title,
                responsibility=step.responsibility,
                agent=PlanAgentView(key=step.agent_key, name=step.agent_name),
                tool_name=step.tool_name,
                operation_type=step.operation_type,
                depends_on=deps.get(step.id, []),
                status=step.status,
                progress=progress,
                attempt_count=step.attempt_count,
                stage_label=step.stage_label,
                result_summary=(step.result_summary or "")[:1000] or None,
                error=error,
                started_at=step.started_at,
                finished_at=step.finished_at,
                duration_ms=step_elapsed,
            )
        )
    plan_error = (
        PlanErrorView(
            code=plan.error_code,
            message=(plan.error_message or "任务执行失败")[:1000],
            retryable=plan.error_retryable,
        )
        if plan.error_code
        else None
    )
    return AgentPlanView(
        plan_id=plan.id,
        turn_id=plan.turn_id,
        task_id=plan.task_id,
        user_message_id=turn.user_message_id if turn else None,
        objective=plan.objective,
        status=plan.status,
        phase=plan.phase,
        runtime_state=plan.runtime_state,
        graph_run_id=plan.graph_run_id,
        version=plan.version,
        counts=PlanCounts(
            total=plan.step_count,
            completed=plan.completed_count,
            failed=plan.failed_count,
            skipped=plan.skipped_count,
        ),
        elapsed_ms=elapsed,
        result_summary=(plan.result_summary or "")[:4000] or None,
        error=plan_error,
        steps=step_views,
        created_at=plan.created_at,
        finished_at=plan.finished_at,
    )


def terminal_step(status: str) -> bool:
    return status in _TERMINAL_STEP_STATUSES
