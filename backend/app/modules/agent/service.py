"""Durable Agent task lifecycle primitives."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.agent import AgentRun, AgentTask, PendingWrite
from app.modules.agent.audit import write_execution_record
from app.modules.agent.intents import IntentPlan, dispatch_intent
from app.modules.agent.registry import ToolContext, tool_registry
from app.modules.agent.runner import BatchOutcome, WorkItem, enforce_batch_limit, run_configured
from app.modules.agent.status import publish_status
from app.modules.jobs import service as jobs_service

AnalysisCallable = Callable[[dict[str, str], str], Mapping[str, Any] | Any]

_OPERATIONS = {"query", "analyze", "create", "update", "delete", "publish", "rollback"}
_WRITE_SIGNALS = ("保存", "写入", "应用", "更新到", "落库")


def _request_wants_write(request_text: str) -> bool:
    return any(signal in request_text.casefold() for signal in _WRITE_SIGNALS)


def _high_risk_write(
    operation_type: str,
    targets: Sequence[Mapping[str, Any]],
    preview: Mapping[str, Any],
) -> bool:
    return (
        operation_type == "delete"
        or bool(preview.get("overwrite"))
        or (operation_type == "update" and len(targets) > 1)
    )


def create_pending_write(
    session: Session,
    *,
    task: AgentTask,
    run: AgentRun,
    operation_type: str,
    target_type: str,
    targets: Sequence[Mapping[str, Any]],
    preview: Mapping[str, Any],
    reversible: bool,
    tool_name: str,
    original_request_confirmed: bool = False,
) -> PendingWrite:
    """Persist an auditable proposal and stop execution before any business write."""
    del original_request_confirmed  # Never bypass the structured confirmation endpoint.
    if operation_type not in _OPERATIONS or operation_type in {"query", "analyze"}:
        raise ValidationError(
            "Pending write operation is invalid",
            code="agent_pending_write_operation_invalid",
        )
    tool = tool_registry.get(tool_name)
    if tool.type != "write" or not tool.available:
        raise ValidationError(
            "Requested tool is not an available write capability",
            code="agent_write_capability_unavailable",
        )
    normalized_targets: list[dict[str, Any]] = []
    for target in targets:
        try:
            target_id = str(uuid.UUID(str(target.get("id") or "")))
        except ValueError as exc:
            raise ValidationError(
                "Pending write target id is invalid",
                code="agent_write_target_invalid",
            ) from exc
        version = target.get("version")
        if version is not None and (not isinstance(version, int) or version < 0):
            raise ValidationError(
                "Pending write target version is invalid",
                code="agent_write_target_invalid",
            )
        normalized_targets.append({"id": target_id, "version": version})

    pending = PendingWrite(
        task_id=task.id,
        run_id=run.id,
        operation_type=operation_type,
        target_type=target_type,
        targets_json=normalized_targets,
        preview_json=dict(preview),
        affected_count=len(normalized_targets),
        reversible=reversible,
        high_risk=_high_risk_write(operation_type, normalized_targets, preview),
        decision="pending",
    )
    session.add(pending)
    session.flush()
    tools_by_confirmation = dict(task.scope_json.get("pending_write_tools", {}))
    tools_by_confirmation[str(pending.id)] = tool_name
    pending_write_ids = _scope_ids(task.scope_json.get("pending_write_ids"))
    pending_write_ids.append(str(pending.id))
    task.scope_json = {
        **task.scope_json,
        "pending_write_tools": tools_by_confirmation,
        "pending_write_ids": pending_write_ids,
    }
    task.status = "waiting_confirmation"
    task.finished_at = None
    run.allowed_tools = list(dict.fromkeys([*run.allowed_tools, tool_name]))
    run.allow_write = False
    run.status = "waiting_confirmation"
    run.current_tool = None
    run.stage_label = "等待确认写入"
    run.finished_at = None
    jobs_service.transition(
        session,
        task.job,
        status="waiting_user",
        progress=90,
        current_step="等待确认写入",
        result={"agent_task_id": str(task.id), "confirmation_id": str(pending.id)},
    )
    publish_status(session, task, run)
    session.flush()
    return pending


def prepare_pending_write(
    session: Session,
    *,
    task: AgentTask,
    run: AgentRun,
    operation_type: str,
    target_type: str,
    targets: Sequence[Mapping[str, Any]],
    preview: Mapping[str, Any],
    reversible: bool,
    tool_name: str,
    original_request_confirmed: bool = False,
) -> tuple[PendingWrite | None, str]:
    """Create a proposal or explicitly report that generated output cannot be saved."""
    try:
        tool = tool_registry.get(tool_name)
    except ValidationError:
        tool = None
    if tool is None or tool.type != "write" or not tool.available:
        message = "结果已生成，但当前没有可用的写入能力，因此无法保存；生成结果仍可查看。"
        run.allow_write = False
        run.status = "partial_success"
        run.current_tool = None
        run.stage_label = "已生成但无法保存"
        run.result_summary = message
        run.finished_at = datetime.now(UTC)
        task.status = "partial_success"
        task.finished_at = run.finished_at
        jobs_service.transition(
            session,
            task.job,
            status="completed",
            progress=100,
            current_step="已生成但无法保存",
            result={"agent_task_id": str(task.id), "status": "partial_success"},
        )
        publish_status(session, task, run)
        session.flush()
        return None, message
    pending = create_pending_write(
        session,
        task=task,
        run=run,
        operation_type=operation_type,
        target_type=target_type,
        targets=targets,
        preview=preview,
        reversible=reversible,
        tool_name=tool_name,
        original_request_confirmed=original_request_confirmed,
    )
    return pending, "等待确认后保存。"


def list_pending_writes(
    session: Session,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
) -> list[PendingWrite]:
    get_owned_task(session, user_id, task_id)
    return list(
        session.scalars(
            select(PendingWrite)
            .where(PendingWrite.task_id == task_id)
            .order_by(PendingWrite.created_at, PendingWrite.id)
        ).all()
    )


def _update_confirmation_result(
    task: AgentTask,
    *,
    decision: str,
    saved: Sequence[Mapping[str, Any]] = (),
) -> None:
    try:
        reply = json.loads(task.result_summary or "{}")
    except json.JSONDecodeError:
        reply = {}
    if not isinstance(reply, dict):
        reply = {}
    result = reply.get("执行结果")
    if not isinstance(result, dict):
        result = {}
    result["已保存"] = list(saved)
    result["写入确认"] = "已批准并执行" if decision == "approved" else "用户已拒绝，未写入"
    reply["执行结果"] = result
    task.result_summary = json.dumps(reply, ensure_ascii=False, separators=(",", ":"))


def decide_pending_write(
    session: Session,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    confirmation_id: uuid.UUID,
    decision: str,
) -> PendingWrite:
    """Record one decision and resume the approved write in the same transaction."""
    if decision not in {"approve", "reject"}:
        raise ValidationError("Invalid confirmation decision", code="agent_decision_invalid")
    task = get_owned_task(session, user_id, task_id)
    pending = session.scalar(
        select(PendingWrite)
        .where(PendingWrite.id == confirmation_id, PendingWrite.task_id == task.id)
        .with_for_update()
    )
    if pending is None:
        raise NotFoundError("Pending write not found")
    if pending.decision != "pending" or task.status != "waiting_confirmation":
        raise ConflictError(
            "Pending write was already decided or task is not waiting for confirmation",
            code="agent_confirmation_conflict",
        )
    run = session.get(AgentRun, pending.run_id) if pending.run_id else None
    if run is None or run.task_id != task.id or run.status != "waiting_confirmation":
        raise ConflictError(
            "Agent run is not waiting for confirmation",
            code="agent_confirmation_conflict",
        )
    now = datetime.now(UTC)
    confirmed_operations = list(task.scope_json.get("confirmed_operations", []))
    confirmed_operations.append(
        {
            "confirmation_id": str(pending.id),
            "operation_type": pending.operation_type,
            "decision": "approved" if decision == "approve" else "rejected",
            "decided_at": now.isoformat(),
        }
    )
    task.scope_json = {
        **task.scope_json,
        "confirmed_operations": confirmed_operations,
        "pending_write_ids": [
            value
            for value in _scope_ids(task.scope_json.get("pending_write_ids"))
            if value != str(pending.id)
        ],
    }
    if decision == "reject":
        pending.decision = "rejected"
        pending.decided_at = now
        run.allow_write = False
        run.status = "success"
        run.stage_label = "写入已取消"
        run.result_summary = "用户已拒绝写入，业务数据未修改"
        run.finished_at = now
        task.status = "success"
        task.finished_at = now
        _update_confirmation_result(task, decision="rejected")
        jobs_service.transition(
            session,
            task.job,
            status="completed",
            progress=100,
            current_step="写入已取消",
            result={"agent_task_id": str(task.id), "status": "success"},
        )
        publish_status(session, task, run)
        session.flush()
        return pending

    tool_name = task.scope_json.get("pending_write_tools", {}).get(str(pending.id))
    if not isinstance(tool_name, str):
        raise ConflictError(
            "Write capability binding is missing",
            code="agent_write_capability_missing",
        )
    pending.decision = "approved"
    pending.decided_at = now
    run.allow_write = True
    run.status = "running"
    run.current_tool = tool_name
    run.stage_label = "正在执行已确认写入"
    publish_status(session, task, run)
    saved = tool_registry.invoke(
        tool_name,
        context=ToolContext(
            user_id=user_id,
            task_id=task.id,
            run_id=run.id,
            session=session,
        ),
        params={"confirmation_id": str(pending.id)},
    )
    finished = datetime.now(UTC)
    run.allow_write = False
    run.status = "success"
    run.current_tool = None
    run.stage_label = "确认写入完成"
    run.result_summary = f"已保存 {len(saved) if isinstance(saved, list) else 1} 项"
    run.finished_at = finished
    task.status = "success"
    task.finished_at = finished
    _update_confirmation_result(
        task,
        decision="approved",
        saved=saved if isinstance(saved, list) else [saved],
    )
    write_execution_record(
        session,
        task_id=task.id,
        run_id=run.id,
        step_id=f"write-{pending.id.hex[:12]}",
        agent_name=run.agent_name,
        step_label="执行用户已确认的文章写入",
        tool_name=tool_name,
        operation_type=pending.operation_type,
        params={"confirmation_id": str(pending.id), "affected_count": pending.affected_count},
        status="success",
        result_summary=run.result_summary,
        started_at=now,
    )
    jobs_service.transition(
        session,
        task.job,
        status="completed",
        progress=100,
        current_step="确认写入完成",
        result={"agent_task_id": str(task.id), "status": "success"},
    )
    publish_status(session, task, run)
    session.flush()
    return pending


def create_agent_task(
    session: Session,
    *,
    user_id: uuid.UUID,
    request_text: str,
    intent_key: str,
    scope: dict | None = None,
    idempotency_key: str | None = None,
) -> AgentTask:
    """Persist an AgentTask and paired AsyncJob in the caller's transaction.

    This function deliberately performs no model or provider call. Callers must
    commit this transaction before dispatching asynchronous intelligence work.
    """
    text = request_text.strip()
    if not text:
        raise ValidationError("Request text is required", code="agent_request_empty")
    if len(text) > 4000:
        raise ValidationError("Request text is too long", code="agent_request_too_long")
    if not intent_key or len(intent_key) > 64:
        raise ValidationError("Intent key is invalid", code="agent_intent_key_invalid")

    task_id = uuid.uuid4()
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="agent.execute",
        entity_type="agent_task",
        entity_id=task_id,
        idempotency_key=idempotency_key,
        max_retries=1,
    )
    task = AgentTask(
        id=task_id,
        user_id=user_id,
        job=job,
        request_text=text,
        intent_key=intent_key,
        status="pending",
        scope_json=scope or {},
    )
    session.add(task)
    session.flush()
    return task


def get_owned_task(session: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> AgentTask:
    task = session.get(AgentTask, task_id)
    if task is None or task.user_id != user_id:
        raise NotFoundError("Agent task not found")
    return task


def _scope_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, (str, uuid.UUID)):
            continue
        object_id = str(item).strip()
        if object_id and object_id not in normalized:
            normalized.append(object_id)
    return normalized


def remaining_scope_object_ids(scope: Mapping[str, Any]) -> list[str]:
    """Return scope objects that have not already completed successfully."""
    completed = set(_scope_ids(scope.get("completed_object_ids")))
    return [
        object_id for object_id in _scope_ids(scope.get("object_ids")) if object_id not in completed
    ]


def _current_post_versions(
    session: Session,
    user_id: uuid.UUID,
    object_ids: Sequence[str],
) -> dict[str, int]:
    from app.models.posts import Post

    parsed: list[uuid.UUID] = []
    for object_id in object_ids:
        try:
            parsed.append(uuid.UUID(object_id))
        except ValueError:
            continue
    if not parsed:
        return {}
    rows = session.execute(
        select(Post.id, Post.version).where(
            Post.user_id == user_id,
            Post.id.in_(parsed),
            Post.deleted_at.is_(None),
        )
    ).all()
    return {str(post_id): version for post_id, version in rows}


def inherit_conversation_scope(
    session: Session,
    *,
    user_id: uuid.UUID,
    previous: AgentTask,
    request_text: str,
) -> dict[str, Any]:
    """Copy an owned prior scope and refresh it when its object snapshot is stale."""
    del request_text  # Explicit previous_task_id is the unambiguous conversation link.
    prior = dict(previous.scope_json or {})
    object_ids = _scope_ids(prior.get("object_ids"))
    prior_versions = prior.get("object_versions")
    if not isinstance(prior_versions, Mapping):
        prior_versions = {}
    current_versions = _current_post_versions(session, user_id, object_ids)
    stale = bool(object_ids) and (
        set(current_versions) != set(object_ids)
        or any(
            prior_versions.get(object_id) != version
            for object_id, version in current_versions.items()
        )
    )
    refreshed = False
    notice: str | None = None
    query_conditions = prior.get("query_conditions")
    if not isinstance(query_conditions, Mapping):
        query_conditions = {}
    if stale:
        refreshed = True
        notice = "上一轮对象已变化或不可用，已按原查询条件刷新处理范围。"
        if previous.intent_key == "articles.list_recent":
            result = tool_registry.invoke(
                "posts.list_recent",
                context=ToolContext(
                    user_id=user_id,
                    task_id=previous.id,
                    run_id=None,
                    session=session,
                ),
                params=dict(query_conditions),
            )
            object_ids = _scope_ids(
                [item.get("id") for item in result if isinstance(item, Mapping)]
                if isinstance(result, list)
                else []
            )
        else:
            object_ids = [object_id for object_id in object_ids if object_id in current_versions]
        current_versions = _current_post_versions(session, user_id, object_ids)

    scope = {
        **prior,
        "object_ids": object_ids,
        "object_versions": current_versions,
        "query_conditions": dict(query_conditions),
        "query_range": dict(prior.get("query_range", {}))
        if isinstance(prior.get("query_range"), Mapping)
        else {},
        "sort": prior.get("sort"),
        "confirmed_operations": list(prior.get("confirmed_operations", []))
        if isinstance(prior.get("confirmed_operations"), list)
        else [],
        "pending_write_ids": _scope_ids(prior.get("pending_write_ids")),
        "completed_object_ids": _scope_ids(prior.get("completed_object_ids")),
        "failed_object_ids": _scope_ids(prior.get("failed_object_ids")),
        "valid": True,
        "scope_refreshed": refreshed,
        "refresh_notice": notice,
        "previous_task_id": str(previous.id),
    }
    return scope


def list_owned_tasks(
    session: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[AgentTask]:
    stmt = select(AgentTask).where(AgentTask.user_id == user_id)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    return list(session.scalars(stmt.order_by(AgentTask.created_at.desc()).limit(limit)).all())


def task_runs(session: Session, task_id: uuid.UUID) -> list[AgentRun]:
    return list(
        session.scalars(
            select(AgentRun)
            .where(AgentRun.task_id == task_id)
            .order_by(AgentRun.started_at, AgentRun.id)
        ).all()
    )


def clean_result_items(
    items: list[dict[str, Any]], *, name_field: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize names, drop empty/duplicate rows, and report anomalies."""
    cleaned: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        normalized = " ".join(str(item.get(name_field) or "").split())
        if not normalized:
            anomalies.append({"id": item.get("id"), "reason": "empty_name"})
            continue
        key = normalized.casefold()
        if key in seen:
            anomalies.append({"id": item.get("id"), "reason": "duplicate_name"})
            continue
        seen.add(key)
        value = {**item, name_field: normalized}
        if isinstance(value.get("usage_count"), (int, float)) and value["usage_count"] < 0:
            anomalies.append({"id": item.get("id"), "reason": "negative_count"})
        cleaned.append(value)
    return cleaned, anomalies


