"""Durable Agent task lifecycle primitives."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.agent import AgentRun, AgentTask
from app.modules.agent.audit import write_execution_record
from app.modules.agent.intents import IntentPlan, dispatch_intent
from app.modules.agent.registry import ToolContext, tool_registry
from app.modules.agent.runner import BatchOutcome, WorkItem, enforce_batch_limit, run_configured
from app.modules.agent.status import publish_status
from app.modules.jobs import service as jobs_service

AnalysisCallable = Callable[[dict[str, str], str], Mapping[str, Any] | Any]


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
    return {
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


def execute_query_task(session: Session, task_id: uuid.UUID) -> AgentTask:
    """Execute one registered read intent and persist its audit/result state."""
    task = session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError("Agent task not found")
    plan = dispatch_intent(task.intent_key, task.request_text)
    if not isinstance(plan, IntentPlan):
        raise ValidationError("Intent produced an invalid plan", code="agent_intent_plan_invalid")
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
        task.scope_json = {**task.scope_json, "object_ids": [item["id"] for item in result]}
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
    raw_ids = task.scope_json.get("object_ids", [])
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValidationError(
            "Analysis requires an explicit object scope",
            code="agent_analysis_scope_required",
        )
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
    )
    task.status = terminal_status
    task.result_summary = json.dumps(reply, ensure_ascii=False, separators=(",", ":"))
    task.finished_at = finished
    task.scope_json = {
        **task.scope_json,
        "completed_object_ids": [result.key for result in outcome.succeeded],
        "failed_object_ids": [result.key for result in outcome.failed],
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
    }
    executor = executors.get(plan.execution_kind)
    if executor is None:
        raise ValidationError(
            "Intent execution kind is unsupported",
            code="agent_intent_execution_unsupported",
        )
    return executor(session, task_id)
