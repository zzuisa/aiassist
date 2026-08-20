"""Deterministic, reconcilable Markdown reports for terminal Agent plans."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.agent import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentStepArtifact,
    AgentTaskReport,
)

TOTAL_KEYS = (
    "matched",
    "processed",
    "applied",
    "verified",
    "conflicted",
    "failed",
    "skipped",
    "unprocessed",
    "manual_review",
)


def _line(value: object) -> str:
    return " ".join(str(value or "").split())[:500]


def render_markdown(
    *,
    objective: str,
    executed_steps: list[dict[str, Any]],
    totals: dict[str, int],
    results: list[dict[str, Any]],
    verified_changes: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    unprocessed: list[dict[str, Any]],
    next_actions: list[str],
) -> str:
    parts = [f"# {_line(objective)}", "", "## 执行结果", ""]
    parts.append(
        "、".join(
            (
                f"匹配：{totals['matched']}",
                f"处理：{totals['processed']}",
                f"已应用：{totals['applied']}",
                f"已验证：{totals['verified']}",
                f"失败：{totals['failed']}",
                f"冲突：{totals['conflicted']}",
                f"未处理：{totals['unprocessed']}",
            )
        )
    )
    parts.extend(("", "## 执行计划", ""))
    for index, step in enumerate(executed_steps, start=1):
        parts.append(
            f"{index}. **{_line(step.get('title'))}** — {_line(step.get('status'))}"
            + (f"：{_line(step.get('summary'))}" if step.get("summary") else "")
        )
    if results:
        parts.extend(("", "## 查询结果", ""))
        for item in results[:1000]:
            title = _line(item.get("title") or item.get("id") or "未命名对象")
            link = str(item.get("link") or "")
            tags = item.get("tags")
            suffix = (
                f"（标签：{'、'.join(map(str, tags))}）"
                if isinstance(tags, list) and tags
                else "（无标签）"
            )
            parts.append(
                f"- [{title}]({link}) {suffix}" if link.startswith("/") else f"- {title} {suffix}"
            )
    for heading, items in (
        ("已验证变更", verified_changes),
        ("冲突", conflicts),
        ("失败", failures),
        ("跳过", skipped),
        ("未处理", unprocessed),
    ):
        if not items:
            continue
        parts.extend(("", f"## {heading}", ""))
        parts.extend(
            f"- {_line(item.get('title') or item.get('object_id') or item)}" for item in items
        )
    if next_actions:
        parts.extend(("", "## 后续建议", ""))
        parts.extend(f"- {_line(item)}" for item in next_actions[:20])
    return "\n".join(parts).strip() + "\n"


def _result_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "posts", "structured_content"):
        nested = payload.get(key)
        found = _result_items(nested)
        if found:
            return found
    return []


def generate_report(session: Session, plan: AgentExecutionPlan) -> AgentTaskReport:
    steps = list(
        session.scalars(
            select(AgentPlanStep)
            .where(AgentPlanStep.plan_id == plan.id)
            .order_by(AgentPlanStep.position)
        ).all()
    )
    artifacts = list(
        session.scalars(
            select(AgentStepArtifact)
            .where(AgentStepArtifact.plan_id == plan.id)
            .order_by(AgentStepArtifact.created_at, AgentStepArtifact.id)
        ).all()
    )
    results: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.artifact_type == "tool_result":
            results.extend(_result_items(artifact.payload_json))
    results = list(
        {
            str(item.get("id") or item.get("post_id") or index): item
            for index, item in enumerate(results)
        }.values()
    )
    analysis_items = [
        item
        for artifact in artifacts
        if artifact.artifact_type == "analysis_proposals"
        for item in _result_items(artifact.payload_json)
    ]
    applied_items = [
        item
        for artifact in artifacts
        if artifact.artifact_type == "write_result"
        for item in _result_items(artifact.payload_json)
    ]
    verification_items = [
        item
        for artifact in artifacts
        if artifact.artifact_type == "verification_result"
        for item in _result_items(artifact.payload_json)
    ]
    verified_changes = [item for item in verification_items if item.get("verified")]
    conflicts = [item for item in verification_items if not item.get("verified")]
    failed_steps = [step for step in steps if step.status == "failed"]
    skipped_steps = [step for step in steps if step.status in {"blocked", "skipped", "cancelled"}]
    totals = {
        "matched": len(results),
        "processed": len(analysis_items),
        "applied": len(applied_items),
        "verified": len(verified_changes),
        "conflicted": len(conflicts),
        "failed": len(failed_steps),
        "skipped": len(skipped_steps),
        "unprocessed": plan.unprocessed_count,
        "manual_review": plan.waiting_count,
    }
    executed_steps = [
        {
            "step_key": step.step_key,
            "title": step.title,
            "status": step.status,
            "summary": step.result_summary,
        }
        for step in steps
    ]
    failures = [
        {"object_id": step.step_key, "title": step.title, "reason": step.error_message}
        for step in failed_steps
    ]
    skipped = [
        {"object_id": step.step_key, "title": step.title, "reason": step.error_message}
        for step in skipped_steps
    ]
    next_actions = ["检查回读失败的文章，解决并发修改后重试。"] if conflicts else []
    facts = {
        "objective": plan.objective,
        "executed_steps": executed_steps,
        "results": results,
        "verified_changes": verified_changes,
        "conflicts": conflicts,
        "failures": failures,
        "skipped": skipped,
        "unprocessed": [],
        "next_actions": next_actions,
    }
    source = json.dumps(
        {"totals": totals, "facts": facts},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    source_digest = hashlib.sha256(source.encode()).hexdigest()
    existing = session.scalar(
        select(AgentTaskReport).where(
            AgentTaskReport.plan_id == plan.id,
            AgentTaskReport.source_digest == source_digest,
            AgentTaskReport.status == "ready",
        )
    )
    if existing is not None:
        return existing
    revision = (
        int(
            session.scalar(
                select(func.coalesce(func.max(AgentTaskReport.revision), 0)).where(
                    AgentTaskReport.plan_id == plan.id
                )
            )
            or 0
        )
        + 1
    )
    markdown = render_markdown(
        objective=plan.objective,
        executed_steps=executed_steps,
        totals=totals,
        results=results,
        verified_changes=verified_changes,
        conflicts=conflicts,
        failures=failures,
        skipped=skipped,
        unprocessed=[],
        next_actions=next_actions,
    )
    report = AgentTaskReport(
        plan_id=plan.id,
        revision=revision,
        schema_version="task-report.v1",
        source_digest=source_digest,
        status="ready",
        totals_json=totals,
        facts_json=facts,
        markdown=markdown,
        short_summary=(plan.result_summary or f"任务完成，匹配 {len(results)} 项")[:1000],
        generation_method="deterministic",
        validation_status="valid",
    )
    session.add(report)
    session.flush()
    return report


def get_latest_owned_report(
    session: Session, *, user_id: uuid.UUID, plan_id: uuid.UUID
) -> AgentTaskReport:
    report = session.scalar(
        select(AgentTaskReport)
        .join(AgentExecutionPlan, AgentExecutionPlan.id == AgentTaskReport.plan_id)
        .where(
            AgentTaskReport.plan_id == plan_id,
            AgentTaskReport.status == "ready",
            AgentExecutionPlan.user_id == user_id,
        )
        .order_by(AgentTaskReport.revision.desc())
    )
    if report is None:
        raise NotFoundError("Agent report not found")
    return report


def regenerate_owned_report(
    session: Session, *, user_id: uuid.UUID, plan_id: uuid.UUID
) -> AgentTaskReport:
    plan = session.scalar(
        select(AgentExecutionPlan).where(
            AgentExecutionPlan.id == plan_id, AgentExecutionPlan.user_id == user_id
        )
    )
    if plan is None:
        raise NotFoundError("Agent plan not found")
    return generate_report(session, plan)


def report_payload(report: AgentTaskReport) -> dict[str, Any]:
    facts = report.facts_json
    markdown_digest = hashlib.sha256(report.markdown.encode()).hexdigest()
    return {
        "schema_version": "task-report.v1",
        "report_id": report.id,
        "plan_id": report.plan_id,
        "revision": report.revision,
        "source_digest": report.source_digest,
        "objective": facts.get("objective", ""),
        "executed_steps": facts.get("executed_steps", []),
        "totals": report.totals_json,
        "verified_changes": facts.get("verified_changes", []),
        "conflicts": facts.get("conflicts", []),
        "failures": facts.get("failures", []),
        "skipped": facts.get("skipped", []),
        "unprocessed": facts.get("unprocessed", []),
        "next_actions": facts.get("next_actions", []),
        "results": facts.get("results", []),
        "markdown": report.markdown,
        "report_digest": markdown_digest,
        "generation_method": report.generation_method,
        "generated_at": report.created_at.astimezone(UTC),
    }