def _clean_tool_result(result: Any) -> tuple[Any, list[dict[str, Any]]]:
    if isinstance(result, list) and result and "title" in result[0]:
        return clean_result_items(result, name_field="title")
    if isinstance(result, dict):
        for key in ("categories", "tags"):
            if isinstance(result.get(key), list):
                cleaned, anomalies = clean_result_items(result[key], name_field="name")
                count_key = "category_count" if key == "categories" else "tag_count"
                return {**result, key: cleaned, count_key: len(cleaned)}, anomalies
    return result, []


def _normalize_terms(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = " ".join(str(value or "").split())
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        normalized.append(term)
    return normalized


def normalize_analysis_value(
    value: Mapping[str, Any] | Any,
    *,
    expected_post_id: str,
) -> dict[str, Any]:
    """Validate and normalize one generated result without implying persistence."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if not isinstance(value, Mapping):
        raise ValidationError(
            "Content analysis returned an invalid result",
            code="agent_analysis_result_invalid",
        )
    post_id = str(value.get("post_id") or "")
    if post_id != expected_post_id:
        raise ValidationError(
            "Content analysis returned a mismatched object id",
            code="agent_analysis_scope_mismatch",
        )
    return {
        "post_id": post_id,
        "tags": _normalize_terms(value.get("tags")),
        "keywords": _normalize_terms(value.get("keywords")),
        "summary": " ".join(str(value.get("summary") or "").split()),
        "save_status": "generated_not_saved",
    }


def analysis_run_count(
    *,
    object_count: int,
    selected_agent_count: int,
    max_concurrency: int,
) -> int:
    """Use one Agent for small work and bounded fan-out only when it has value."""
    if object_count <= 0:
        return 0
    if object_count >= 8:
        return min(object_count, max_concurrency)
    if selected_agent_count > 1:
        return min(object_count, selected_agent_count, max_concurrency)
    return 1


def _partition_ids(object_ids: Sequence[str], count: int) -> list[list[str]]:
    return [list(object_ids[index::count]) for index in range(count)] if count else []


def select_analysis_agents(
    bodies: Sequence[dict[str, Any]], request_text: str
) -> tuple[list[str], list[dict[str, str]]]:
    """Reuse the blog orchestrator's value/capability gates, not its prompt assembly."""
    from app.modules.posts import orchestrator
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    title = bodies[0].get("title") if len(bodies) == 1 else "批量文章内容分析"
    content = "\n\n".join(str(item.get("markdown") or "")[:4000] for item in bodies)[:50000]
    orchestration = orchestrator.build_plan(
        str(title or "文章内容分析"),
        content,
        instruction=request_text,
    )
    selected: list[str] = []
    for agent_key in orchestration.selected_agents:
        if agent_key not in {"editor-agent", "logic-agent", "data-agent"}:
            continue
        binding = resolve_builtin_agent(agent_key)
        if binding.enabled and agent_key not in selected:
            selected.append(agent_key)
    # An explicit content-analysis request still has value for short articles;
    # the existing Editor node is the minimum single Agent for that operation.
    if not selected:
        selected.append("editor-agent")
    return selected, orchestration.skipped_agents


def _analysis_reply(
    *,
    selected_agent_keys: Sequence[str],
    skipped_agents: Sequence[dict[str, str]],
    runs: Sequence[AgentRun],
    outcome: BatchOutcome,
    unprocessed_ids: Sequence[str],
    record_count: int,
    scope_notice: str | None = None,
) -> dict[str, Any]:
    generated = [result.value for result in outcome.succeeded]
    failed = [
        {
            "post_id": result.key,
            "reason": result.error or "分析失败",
            "error_code": result.error_code,
            "attempts": result.attempts,
        }
        for result in outcome.failed
    ]
    unique_tags = _normalize_terms([tag for item in generated for tag in item.get("tags", [])])
    unique_keywords = _normalize_terms(
        [keyword for item in generated for keyword in item.get("keywords", [])]
    )
    reply: dict[str, Any] = {
        "执行计划": {
            "selected_agents": list(selected_agent_keys),
            "skipped_agents": list(skipped_agents),
            "execution_mode": "parallel" if len(runs) > 1 else "single",
            "run_count": len(runs),
        },
        "当前运行 Agent": [
            {
                "agent_id": str(run.id),
                "agent_key": run.agent_key,
                "agent_version": run.agent_version,
                "status": run.status,
                "processed": run.progress_current,
                "total": run.progress_total,
            }
            for run in runs
        ],
        "执行结果": {
            "已生成未保存": generated,
            "已保存": [],
            "失败": failed,
            "未处理": [
                {"post_id": post_id, "reason": "对象不存在或无权访问"}
                for post_id in unprocessed_ids
            ],
            "质量检查": {
                "unique_tags": unique_tags,
                "unique_keywords": unique_keywords,
            },
        },
        "执行记录": {
            "total": record_count,
            "success": len(outcome.succeeded),
            "failed": len(outcome.failed),
        },
    }
    if scope_notice:
        reply["执行计划"]["scope_notice"] = scope_notice
    return reply


def execute_query_task(session: Session, task_id: uuid.UUID) -> AgentTask:
    """Execute one registered read intent and persist its audit/result state."""
    task = session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    plan = dispatch_intent(task.intent_key, task.request_text)
    if not isinstance(plan, IntentPlan):
        raise ValidationError("Intent produced an invalid plan", code="agent_intent_plan_invalid")
    if plan.tool_name == "posts.list_recent":
        # Parameter defaults come from the active user Skill.  The optional
        # model-proposed value was bounded at the conversation policy boundary.
        from app.modules.ai_config.service import resolve

        config = resolve(session, task.user_id, "conversation_route")
        params = dict(config.tool_defaults.get("posts.list_recent", {}))
        requested = task.scope_json.get("tool_parameters", {})
        if isinstance(requested, Mapping):
            params.update(requested)
        limit = params.get("limit", 10)
        if not isinstance(limit, int) or isinstance(limit, bool):
            limit = 10
        plan = IntentPlan(tool_name=plan.tool_name, params={"limit": min(max(limit, 1), 100)})
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    binding = resolve_builtin_agent("article-query-agent")
    now = datetime.now(UTC)
    run = AgentRun(
        task_id=task.id,
        agent_key=binding.agent_key,
        agent_version=binding.version_ref,
        agent_name=binding.agent_name,
        responsibility=binding.responsibility,
        current_task=task.request_text,
        allowed_tools=[plan.tool_name],
        status="running",
        current_tool=plan.tool_name,
        stage_label="正在查询必要数据",
        started_at=now,
    )
    session.add(run)
    task.status = "running"
    jobs_service.transition(
        session,
        task.job,
        status="processing",
        progress=10,
        current_step="正在查询必要数据",
    )
    publish_status(session, task, run)
    session.flush()

    if plan.clarification_question:
        result: Any = plan.clarification_question
        anomalies: list[dict[str, Any]] = []
        record_status = "skipped"
        record_summary = "缺少必要的数量条件"
    else:
        result = tool_registry.invoke(
            plan.tool_name,
            context=ToolContext(
                user_id=task.user_id,
                task_id=task.id,
                run_id=run.id,
                session=session,
            ),
            params=plan.params,
        )
        result, anomalies = _clean_tool_result(result)
        record_status = "success"
        record_summary = f"返回 {len(result) if isinstance(result, list) else 1} 项"

    record = write_execution_record(
        session,
        task_id=task.id,
        run_id=run.id,
        step_id="query-1",
        agent_name=run.agent_name,
        step_label="获取完成请求所需的最小数据",
        tool_name=plan.tool_name,
        operation_type="query",
        params=plan.params,
        status=record_status,
        result_summary=record_summary,
        started_at=now,
    )
    reply: dict[str, Any] = {
        "处理结果": result,
        "执行记录": [
            {
                "step_id": record.step_id,
                "tool_name": record.tool_name,
                "status": record.status,
                "result_summary": record.result_summary,
            }
        ],
        "局限说明": {"异常数据": anomalies} if anomalies else None,
    }
    finished = datetime.now(UTC)
    task.result_summary = json.dumps(reply, ensure_ascii=False, separators=(",", ":"))
    task.status = "success"
    task.finished_at = finished
    if isinstance(result, list):
        object_ids = _scope_ids([item.get("id") for item in result if isinstance(item, Mapping)])
        task.scope_json = {
            **task.scope_json,
            "object_ids": object_ids,
            "object_versions": _current_post_versions(session, task.user_id, object_ids),
            "query_conditions": dict(plan.params),
            "query_range": {
                "returned": len(object_ids),
                "limit": plan.params.get("limit"),
            },
            "sort": "updated_desc",
            "confirmed_operations": [],
            "pending_write_ids": [],
            "completed_object_ids": [],
            "failed_object_ids": [],
            "valid": True,
            "scope_refreshed": False,
            "refresh_notice": None,
        }
    run.status = "success" if record_status == "success" else "skipped"
    run.current_tool = None
    run.stage_label = "查询完成"
    run.result_summary = record_summary
    run.finished_at = finished
    jobs_service.transition(
        session,
        task.job,
        status="completed",
        progress=100,
        current_step="查询完成",
        result={"agent_task_id": str(task.id)},
    )
    publish_status(session, task, run)
    session.flush()
    return task


def _complete_already_processed_scope(session: Session, task: AgentTask) -> AgentTask:
    """Finish a repeated follow-up without invoking tools for completed objects."""
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    now = datetime.now(UTC)
    binding = resolve_builtin_agent("coordinator-agent")
    run = AgentRun(
        task_id=task.id,
        agent_key=binding.agent_key,
        agent_version=binding.version_ref,
        agent_name=binding.agent_name,
        responsibility=binding.responsibility,
        current_task=task.request_text,
        input_scope_json={"object_ids": []},
        allowed_tools=[],
        status="skipped",
        stage_label="已跳过重复步骤",
        result_summary="上一轮对象均已成功处理，本次未重复执行",
        started_at=now,
        finished_at=now,
    )
    session.add(run)
    session.flush()
    record = write_execution_record(
        session,
        task_id=task.id,
        run_id=run.id,
        step_id=None,
        agent_name=run.agent_name,
        step_label="检查上一轮已完成对象",
        tool_name="scope.completed",
        operation_type="analyze",
        params={"completed_object_ids": task.scope_json.get("completed_object_ids", [])},
        status="skipped",
        result_summary=run.result_summary,
        started_at=now,
        finished_at=now,
    )
    task.status = "success"
    task.finished_at = now
    task.result_summary = json.dumps(
        {
            "执行计划": {"execution_mode": "none", "reason": run.result_summary},
            "当前运行 Agent": [],
            "执行结果": {"已生成未保存": [], "已保存": [], "失败": [], "未处理": []},
            "执行记录": {"total": 1, "skipped": 1, "step_id": record.step_id},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    jobs_service.transition(
        session,
        task.job,
        status="completed",
        progress=100,
        current_step="已跳过重复步骤",
        result={"agent_task_id": str(task.id), "status": "success"},
    )
    publish_status(session, task, run)
    session.flush()
    return task


def execute_analysis_task(
    session: Session,
    task_id: uuid.UUID,
    *,
    analyze_post: AnalysisCallable | None = None,
) -> AgentTask:
    """Read only the explicit scope, fan out pure analysis, then persist outcomes."""
    from app.core.config import get_settings
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    task = session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    all_scope_ids = _scope_ids(task.scope_json.get("object_ids"))
    if not all_scope_ids:
        raise ValidationError(
            "Analysis requires an explicit object scope",
            code="agent_analysis_scope_required",
        )
    raw_ids = remaining_scope_object_ids(task.scope_json)
    if not raw_ids:
        return _complete_already_processed_scope(session, task)
    try:
        object_ids = list(dict.fromkeys(str(uuid.UUID(str(value))) for value in raw_ids))
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Analysis scope contains an invalid object id",
            code="agent_analysis_scope_invalid",
        ) from exc
    settings = get_settings()
    enforce_batch_limit(len(object_ids), maximum=settings.agent_max_batch_objects)

    started = datetime.now(UTC)
    coordinator_binding = resolve_builtin_agent("coordinator-agent")
    coordinator = AgentRun(
        task_id=task.id,
        agent_key=coordinator_binding.agent_key,
        agent_version=coordinator_binding.version_ref,
        agent_name=coordinator_binding.agent_name,
        responsibility=coordinator_binding.responsibility,
        current_task=task.request_text,
        input_scope_json={"object_ids": object_ids},
        allowed_tools=["posts.read_body"],
        expected_output="汇总已生成未保存、已保存、失败与未处理对象",
        status="running",
        current_tool="posts.read_body",
        progress_current=0,
        progress_total=len(object_ids),
        stage_label="正在读取目标文章正文",
        started_at=started,
    )
    session.add(coordinator)
    task.status = "running"
    task.finished_at = None
    task.job.error_retryable = False
    jobs_service.transition(
        session,
        task.job,
        status="processing",
        progress=10,
        current_step="正在读取目标文章正文",
    )
    publish_status(session, task, coordinator)

    bodies = tool_registry.invoke(
        "posts.read_body",
        context=ToolContext(
            user_id=task.user_id,
            task_id=task.id,
            run_id=coordinator.id,
            session=session,
        ),
        params={"post_ids": object_ids},
    )
    body_by_id = {str(item["id"]): item for item in bodies}
    unprocessed_ids = [post_id for post_id in object_ids if post_id not in body_by_id]
    body_record = write_execution_record(
        session,
        task_id=task.id,
        run_id=coordinator.id,
        step_id=f"body-read-{coordinator.id.hex[:12]}",
        agent_name=coordinator.agent_name,
        step_label="按明确对象范围读取文章正文",
        tool_name="posts.read_body",
        operation_type="analyze",
        params={"post_ids": object_ids},
        status="success",
        result_summary=f"读取 {len(bodies)} 篇目标文章",
        started_at=started,
    )

    selected_agent_keys, skipped_agents = select_analysis_agents(bodies, task.request_text)
    run_count = analysis_run_count(
        object_count=len(bodies),
        selected_agent_count=len(selected_agent_keys),
        max_concurrency=settings.agent_max_concurrency,
    )
    shards = _partition_ids(list(body_by_id), run_count)
    child_runs: list[AgentRun] = []
    run_by_object_id: dict[str, AgentRun] = {}
    for index, shard in enumerate(shards):
        binding = resolve_builtin_agent(selected_agent_keys[index % len(selected_agent_keys)])
        run = AgentRun(
            task_id=task.id,
            parent_run_id=coordinator.id,
            agent_key=binding.agent_key,
            agent_version=binding.version_ref,
            agent_name=binding.agent_name,
            responsibility=binding.responsibility,
            current_task=task.request_text,
            input_scope_json={"object_ids": shard},
            allowed_tools=["content.extract_metadata"],
            expected_output="每篇文章的标签、关键词与摘要提案",
            status="running",
            current_tool="content.extract_metadata",
            progress_current=0,
            progress_total=len(shard),
            stage_label="正在并行分析文章",
            started_at=datetime.now(UTC),
        )
        session.add(run)
        session.flush()
        child_runs.append(run)
        for post_id in shard:
            run_by_object_id[post_id] = run
        publish_status(session, task, run)

    jobs_service.transition(
        session,
        task.job,
        progress=30,
        current_step="正在并行分析文章",
    )

    def default_analyzer(post: dict[str, str], request_text: str) -> Mapping[str, Any]:
        run = run_by_object_id[post["id"]]
        return tool_registry.invoke(
            "content.extract_metadata",
            context=ToolContext(
                user_id=task.user_id,
                task_id=task.id,
                run_id=run.id,
                session=session,
            ),
            params={"post": post, "instruction": request_text},
        )

    analyzer = analyze_post or default_analyzer
    items = [
        WorkItem(
            key=post_id,
            input_scope={
                "object_ids": [post_id],
                "run_id": str(run_by_object_id[post_id].id),
            },
        )
        for post_id in body_by_id
    ]

    def analyze_item(item: WorkItem) -> dict[str, Any]:
        value = analyzer(body_by_id[item.key], task.request_text)
        return normalize_analysis_value(value, expected_post_id=item.key)

    outcome = run_configured(items, analyze_item, retry_once=True)
    records = [body_record]
    results_by_run: dict[uuid.UUID, list[Any]] = {run.id: [] for run in child_runs}
    for index, result in enumerate(outcome.results, start=1):
        run = run_by_object_id[result.key]
        results_by_run[run.id].append(result)
        records.append(
            write_execution_record(
                session,
                task_id=task.id,
                run_id=run.id,
                step_id=f"analysis-{index}",
                agent_name=run.agent_name,
                step_label="分析单篇文章并生成结构化提案",
                tool_name="content.extract_metadata",
                operation_type="analyze",
                params={"post_id": result.key, "attempts": result.attempts},
                status=result.status,
                result_summary=(
                    "已生成结果，尚未保存" if result.status == "success" else "文章分析失败"
                ),
                error_reason=result.error,
            )
        )

    finished = datetime.now(UTC)
    for run in child_runs:
        run_results = results_by_run[run.id]
        success_count = sum(result.status == "success" for result in run_results)
        if success_count == len(run_results):
            run.status = "success"
        elif success_count:
            run.status = "partial_success"
        else:
            run.status = "failed"
        run.current_tool = None
        run.progress_current = len(run_results)
        run.stage_label = "分析完成" if run.status == "success" else "分析完成，存在失败项"
        run.result_summary = f"成功 {success_count}，失败 {len(run_results) - success_count}"
        failed_result = next(
            (result for result in run_results if result.status == "failed"),
            None,
        )
        run.error_message = failed_result.error if failed_result is not None else None
        run.finished_at = finished
        publish_status(session, task, run)

    if outcome.succeeded:
        terminal_status = "partial_success" if outcome.failed or unprocessed_ids else "success"
    else:
        terminal_status = "failed"
    reply = _analysis_reply(
        selected_agent_keys=selected_agent_keys,
        skipped_agents=skipped_agents,
        runs=child_runs,
        outcome=outcome,
        unprocessed_ids=unprocessed_ids,
        record_count=len(records),
        scope_notice=(
            str(task.scope_json.get("refresh_notice"))
            if task.scope_json.get("refresh_notice")
            else None
        ),
    )
    task.status = terminal_status
    task.result_summary = json.dumps(reply, ensure_ascii=False, separators=(",", ":"))
    task.finished_at = finished
    prior_completed = _scope_ids(task.scope_json.get("completed_object_ids"))
    prior_failed = _scope_ids(task.scope_json.get("failed_object_ids"))
    succeeded_ids = [result.key for result in outcome.succeeded]
    failed_ids = [result.key for result in outcome.failed]
    task.scope_json = {
        **task.scope_json,
        "completed_object_ids": list(dict.fromkeys([*prior_completed, *succeeded_ids])),
        "failed_object_ids": [
            object_id
            for object_id in dict.fromkeys([*prior_failed, *failed_ids])
            if object_id not in succeeded_ids
        ],
        "unprocessed_object_ids": unprocessed_ids,
        "retryable": any(result.retryable for result in outcome.failed),
    }
    coordinator.status = terminal_status
    coordinator.current_tool = None
    coordinator.progress_current = len(outcome.results)
    coordinator.stage_label = "汇总完成" if terminal_status != "failed" else "分析失败"
    coordinator.result_summary = (
        f"成功 {len(outcome.succeeded)}，失败 {len(outcome.failed)}，未处理 {len(unprocessed_ids)}"
    )
    coordinator.error_message = "全部目标分析失败" if terminal_status == "failed" else None
    coordinator.finished_at = finished
    if outcome.succeeded and _request_wants_write(task.request_text):
        from app.models.posts import Post

        succeeded_post_ids = [uuid.UUID(result.key) for result in outcome.succeeded]
        version_rows = session.execute(
            select(Post.id, Post.version).where(
                Post.user_id == task.user_id,
                Post.id.in_(succeeded_post_ids),
            )
        ).all()
        versions = {str(post_id): version for post_id, version in version_rows}
        changes = [
            {
                "post_id": result.key,
                "summary": result.value.get("summary"),
                "tags": result.value.get("tags", []),
                "keywords": result.value.get("keywords", []),
            }
            for result in outcome.succeeded
            if result.key in versions
        ]
        targets = [
            {"id": change["post_id"], "version": versions[change["post_id"]]} for change in changes
        ]
        pending, capability_message = prepare_pending_write(
            session,
            task=task,
            run=coordinator,
            operation_type="update",
            target_type="post",
            targets=targets,
            preview={
                "summary": "把已生成的标签、关键词与摘要写入目标文章",
                "scope": {"post_ids": [change["post_id"] for change in changes]},
                "changes": changes,
            },
            reversible=True,
            tool_name="posts.apply_analysis",
            original_request_confirmed=True,
        )
        reply["执行结果"]["写入说明"] = capability_message
        if pending is not None:
            reply["执行结果"]["待确认写入"] = {
                "confirmation_id": str(pending.id),
                "affected_count": pending.affected_count,
                "high_risk": pending.high_risk,
                "reversible": pending.reversible,
            }
            coordinator.result_summary = f"已生成 {len(changes)} 项，等待确认写入"
            task.result_summary = json.dumps(reply, ensure_ascii=False, separators=(",", ":"))
        else:
            reply["局限说明"] = {"写入能力": capability_message}
            task.result_summary = json.dumps(reply, ensure_ascii=False, separators=(",", ":"))
        session.flush()
        return task
    if terminal_status == "failed":
        retryable = any(result.retryable for result in outcome.failed)
        jobs_service.transition(
            session,
            task.job,
            status="failed",
            current_step="文章分析失败",
            error_code=("agent_dependency_unavailable" if retryable else "agent_analysis_failed"),
            error_message="目标文章未能生成有效分析结果",
            error_retryable=retryable,
        )
    else:
        jobs_service.transition(
            session,
            task.job,
            status="completed",
            progress=100,
            current_step="文章分析完成",
            result={"agent_task_id": str(task.id), "status": terminal_status},
        )
    publish_status(session, task, coordinator)
    session.flush()
    return task


def _requested_agent_key(request_text: str) -> str:
    normalized = request_text.casefold()
    if any(signal in normalized for signal in ("概念插画", "插画", "illustration")):
        return "illustration-agent"
    if any(signal in normalized for signal in ("场景图片", "实景图", "scene image")):
        return "scene-image-agent"
    return "unregistered-agent"


def build_capability_gap(
    request_text: str,
    inspection: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Describe unsupported work without claiming a missing capability executed."""
    agent_key = str(inspection.get("agent_key") or "unregistered-agent")
    reason = str(inspection.get("unavailable_reason") or "没有匹配的已注册能力")
    return {
        "缺失能力": [f"{agent_key}: {reason}"],
        "缺失接口/字段/权限": ["当前工具清单中没有完成该请求所需的可用接口或权限"],
        "可完成部分": ["可以记录请求、检查当前能力清单并明确说明能力边界"],
        "不可完成部分": [request_text],
        "建议补充项": [f"在 spec 006 中注册并启用 {agent_key}，再绑定完成该请求所需的工具"],
    }


def execute_capability_gap_task(session: Session, task_id: uuid.UUID) -> AgentTask:
    """Persist a truthful capability-gap result without invoking the requested work."""
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    task = session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    now = datetime.now(UTC)
    binding = resolve_builtin_agent("coordinator-agent")
    run = AgentRun(
        task_id=task.id,
        agent_key=binding.agent_key,
        agent_version=binding.version_ref,
        agent_name=binding.agent_name,
        responsibility=binding.responsibility,
        current_task=task.request_text,
        allowed_tools=["agent.capabilities"],
        status="running",
        current_tool="agent.capabilities",
        stage_label="正在检查可用能力",
        started_at=now,
    )
    session.add(run)
    task.status = "running"
    jobs_service.transition(
        session,
        task.job,
        status="processing",
        progress=50,
        current_step="正在检查可用能力",
    )
    session.flush()
    publish_status(session, task, run)
    requested_agent_key = _requested_agent_key(task.request_text)
    inspection = tool_registry.invoke(
        "agent.capabilities",
        context=ToolContext(
            user_id=task.user_id,
            task_id=task.id,
            run_id=run.id,
            session=session,
        ),
        params={"agent_key": requested_agent_key},
    )
    gap = build_capability_gap(task.request_text, inspection)
    finished = datetime.now(UTC)
    record = write_execution_record(
        session,
        task_id=task.id,
        run_id=run.id,
        step_id=None,
        agent_name=run.agent_name,
        step_label="检查 Agent 与工具清单",
        tool_name="agent.capabilities",
        operation_type="query",
        params={"agent_key": requested_agent_key},
        status="success",
        result_summary="已确认当前能力不足，未执行目标业务操作",
        started_at=now,
        finished_at=finished,
    )
    run.status = "partial_success"
    run.current_tool = None
    run.stage_label = "能力检查完成"
    run.result_summary = record.result_summary
    run.finished_at = finished
    task.status = "partial_success"
    task.finished_at = finished
    task.result_summary = json.dumps(
        {
            "能力缺口": gap,
            "执行记录": [
                {
                    "step_id": record.step_id,
                    "status": record.status,
                    "result_summary": record.result_summary,
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    task.scope_json = {
        **task.scope_json,
        "capability_gap": gap,
        "requested_agent_key": requested_agent_key,
    }
    jobs_service.transition(
        session,
        task.job,
        status="completed",
        progress=100,
        current_step="能力检查完成",
        result={"agent_task_id": str(task.id), "status": "partial_success"},
    )
    publish_status(session, task, run)
    session.flush()
    return task


def execute_assistant_compat_task(session: Session, task_id: uuid.UUID) -> AgentTask:
    from app.modules.assistant.service import complete_agent_task

    task = session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    complete_agent_task(session, task)
    return task


def execute_agent_task(session: Session, task_id: uuid.UUID) -> AgentTask:
    """Dispatch by extensible execution kind rather than hard-coded intent keys."""
    task = session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    plan = dispatch_intent(task.intent_key, task.request_text)
    if not isinstance(plan, IntentPlan):
        raise ValidationError("Intent produced an invalid plan", code="agent_intent_plan_invalid")
    executors: dict[str, Callable[[Session, uuid.UUID], AgentTask]] = {
        "query": execute_query_task,
        "analysis": execute_analysis_task,
        "capability_gap": execute_capability_gap_task,
        "assistant_compat": execute_assistant_compat_task,
    }
    executor = executors.get(plan.execution_kind)
    if executor is None:
        raise ValidationError(
            "Intent execution kind is unsupported",
            code="agent_intent_execution_unsupported",
        )
    return executor(session, task_id)
