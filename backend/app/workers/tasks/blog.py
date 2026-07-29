"""Blog generation/optimization worker: creates unapplied AI revisions.

The AI never overwrites the authored Markdown; it produces a candidate revision
that the user reviews as a diff and explicitly applies. Grounding uses only the
supplied, authorized source entities.
"""

from __future__ import annotations

import uuid

from app.core.observability import get_logger
from app.db.session import session_scope
from app.services.llm.base import ChatRequest, LLMError
from app.workers.celery_app import celery

log = get_logger("worker.blog")

_SYSTEM = (
    "你是个人博客写作助手。基于用户已有正文和授权来源生成或改写 Markdown。"
    "只输出 Markdown 正文，不要编造未提供的事实。"
)


def generate_revision(post_id: uuid.UUID, scenario: str, instruction: str | None) -> str:
    from app.modules.posts import service as post_service
    from app.services.llm.gateway import get_llm_gateway

    with session_scope() as s:
        from app.models.posts import Post

        post = s.get(Post, post_id)
        if post is None or post.deleted_at is not None:
            return "skipped"
        gateway = get_llm_gateway()
        prompt = (
            f"场景：{scenario}\n指令：{instruction or '优化这篇文章'}\n\n"
            f"现有正文：\n{post.markdown}"
        )
        try:
            result = gateway.chat(ChatRequest(scenario=scenario, system=_SYSTEM, user=prompt))
            markdown = result.text  # type: ignore[attr-defined]
        except LLMError as exc:
            log.warning("blog_generate_failed", post_id=str(post_id), error=exc.code)
            return "failed"
        post_service.create_ai_revision(
            s, post, markdown, change_summary=f"{scenario} 生成的改写建议"
        )
        return "ready"


@celery.task(name="app.workers.tasks.blog.generate", bind=True, max_retries=3)
def generate(self, post_id: str, scenario: str, instruction: str | None = None) -> str:  # type: ignore[no-untyped-def]
    return generate_revision(uuid.UUID(post_id), scenario, instruction)


# ---------------------------------------------------------------------------
# URL extraction (spec 005, US1, T039)
#
# Idempotent: keyed on the PostSource. The authored Post text is NEVER
# overwritten — extraction only fills the *source* fields (original_text,
# normalized_markdown, metadata). A partial result (e.g. size-truncated body) is
# stored with status='partial' so the user can still read and retry once.
# ---------------------------------------------------------------------------


def extract_source(source_id: uuid.UUID) -> str:
    from datetime import UTC, datetime

    from app.models.blog import PostSource
    from app.modules.posts.url_extractor import (
        UrlSecurityError,
        extract_article,
        fetch_url,
    )

    with session_scope() as s:
        src = s.get(PostSource, source_id)
        if src is None:
            return "skipped"
        # Already completed (idempotent replay) — do nothing.
        if src.status == "completed":
            return "skipped"
        if src.source_type != "url" or not src.original_url:
            src.status = "failed"
            src.error_code = "not_url_source"
            return "failed"

        src.status = "processing"
        src.fetched_at = datetime.now(UTC)
        s.flush()

        try:
            fetched = fetch_url(src.original_url)
        except UrlSecurityError as exc:
            src.status = "failed"
            src.error_code = exc.code
            src.error_message = str(exc)[:500]
            log.warning("blog_extract_rejected", source_id=str(source_id), code=exc.code)
            return "failed"

        try:
            article = extract_article(fetched.text, fetched.final_url)
        except Exception as exc:  # extraction library failure is non-fatal
            article = {"title": None, "text": None, "markdown": None, "author": None, "site": None}
            log.warning("blog_extract_parse_failed", source_id=str(source_id), error=str(exc)[:200])

        src.original_title = article.get("title")
        src.original_text = article.get("text")
        src.normalized_markdown = article.get("markdown")
        src.source_author = article.get("author")
        src.source_site = article.get("site")
        src.extracted_at = datetime.now(UTC)

        has_body = bool(article.get("markdown") or article.get("text"))
        if fetched.truncated or not has_body:
            src.status = "partial"
            src.error_code = "truncated" if fetched.truncated else "no_content_extracted"
        else:
            src.status = "completed"
            src.error_code = None
            src.error_message = None
        return src.status


@celery.task(
    name="app.workers.tasks.blog.extract",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def extract(self, source_id: str) -> str:  # type: ignore[no-untyped-def]
    return extract_source(uuid.UUID(source_id))


# ---------------------------------------------------------------------------
# AI optimization (spec 005, US3, T073/T074)
#
# Runs the fixed-binding pipeline: preprocess → recognize → generate (structured)
# → validate → save an UNAPPLIED candidate. The current article is never touched.
# Business stages are published as durable Job transitions; only valid or partial
# candidates persist. A cancellation request is honored at each checkpoint.
# ---------------------------------------------------------------------------

_OPT_SYSTEM = (
    "你是个人博客内容优化助手。基于给定正文与技能配置产出优化候选，"
    "不得编造事实，不得改动代码、命令、网址、数字、日期与引用等受保护内容。"
)


def _build_system(config: dict, optimization_type: str, instruction: str | None) -> str:
    goal = config.get("processing_goal", "")
    rules = []
    for key in ("content_rules", "title_rules", "summary_rules", "prohibitions"):
        for r in config.get(key, []) or []:
            rules.append(f"- {r}")
    parts = [_OPT_SYSTEM, f"优化类型：{optimization_type}", f"目标：{goal}"]
    if rules:
        parts.append("规则：\n" + "\n".join(rules))
    if instruction:
        parts.append(f"用户额外要求：{instruction}")
    return "\n\n".join(parts)


def _proposed_fields(result) -> list[str]:  # type: ignore[no-untyped-def]
    fields: list[str] = []
    for name in ("title", "subtitle", "summary", "markdown"):
        if getattr(result, name, None) is not None:
            fields.append(name)
    if getattr(result, "content_class_suggestion", None) is not None:
        fields.append("content_class")
    for key in (getattr(result, "structured_fields", {}) or {}):
        fields.append(f"structured_data.{key}")
    return fields


def _build_field_diff(post, result, classified: dict) -> dict:  # type: ignore[no-untyped-def]
    diff: dict = {}
    mapping = {
        "title": ("title", getattr(result, "title", None)),
        "subtitle": ("subtitle", getattr(result, "subtitle", None)),
        "summary": ("summary", getattr(result, "summary", None)),
        "markdown": ("markdown", getattr(result, "markdown", None)),
        "content_class": ("content_class", getattr(result, "content_class_suggestion", None)),
    }
    for field, cls in classified.items():
        if field.startswith("structured_data."):
            key = field.split(".", 1)[1]
            sf = (getattr(result, "structured_fields", {}) or {}).get(key)
            to_val = getattr(sf, "value", None) if sf else None
            diff[field] = {
                "from": (post.structured_data_json or {}).get(key),
                "to": to_val,
                "classification": cls,
            }
        elif field in mapping:
            attr, to_val = mapping[field]
            diff[field] = {
                "from": getattr(post, attr, None),
                "to": to_val,
                "classification": cls,
            }
    return diff


def optimize_run(
    run_id: uuid.UUID,
    scope: str,
    selected_fields: list[str],
    instruction: str | None,
) -> str:
    from app.models.blog import BlogSkillVersion, PostAIRun
    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.jobs import service as jobs_service
    from app.modules.posts import ai_service, field_policy, protected_content
    from app.services.llm.base import LLMError, StructuredRequest
    from app.services.llm.gateway import get_llm_gateway
    from app.services.llm.schemas import BlogOptimizationV1

    with session_scope() as s:
        run = s.get(PostAIRun, run_id)
        if run is None or run.outcome is not None:
            return "skipped"
        job = s.get(AsyncJob, run.async_job_id)
        post = s.get(Post, run.post_id)
        if job is None or post is None:
            ai_service.mark_run_failed(s, run, code="entity_missing")
            return "failed"

        # Cancellation checkpoint (pre-flight).
        if job.status == "cancelled" or job.cancel_requested_at is not None:
            ai_service.mark_run_failed(s, run, code="cancelled")
            return "cancelled"

        jobs_service.transition(s, job, status="processing", current_step="预处理", progress=10)

        skill_version = s.get(BlogSkillVersion, run.skill_version_id)
        config = (skill_version.config_json if skill_version else {}) or {}

        # Long-content strategy.
        max_chars = skill_version.max_content_chars if skill_version else 200_000
        strategy = skill_version.long_content_strategy if skill_version else "reject"
        body = post.markdown
        if len(body) > max_chars:
            if strategy == "reject":
                ai_service.mark_run_failed(s, run, code="content_too_long")
                jobs_service.transition(
                    s, job, status="failed", error_code="content_too_long",
                    error_message="内容超出技能允许长度", error_retryable=False,
                )
                return "failed"
            # chunk / summarize_then_process: MVP truncates to the ceiling.
            body = body[:max_chars]

        jobs_service.transition(s, job, current_step="内容识别", progress=35)

        # Cancellation checkpoint (before the expensive call).
        s.refresh(job)
        if job.cancel_requested_at is not None:
            ai_service.mark_run_failed(s, run, code="cancelled")
            return "cancelled"

        jobs_service.transition(s, job, current_step="生成候选", progress=55)
        system = _build_system(config, run.optimization_type, instruction)
        user = body if instruction is None else f"{body}\n\n[要求]{instruction}"
        try:
            result = get_llm_gateway().structured(
                StructuredRequest(
                    scenario="optimize_blog", system=system, user=user,
                    schema=BlogOptimizationV1,
                )
            )
        except LLMError as exc:
            ai_service.mark_run_failed(s, run, code=exc.code)
            jobs_service.transition(
                s, job, status="failed", error_code=exc.code,
                error_message="AI 生成失败", error_retryable=True,
            )
            log.warning("blog_optimize_failed", run_id=str(run_id), code=exc.code)
            return "failed"

        jobs_service.transition(s, job, current_step="结果校验", progress=80)

        candidate_md = result.markdown if result.markdown is not None else post.markdown
        changes = protected_content.compare(post.markdown, candidate_md)
        blocking = protected_content.has_blocking_change(changes)
        proposed = _proposed_fields(result)
        classified = field_policy.classify_candidate(
            run.field_policy_json or {}, proposed, blocking_markdown_change=blocking
        )
        rejected = [f for f, c in classified.items() if c == "rejected"]
        outcome = "partial" if (rejected or blocking) else "complete"
        validation = {
            "protected_changes": [c.as_warning() for c in changes],
            "field_classification": classified,
            "model_warnings": [w.model_dump(mode="json") for w in result.warnings],
            "rejected_fields": rejected,
        }
        field_diff = _build_field_diff(post, result, classified)

        ai_service.save_candidate(
            s, run, candidate_markdown=candidate_md, field_diff=field_diff,
            validation=validation, outcome=outcome,
        )
        jobs_service.transition(
            s, job, status="waiting_user", current_step="待审核", progress=100,
            result={"candidate_id": str(run.candidate_id), "outcome": outcome,
                    "rejected_fields": rejected},
        )
        _notify_optimization_done(s, run, post, outcome)
        return outcome


def _notify_optimization_done(session, run, post, outcome: str) -> None:  # type: ignore[no-untyped-def]
    """Completion notification — links only, never article content (T076)."""
    from app.models.notifications import Notification

    session.add(
        Notification(
            id=uuid.uuid4(),
            user_id=run.user_id,
            type="blog.optimization_ready",
            title="AI 优化完成" if outcome == "complete" else "AI 优化（部分）完成",
            body="有新的优化候选待审核。",
            entity_type="post",
            entity_id=post.id,
        )
    )


@celery.task(
    name="app.workers.tasks.blog.optimize",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def optimize(  # type: ignore[no-untyped-def]
    self, run_id: str, scope: str = "all",
    selected_fields: list[str] | None = None, instruction: str | None = None,
) -> str:
    return optimize_run(uuid.UUID(run_id), scope, selected_fields or [], instruction)
