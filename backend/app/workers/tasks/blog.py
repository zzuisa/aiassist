"""Blog generation/optimization worker: creates unapplied AI revisions.

The AI never overwrites the authored Markdown; it produces a candidate revision
that the user reviews as a diff and explicitly applies. Grounding uses only the
supplied, authorized source entities.
"""

from __future__ import annotations

import uuid
from time import monotonic
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.observability import get_logger, set_trace_id
from app.db.session import session_scope
from app.models.blog import PostSource
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
def generate(self: Any, post_id: str, scenario: str, instruction: str | None = None) -> str:
    return generate_revision(uuid.UUID(post_id), scenario, instruction)


# ---------------------------------------------------------------------------
# URL extraction (spec 005, US1, T039)
#
# Idempotent: keyed on the PostSource. The authored Post text is NEVER
# overwritten — extraction only fills the *source* fields (original_text,
# normalized_markdown, metadata). A partial result (e.g. size-truncated body) is
# stored with status='partial' so the user can still read and retry once.
# ---------------------------------------------------------------------------


def _is_stub_body(markdown: str, url: str | None) -> bool:
    """True only when the body is exactly the bare ``<url>`` capture placeholder.

    A URL capture with no note seeds the body as ``<url>`` — pure placeholder, safe
    to replace with the extraction. A capture *with* a note seeds ``# note\\n\\n<url>``,
    which is user-authored and must never be overwritten.
    """
    return bool(url) and (markdown or "").strip() == f"<{url}>"


def _finish_parse(
    session: Session,
    src_row: PostSource,
    *,
    ok: bool,
    code: str | None = None,
    error_message: str = "链接抓取失败，可重试",
    error_retryable: bool = True,
) -> None:
    """Advance the pending_parse post + close the blog.parse job after extraction.

    On success, moves the article out of the transient ``pending_parse`` holding
    state and — when the body is still the capture placeholder — fills it with the
    extracted article content (recorded as an ``import`` revision). Genuinely
    authored bodies are never overwritten. A failed fetch still lands the article
    in triage with a retryable Job.
    """
    from datetime import UTC, datetime

    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.jobs import service as jobs_service
    from app.modules.posts import service as post_service

    post = session.get(Post, src_row.post_id) if src_row.post_id else None
    if post is not None and post.content_status == "pending_parse":
        post.content_status = "triage"
        # Prefer the extracted title when the post title is still the raw URL.
        if src_row.original_title and (post.title or "").strip() in (
            (src_row.original_url or "").strip(),
            "",
        ):
            post.title = src_row.original_title[:240]
        # Fill the article body from the extraction when it is still a placeholder.
        extracted = (src_row.normalized_markdown or src_row.original_text or "").strip()
        if ok and extracted and _is_stub_body(post.markdown, src_row.original_url):
            post.markdown = extracted
            rev = post_service.new_revision(
                session,
                post,
                extracted,
                "import",
                post.current_revision_id,
                change_summary="从链接导入正文",
            )
            rev.applied_at = datetime.now(UTC)
            post.current_revision_id = rev.id
            post.version += 1
    job = session.get(AsyncJob, src_row.async_job_id) if src_row.async_job_id else None
    if job is not None and job.status not in ("completed", "cancelled"):
        if ok:
            jobs_service.transition(
                session,
                job,
                status="completed",
                current_step="完成",
                progress=100,
            )
        else:
            jobs_service.transition(
                session,
                job,
                status="failed",
                error_code=code or "extract_failed",
                error_message=error_message,
                error_retryable=error_retryable,
            )


def extract_source(source_id: uuid.UUID) -> str:
    from datetime import UTC, datetime

    from app.models.blog import PostSource
    from app.models.foundation import AsyncJob
    from app.modules.jobs import service as jobs_service
    from app.modules.posts.url_extractor import (
        UrlSecurityError,
        extract_article,
        fetch_url,
    )

    set_trace_id(None)
    with session_scope() as s:
        src = s.get(PostSource, source_id)
        if src is None:
            log.warning("blog_extract_source_missing", source_id=str(source_id))
            return "skipped"
        job = s.get(AsyncJob, src.async_job_id) if src.async_job_id else None
        set_trace_id(job.trace_id if job is not None else None)
        fields = {
            "source_id": str(source_id),
            "post_id": str(src.post_id),
            "job_id": str(job.id) if job is not None else None,
        }
        if job is not None and job.status == "cancelled":
            log.info("blog_extract_skipped_cancelled", **fields)
            return "skipped"
        # A replay may need to repair the Job/article projection after an older
        # worker completed the source but crashed before closing the Job.
        if src.status == "completed":
            _finish_parse(s, src, ok=True)
            log.info("blog_extract_reconciled", **fields)
            return "skipped"
        if src.source_type != "url" or not src.original_url:
            src.status = "failed"
            src.error_code = "not_url_source"
            _finish_parse(s, src, ok=False, code="not_url_source")
            log.warning("blog_extract_rejected", code="not_url_source", **fields)
            return "failed"

        if job is not None and job.status not in ("processing", "completed"):
            jobs_service.transition(
                s,
                job,
                status="processing",
                current_step="抓取网页",
                progress=10,
            )
        src.status = "processing"
        src.fetched_at = datetime.now(UTC)
        s.flush()
        started = monotonic()
        log.info("blog_extract_started", **fields)

        try:
            fetched = fetch_url(src.original_url)
        except UrlSecurityError as exc:
            src.status = "failed"
            src.error_code = exc.code
            src.error_message = str(exc)[:500]
            log.warning("blog_extract_rejected", code=exc.code, **fields)
            _finish_parse(s, src, ok=False, code=exc.code)
            return "failed"

        try:
            article = extract_article(fetched.text, fetched.final_url)
        except Exception as exc:  # extraction library failure is non-fatal
            article = {"title": None, "text": None, "markdown": None, "author": None, "site": None}
            log.warning("blog_extract_parse_failed", error_type=type(exc).__name__, **fields)

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
        # The parse operation finished (content availability is a source concern);
        # advance the article to triage and complete the Job either way.
        _finish_parse(s, src, ok=True)
        log.info(
            "blog_extract_finished",
            source_status=src.status,
            error_code=src.error_code,
            http_status=fetched.status_code,
            redirect_count=max(0, len(fetched.redirect_chain) - 1),
            truncated=fetched.truncated,
            text_chars=len(src.original_text or ""),
            markdown_chars=len(src.normalized_markdown or ""),
            duration_ms=round((monotonic() - started) * 1000),
            **fields,
        )
        return src.status


@celery.task(
    name="app.workers.tasks.blog.extract",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def extract(self: Any, source_id: str) -> str:
    return extract_source(uuid.UUID(source_id))


# ---------------------------------------------------------------------------
# Bilibili import through the existing Radio service.
#
# One invocation performs one bounded remote operation.  Pending Radio tasks
# are polled through Celery retry messages, so the single heavy worker slot is
# not held while Whisper may run for hours.  Durable state stays on PostSource.
# ---------------------------------------------------------------------------


def _radio_task_failure(error: str | None) -> tuple[str, str, bool]:
    normalized = (error or "").lower()
    if any(
        marker in normalized
        for marker in ("无法获取视频信息", "视频下载失败", "链接", "login", "访问限制")
    ):
        return (
            "BILIBILI_LINK_UNAVAILABLE",
            "无法解析该 B 站链接，视频可能已失效、需要登录或存在访问限制。",
            False,
        )
    return "RADIO_TRANSCRIPTION_FAILED", "音视频转写失败，请稍后重试。", True


def _fail_radio_import(
    session: Session,
    source: PostSource,
    *,
    code: str,
    message: str,
    retryable: bool,
    diagnostic: str,
) -> str:
    source.status = "failed"
    source.error_code = code
    source.error_message = message
    _finish_parse(
        session,
        source,
        ok=False,
        code=code,
        error_message=message,
        error_retryable=retryable,
    )
    log.warning(
        "blog_bilibili_import_failed",
        source_id=str(source.id),
        post_id=str(source.post_id),
        job_id=str(source.async_job_id) if source.async_job_id else None,
        error_code=code,
        diagnostic=diagnostic,
        external_task_id=source.external_task_id,
    )
    return "failed"


def import_bilibili_source(source_id: uuid.UUID) -> str:
    """Advance one Radio submit/poll/finalize step for a Bilibili source."""
    from datetime import UTC, datetime

    from app.models.blog import PostSource
    from app.models.foundation import AsyncJob
    from app.modules.jobs import service as jobs_service
    from app.services.radio import RadioServiceError, get_radio_client

    set_trace_id(None)
    with session_scope() as session:
        source = session.get(PostSource, source_id)
        if source is None:
            log.warning("blog_bilibili_source_missing", source_id=str(source_id))
            return "skipped"
        job = session.get(AsyncJob, source.async_job_id) if source.async_job_id else None
        set_trace_id(job.trace_id if job is not None else None)
        if job is not None and job.status == "cancelled":
            source.status = "cancelled"
            return "cancelled"
        if source.status == "completed":
            _finish_parse(session, source, ok=True)
            return "completed"
        if (source.metadata_json or {}).get("url_type") != "bilibili" or not source.original_url:
            return _fail_radio_import(
                session,
                source,
                code="INVALID_BILIBILI_URL",
                message="B站链接格式不正确。",
                retryable=False,
                diagnostic="source_type_mismatch",
            )

        from app.core.config import get_settings

        settings = get_settings()
        age_seconds = (datetime.now(UTC) - source.created_at).total_seconds()
        if age_seconds > settings.radio_service_max_wait_seconds:
            return _fail_radio_import(
                session,
                source,
                code="RADIO_TRANSCRIPTION_TIMEOUT",
                message="B站音视频转写超时，请稍后重试。",
                retryable=True,
                diagnostic="max_wait_exceeded",
            )

        if job is not None and job.status not in {"processing", "completed"}:
            jobs_service.transition(
                session, job, status="processing", current_step="提交 B站转写", progress=5
            )
        source.status = "processing"
        source.fetched_at = source.fetched_at or datetime.now(UTC)

        try:
            client = get_radio_client()
            if not source.external_task_id:
                source.external_task_id = client.submit_bilibili_transcription(source.original_url)
                if job is not None:
                    jobs_service.transition(
                        session, job, current_step="等待音视频处理", progress=10
                    )
                log.info(
                    "blog_bilibili_radio_task_submitted",
                    source_id=str(source.id),
                    post_id=str(source.post_id),
                    job_id=str(job.id) if job else None,
                    external_task_id=source.external_task_id,
                )
                return "polling"
            radio_task = client.get_task(source.external_task_id)
        except RadioServiceError as exc:
            return _fail_radio_import(
                session,
                source,
                code=exc.code,
                message=exc.public_message,
                retryable=exc.retryable,
                diagnostic=exc.diagnostic,
            )

        if radio_task.status in {"queued", "running"}:
            if job is not None:
                # Reserve the final 10% for validating and saving the blog.
                progress = max(10, min(90, int(radio_task.progress * 0.85)))
                jobs_service.transition(
                    session,
                    job,
                    current_step="音视频转写中",
                    progress=progress,
                )
            return "polling"
        if radio_task.status == "failed":
            code, message, retryable = _radio_task_failure(radio_task.error)
            return _fail_radio_import(
                session,
                source,
                code=code,
                message=message,
                retryable=retryable,
                diagnostic="radio_task_failed",
            )
        if radio_task.status != "success" or not radio_task.result:
            return _fail_radio_import(
                session,
                source,
                code="RADIO_SERVICE_UNAVAILABLE",
                message="B站音视频处理服务当前不可用，请稍后重试。",
                retryable=True,
                diagnostic="task_unknown_status",
            )

        result = radio_task.result
        video_info = result.get("video_info")
        text = result.get("text")
        record_id = result.get("transcript_id")
        if not isinstance(video_info, dict) or not isinstance(record_id, str):
            return _fail_radio_import(
                session,
                source,
                code="RADIO_SERVICE_UNAVAILABLE",
                message="B站音视频处理服务当前不可用，请稍后重试。",
                retryable=True,
                diagnostic="task_result_invalid",
            )
        transcript = text.strip() if isinstance(text, str) else ""
        if not transcript:
            return _fail_radio_import(
                session,
                source,
                code="RADIO_EMPTY_TRANSCRIPT",
                message="音视频转写失败，未获得可用正文。",
                retryable=True,
                diagnostic="empty_transcript",
            )

        title = str(video_info.get("title") or "B站转写记录")[:240]
        source.original_title = title
        source.original_text = transcript
        source.normalized_markdown = transcript
        source.source_site = "Bilibili"
        source.external_record_id = record_id.strip()
        source.extracted_at = datetime.now(UTC)
        source.status = "completed"
        source.error_code = None
        source.error_message = None
        source.metadata_json = {
            **(source.metadata_json or {}),
            "bvid": video_info.get("bvid"),
            "radio_task_id": radio_task.id,
        }
        _finish_parse(session, source, ok=True)
        log.info(
            "blog_bilibili_import_completed",
            source_id=str(source.id),
            post_id=str(source.post_id),
            job_id=str(job.id) if job else None,
            external_task_id=radio_task.id,
            external_record_id=source.external_record_id,
            text_chars=len(transcript),
        )
        return "completed"


@celery.task(
    name="app.workers.tasks.blog.import_bilibili",
    bind=True,
    max_retries=8640,
    acks_late=True,
)
def import_bilibili(self, source_id: str) -> str:  # type: ignore[no-untyped-def]
    state = import_bilibili_source(uuid.UUID(source_id))
    if state == "polling":
        from app.core.config import get_settings

        # The project-wide Celery annotation caps ordinary retries at five and
        # overrides decorator attributes. Pass this task's bounded six-hour
        # polling budget explicitly so long Radio jobs keep being observed.
        raise self.retry(
            countdown=get_settings().radio_service_poll_interval_seconds,
            max_retries=8640,
        )
    return state


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


def _build_system(
    config: dict,
    optimization_type: str,
    instruction: str | None,
    *,
    scope: str = "all",
) -> str:
    goal = config.get("processing_goal", "")
    rules = []
    rule_keys = (
        ("content_rules", "prohibitions")
        if scope == "body"
        else ("content_rules", "title_rules", "summary_rules", "prohibitions")
    )
    for key in rule_keys:
        for r in config.get(key, []) or []:
            rules.append(f"- {r}")
    parts = [_OPT_SYSTEM, f"优化类型：{optimization_type}", f"目标：{goal}"]
    if scope == "body":
        parts.append("仅优化正文，并返回完整 Markdown；不要生成标题、摘要、分类或其他元数据。")
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
    for key in getattr(result, "structured_fields", {}) or {}:
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


def _normalize_orchestration_result(result, post):  # type: ignore[no-untyped-def]
    """Adapt the total-controller envelope to the existing candidate contract.

    Candidate review still consumes ``blog-optimization.v1``.  Keeping this
    adapter at the worker boundary lets existing Skills and test providers emit
    the legacy envelope while Qwen/DeepSeek receive the richer orchestrator
    schema.
    """

    from app.services.llm.schemas import BlogEnhancementResultV1, BlogOptimizationV1, BlogWarning

    if isinstance(result, BlogOptimizationV1):
        return result, None
    if not isinstance(result, BlogEnhancementResultV1):
        raise TypeError("unsupported blog optimization result")

    article = result.optimized_article
    warnings = [
        BlogWarning(
            code="other",
            field=None,
            message=warning,
            severity="warning",
        )
        for warning in result.quality_report.warnings[:20]
    ]
    return (
        BlogOptimizationV1(
            schema_version="blog-optimization.v1",
            title=article.title or None,
            subtitle=None,
            summary=article.summary or None,
            markdown=article.content_markdown or None,
            content_class_suggestion=None,
            content_type_suggestion=None,
            category_suggestions=[],
            tag_suggestions=[],
            keyword_suggestions=[],
            occurred_at=None,
            location=None,
            project=None,
            source_summary=None,
            structured_fields={},
            related_post_suggestions=[],
            claims=[],
            warnings=warnings,
        ),
        result.model_dump(mode="json"),
    )


def run_skill_test(
    job_id: uuid.UUID,
    skill_version_id: uuid.UUID,
    title: str,
    markdown: str,
    instruction: str | None,
) -> str:
    """Run one Skill against ephemeral text and persist only a validated Job result."""
    from app.models.blog import BlogSkillVersion
    from app.models.foundation import AsyncJob
    from app.modules.jobs import service as jobs_service
    from app.modules.posts import field_policy, protected_content
    from app.services.llm.base import LLMError, StructuredRequest
    from app.services.llm.gateway import get_llm_gateway
    from app.services.llm.schemas import BlogOptimizationV1

    with session_scope() as session:
        job = session.get(AsyncJob, job_id)
        version = session.get(BlogSkillVersion, skill_version_id)
        if job is None or job.job_type != "blog.skill_test":
            return "missing"
        set_trace_id(job.trace_id)
        if job.status in ("completed", "cancelled"):
            return "skipped"
        if version is None or version.user_id != job.user_id:
            jobs_service.transition(
                session,
                job,
                status="failed",
                error_code="skill_version_missing",
                error_message="技能版本不存在或不可用",
                error_retryable=False,
            )
            return "failed"

        config = version.config_json or {}
        jobs_service.transition(
            session, job, status="processing", current_step="正在执行技能测试", progress=20
        )
        session.commit()
        system = _build_system(config, "skill_test", instruction)
        user_payload = f"标题：{title}\n\n正文：\n{markdown}"
        try:
            result = get_llm_gateway().structured(
                StructuredRequest(
                    scenario="test_blog_skill",
                    system=system,
                    user=user_payload,
                    schema=BlogOptimizationV1,
                    max_tokens=get_settings().llm_max_output_tokens,
                )
            )
            # Test doubles and future providers still have to honor the declared
            # contract before their payload can become a user-visible result.
            if not isinstance(result, BlogOptimizationV1):
                result = BlogOptimizationV1.model_validate(result)
        except (LLMError, ValueError, TypeError) as exc:
            code = exc.code if isinstance(exc, LLMError) else "invalid_structured_output"
            jobs_service.transition(
                session,
                job,
                status="failed",
                error_code=code,
                error_message="技能测试失败：AI 返回内容未通过格式校验",
                error_retryable=isinstance(exc, LLMError) and exc.retryable,
            )
            log.warning("blog_skill_test_failed", job_id=str(job.id), code=code)
            return "failed"

        jobs_service.transition(session, job, current_step="正在校验测试结果", progress=80)
        session.commit()
        candidate_markdown = result.markdown if result.markdown is not None else markdown
        protected_changes = protected_content.compare(markdown, candidate_markdown)
        blocking = protected_content.has_blocking_change(protected_changes)
        proposed = _proposed_fields(result)
        classified = field_policy.classify_candidate(
            config.get("field_policies", {}), proposed, blocking_markdown_change=blocking
        )
        rejected = [field for field, state in classified.items() if state == "rejected"]
        outcome = "partial" if blocking or rejected else "complete"
        jobs_service.transition(
            session,
            job,
            status="completed",
            current_step="技能测试完成",
            progress=100,
            result={
                "context": {
                    "skill_id": str(version.skill_id),
                    "skill_version_id": str(version.id),
                    "skill_version": version.version_number,
                    "sample_title": title,
                },
                "outcome": outcome,
                "candidate": result.model_dump(mode="json"),
                "validation": {
                    "protected_changes": [c.as_warning() for c in protected_changes],
                    "field_classification": classified,
                    "rejected_fields": rejected,
                },
            },
        )
        log.info("blog_skill_test_completed", job_id=str(job.id), outcome=outcome)
        return outcome


@celery.task(
    name="app.workers.tasks.blog.skill_test",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def skill_test(  # type: ignore[no-untyped-def]
    self,
    job_id: str,
    skill_version_id: str,
    title: str,
    markdown: str,
    instruction: str | None = None,
) -> str:
    return run_skill_test(
        uuid.UUID(job_id), uuid.UUID(skill_version_id), title, markdown, instruction
    )


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
    from app.modules.posts.orchestrator import (
        build_default_reader_visual,
        build_plan,
        build_system_prompt,
        build_user_payload,
        has_embedded_visual,
    )
    from app.modules.posts.visuals import (
        execute_enhancement_items,
        execute_enhancements,
        insert_enhancements,
    )
    from app.services.llm.base import LLMError, StructuredRequest
    from app.services.llm.gateway import get_llm_gateway
    from app.services.llm.schemas import (
        BlogBodyOptimizationV1,
        BlogEnhancementResultV1,
        BlogEnhancementV1,
        BlogOptimizationV1,
    )

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

        jobs_service.transition(
            s, job, status="processing", current_step="正在准备文章", progress=10
        )
        # Each checkpoint is committed independently so the durable SSE stream
        # can expose real progress while the model call is still running.
        s.commit()

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
                    s,
                    job,
                    status="failed",
                    error_code="content_too_long",
                    error_message="内容超出技能允许长度",
                    error_retryable=False,
                )
                return "failed"
            # chunk / summarize_then_process: MVP truncates to the ceiling.
            body = body[:max_chars]

        jobs_service.transition(s, job, current_step="正在分析内容", progress=35)
        s.commit()

        # Cancellation checkpoint (before the expensive call).
        s.refresh(job)
        if job.cancel_requested_at is not None:
            ai_service.mark_run_failed(s, run, code="cancelled")
            return "cancelled"

        settings = get_settings()
        visual_options = {
            "allow_retrieved_images": settings.blog_allow_retrieved_images,
            "allow_generated_images": settings.blog_allow_generated_images,
        }
        orchestration_plan = build_plan(
            post.title, body, options=visual_options, instruction=instruction
        )
        provider_label = "Radio" if run.provider_key == "radio" else "AI Assist"
        jobs_service.transition(
            s,
            job,
            current_step=f"{provider_label} 正在生成优化内容",
            progress=55,
        )
        s.commit()
        system = (
            build_system_prompt(config, orchestration_plan, instruction)
            if scope != "body"
            else _build_system(config, run.optimization_type, instruction, scope=scope)
        )
        user = (
            build_user_payload(
                title=post.title,
                content=body,
                language=post.language,
                category=post.content_class,
                target_audience=None,
                author_intent=instruction,
                options={"allow_rewrite": scope != "metadata", **visual_options},
                skill_config=config,
                plan=orchestration_plan,
            )
            if scope != "body"
            else (body if instruction is None else f"{body}\n\n[要求]{instruction}")
        )
        result: BlogOptimizationV1 | BlogEnhancementResultV1
        if run.provider_key == "radio":
            from app.services.radio import RadioServiceError, get_radio_client

            try:
                optimized_markdown = get_radio_client().optimize_text(body, instruction=instruction)
            except RadioServiceError as exc:
                ai_service.mark_run_failed(s, run, code=exc.code)
                jobs_service.transition(
                    s,
                    job,
                    status="failed",
                    error_code=exc.code,
                    error_message=exc.public_message,
                    error_retryable=exc.retryable,
                )
                log.warning(
                    "blog_optimize_failed",
                    run_id=str(run_id),
                    provider_key=run.provider_key,
                    code=exc.code,
                    diagnostic=exc.diagnostic,
                )
                return "failed"
            result = BlogOptimizationV1(
                schema_version="blog-optimization.v1",
                title=None,
                subtitle=None,
                summary=None,
                markdown=optimized_markdown,
                content_class_suggestion=None,
                content_type_suggestion=None,
                category_suggestions=[],
                tag_suggestions=[],
                keyword_suggestions=[],
                occurred_at=None,
                location=None,
                project=None,
                source_summary=None,
                structured_fields={},
                related_post_suggestions=[],
                claims=[],
                warnings=[],
            )
        else:
            generation_started = monotonic()
            try:
                if scope == "body":
                    body_result = get_llm_gateway().structured(
                        StructuredRequest(
                            scenario="optimize_blog_body",
                            system=system,
                            user=user,
                            schema=BlogBodyOptimizationV1,
                            max_tokens=get_settings().llm_max_output_tokens,
                        )
                    )
                    result = BlogOptimizationV1(
                        schema_version="blog-optimization.v1",
                        title=None,
                        subtitle=None,
                        summary=None,
                        markdown=body_result.markdown,
                        content_class_suggestion=None,
                        content_type_suggestion=None,
                        category_suggestions=[],
                        tag_suggestions=[],
                        keyword_suggestions=[],
                        occurred_at=None,
                        location=None,
                        project=None,
                        source_summary=None,
                        structured_fields={},
                        related_post_suggestions=[],
                        claims=[],
                        warnings=[],
                    )
                else:
                    result = get_llm_gateway().structured(
                        StructuredRequest(
                            scenario="optimize_blog",
                            system=system,
                            user=user,
                            schema=BlogEnhancementResultV1,
                            max_tokens=get_settings().llm_max_output_tokens,
                        )
                    )
            except LLMError as exc:
                elapsed_seconds = round(monotonic() - generation_started, 2)
                settings = get_settings()
                public_message = {
                    "timeout": (
                        "AI Assist 生成超时"
                        f"（已等待 {settings.llm_read_timeout_seconds:g} 秒），"
                        "请重试、缩小优化范围或改用 Radio"
                    ),
                    "rate_limited": "AI Assist 当前请求较多，请稍后重试",
                    "provider_unavailable": "AI Assist 服务暂时不可用，请稍后重试",
                    "authentication_failed": "AI Assist 服务配置异常，请联系管理员",
                    "invalid_structured_output": "AI 返回内容格式异常，请重试或改用 Radio",
                }.get(exc.code, "AI Assist 生成失败，请稍后重试")
                ai_service.mark_run_failed(s, run, code=exc.code)
                jobs_service.transition(
                    s,
                    job,
                    status="failed",
                    error_code=exc.code,
                    error_message=public_message,
                    error_retryable=exc.retryable,
                )
                log.warning(
                    "blog_optimize_failed",
                    run_id=str(run_id),
                    post_id=str(post.id),
                    job_id=str(job.id),
                    provider_key=run.provider_key,
                    model_key=run.model_key,
                    configured_model=settings.llm_default_model,
                    code=exc.code,
                    diagnostic=exc.diagnostic,
                    elapsed_seconds=elapsed_seconds,
                    markdown_chars=len(body),
                    max_output_tokens=settings.llm_max_output_tokens,
                    timeout_seconds=settings.llm_read_timeout_seconds,
                )
                return "failed"

        jobs_service.transition(s, job, current_step="已收到结果，正在检查", progress=75)
        s.commit()

        jobs_service.transition(s, job, current_step="正在校验格式与受保护内容", progress=85)
        s.commit()

        orchestration_result = None
        visual_items: list[dict] = []
        jobs_service.transition(s, job, current_step="正在生成读者示意图", progress=90)
        s.commit()
        if isinstance(result, BlogEnhancementResultV1):
            existing_visual = has_embedded_visual(post.markdown)
            if existing_visual:
                for item in result.enhancements:
                    if item.capability == "visualize" and item.status == "executed":
                        item.status = "skipped"
                        item.reason = "文章已有 PNG 视觉资产，保留现有图示以避免重复"
            # The model is instructed to create a compact reader visual for
            # explainers, but the product promise must not depend on a model
            # remembering one optional field. Reuse only source-backed steps
            # when it omitted the visual; the normal visual validator and PNG
            # renderer remain the final safety gates.
            if (
                not existing_visual
                and orchestration_plan.reader_explainer
                and not any(
                    item.capability == "visualize" and item.status == "executed"
                    for item in result.enhancements
                )
            ):
                fallback = build_default_reader_visual(
                    post.title,
                    result.optimized_article.content_markdown or post.markdown,
                    orchestration_plan,
                )
                if fallback is None and result.optimized_article.content_markdown != post.markdown:
                    # A structure editor may turn Markdown headings/lists into
                    # bold prose. Preserve the visual promise by extracting
                    # source-backed nodes from the original article instead of
                    # depending on the model's formatting choices.
                    fallback = build_default_reader_visual(
                        post.title, post.markdown, orchestration_plan
                    )
                if fallback is not None:
                    result.enhancements.append(BlogEnhancementV1(**fallback))
            visual_items = execute_enhancements(
                result,
                max_visual_items=2,
                user_id=post.user_id,
                post_id=post.id,
            )
        elif scope in {"all", "body"} and not has_embedded_visual(post.markdown):
            # Radio and the body-only AI Assist path use the legacy text schema,
            # so they cannot return an enhancement envelope. Keep the visual
            # stage provider-neutral by rendering a source-backed compact PNG
            # from the shared diagnosis instead of requiring another prompt.
            visual_source = getattr(result, "markdown", None) or post.markdown
            fallback = build_default_reader_visual(post.title, visual_source, orchestration_plan)
            if fallback is None and visual_source != post.markdown:
                fallback = build_default_reader_visual(
                    post.title, post.markdown, orchestration_plan
                )
            if fallback is not None:
                visual_items = execute_enhancement_items(
                    [BlogEnhancementV1(**fallback)],
                    max_visual_items=1,
                    user_id=post.user_id,
                    post_id=post.id,
                )

        if visual_items:
            if isinstance(result, BlogEnhancementResultV1):
                result.optimized_article.content_markdown = insert_enhancements(
                    result.optimized_article.content_markdown,
                    visual_items,
                )
            else:
                result.markdown = insert_enhancements(
                    result.markdown or post.markdown, visual_items
                )
        normalized_result, orchestration_result = _normalize_orchestration_result(result, post)
        result = cast(BlogOptimizationV1, normalized_result)
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
            "orchestration_plan": orchestration_plan.as_dict(),
            "visual_enhancements": visual_items,
        }
        if orchestration_result is not None:
            validation["orchestration_result"] = {
                key: value
                for key, value in orchestration_result.items()
                if key != "optimized_article"
            }
        field_diff = _build_field_diff(post, result, classified)

        jobs_service.transition(s, job, current_step="正在保存优化候选", progress=95)
        s.commit()

        ai_service.save_candidate(
            s,
            run,
            candidate_markdown=candidate_md,
            field_diff=field_diff,
            validation=validation,
            outcome=outcome,
        )
        jobs_service.transition(
            s,
            job,
            status="waiting_user",
            current_step="待审核",
            progress=100,
            result={
                "candidate_id": str(run.candidate_id),
                "outcome": outcome,
                "rejected_fields": rejected,
            },
        )
        _notify_optimization_done(s, run, post, outcome)
        log.info(
            "blog_optimize_completed",
            run_id=str(run.id),
            post_id=str(post.id),
            job_id=str(job.id),
            provider_key=run.provider_key,
            outcome=outcome,
        )
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
    self,
    run_id: str,
    scope: str = "all",
    selected_fields: list[str] | None = None,
    instruction: str | None = None,
) -> str:
    return optimize_run(uuid.UUID(run_id), scope, selected_fields or [], instruction)


def run_taxonomy_merge(merge_id: uuid.UUID) -> str:
    from app.models.blog import TaxonomyMerge
    from app.models.foundation import AsyncJob
    from app.modules.jobs import service as jobs_service
    from app.modules.posts import taxonomy_service

    try:
        with session_scope() as session:
            audit = session.get(TaxonomyMerge, merge_id)
            if audit is None:
                return "missing"
            if audit.status == "completed":
                return "completed"
            job = session.get(AsyncJob, audit.async_job_id) if audit.async_job_id else None
            audit.error_summary = None
            if job:
                job.error_code = None
                job.error_message = None
                job.error_retryable = False
                jobs_service.transition(
                    session,
                    job,
                    status="processing",
                    progress=10,
                    current_step="正在合并组织项",
                )
            taxonomy_service.merge_items(
                session,
                audit.user_id,
                audit.kind,
                audit.source_id,
                audit.target_id,
                merge_id=audit.id,
            )
            if job:
                jobs_service.transition(
                    session,
                    job,
                    status="completed",
                    progress=100,
                    current_step="组织项合并完成",
                    result={"merge_id": str(audit.id)},
                )
    except Exception:
        with session_scope() as session:
            audit = session.get(TaxonomyMerge, merge_id)
            if audit:
                audit.status = "failed"
                audit.error_summary = "组织项合并失败，可安全重试"
                job = session.get(AsyncJob, audit.async_job_id) if audit.async_job_id else None
                if job:
                    jobs_service.transition(
                        session,
                        job,
                        status="failed",
                        error_code="taxonomy_merge_failed",
                        error_message="组织项合并失败，可安全重试",
                        error_retryable=True,
                    )
        raise
    return "completed"


@celery.task(name="app.workers.tasks.blog.taxonomy_merge", acks_late=True)
def taxonomy_merge(merge_id: str) -> str:
    return run_taxonomy_merge(uuid.UUID(merge_id))


def run_keyword_recompute(job_id: uuid.UUID, user_id: uuid.UUID) -> str:
    from sqlalchemy import delete, select

    from app.models.blog import PostKeyword, PostKeywordAlias, PostKeywordLink
    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.jobs import service as jobs_service

    try:
        with session_scope() as session:
            job = session.get(AsyncJob, job_id)
            if job is None or job.user_id != user_id:
                return "missing"
            if job.status == "completed":
                return "completed"
            job.error_code = None
            job.error_message = None
            job.error_retryable = False
            jobs_service.transition(
                session, job, status="processing", progress=10, current_step="正在重算关键词"
            )
            keywords = session.scalars(
                select(PostKeyword).where(
                    PostKeyword.user_id == user_id,
                    PostKeyword.enabled.is_(True),
                    PostKeyword.is_stop_word.is_(False),
                )
            ).all()
            alias_rows = session.execute(
                select(PostKeywordAlias.keyword_id, PostKeywordAlias.alias).where(
                    PostKeywordAlias.user_id == user_id
                )
            ).all()
            aliases_by_keyword: dict[uuid.UUID, list[str]] = {}
            for keyword_id, alias in alias_rows:
                aliases_by_keyword.setdefault(keyword_id, []).append(alias.casefold())
            posts = session.scalars(
                select(Post).where(Post.user_id == user_id, Post.deleted_at.is_(None))
            ).all()
            session.execute(
                delete(PostKeywordLink).where(
                    PostKeywordLink.user_id == user_id,
                    PostKeywordLink.source == "recomputed",
                )
            )
            existing = {
                (post_id, keyword_id)
                for post_id, keyword_id in session.execute(
                    select(PostKeywordLink.post_id, PostKeywordLink.keyword_id).where(
                        PostKeywordLink.user_id == user_id
                    )
                )
            }
            created = 0
            for post in posts:
                haystack = f"{post.title}\n{post.summary or ''}\n{post.markdown}".casefold()
                for keyword in keywords:
                    pair = (post.id, keyword.id)
                    names = [
                        keyword.canonical_text.casefold(),
                        *aliases_by_keyword.get(keyword.id, []),
                    ]
                    if pair not in existing and any(name in haystack for name in names):
                        session.add(
                            PostKeywordLink(
                                post_id=post.id,
                                keyword_id=keyword.id,
                                user_id=user_id,
                                source="recomputed",
                                weight=1,
                            )
                        )
                        existing.add(pair)
                        created += 1
            jobs_service.transition(
                session,
                job,
                status="completed",
                progress=100,
                current_step="关键词重算完成",
                result={"created_links": created},
            )
        return "completed"
    except Exception:
        with session_scope() as session:
            job = session.get(AsyncJob, job_id)
            if job:
                jobs_service.transition(
                    session,
                    job,
                    status="failed",
                    error_code="keyword_recompute_failed",
                    error_message="关键词重算失败，可安全重试",
                    error_retryable=True,
                )
        raise


@celery.task(name="app.workers.tasks.blog.keyword_recompute", acks_late=True)
def keyword_recompute(job_id: str, user_id: str) -> str:
    return run_keyword_recompute(uuid.UUID(job_id), uuid.UUID(user_id))


def run_wordcloud(snapshot_id: uuid.UUID, min_frequency: int, max_terms: int) -> str:
    from datetime import UTC, datetime

    from sqlalchemy import func, select

    from app.models.blog import (
        PostKeyword,
        PostKeywordLink,
        PostTagProfile,
        PostWordCloudSnapshot,
    )
    from app.models.foundation import AsyncJob, Tag
    from app.models.posts import Post, PostTag
    from app.modules.jobs import service as jobs_service
    from app.modules.posts import settings_service

    try:
        with session_scope() as session:
            snapshot = session.get(PostWordCloudSnapshot, snapshot_id)
            if snapshot is None:
                return "missing"
            job = session.get(AsyncJob, snapshot.async_job_id) if snapshot.async_job_id else None
            if job is None:
                return "missing"
            if job.status == "completed":
                return "completed"
            if job.status == "cancelled":
                return "cancelled"
            job.error_code = None
            job.error_message = None
            job.error_retryable = False
            jobs_service.transition(
                session, job, status="processing", progress=10, current_step="正在聚合词云"
            )

            filters = snapshot.filter_json or {}
            post_ids = select(Post.id).where(
                Post.user_id == snapshot.user_id,
                Post.deleted_at.is_(None),
                Post.content_status.notin_(("archived", "discarded")),
            )
            if filters.get("year"):
                post_ids = post_ids.where(
                    func.extract("year", func.coalesce(Post.occurred_at, Post.created_at))
                    == int(filters["year"])
                )
            if filters.get("month"):
                post_ids = post_ids.where(
                    func.extract("month", func.coalesce(Post.occurred_at, Post.created_at))
                    == int(filters["month"])
                )
            if filters.get("from"):
                post_ids = post_ids.where(
                    func.coalesce(Post.occurred_at, Post.created_at)
                    >= datetime.fromisoformat(str(filters["from"]).replace("Z", "+00:00"))
                )
            if filters.get("to"):
                post_ids = post_ids.where(
                    func.coalesce(Post.occurred_at, Post.created_at)
                    <= datetime.fromisoformat(str(filters["to"]).replace("Z", "+00:00"))
                )
            if filters.get("content_class"):
                post_ids = post_ids.where(Post.content_class == filters["content_class"])
            if filters.get("category_id"):
                post_ids = post_ids.where(Post.category_id == uuid.UUID(filters["category_id"]))

            settings = settings_service.settings_to_dict(
                settings_service.get_settings(session, snapshot.user_id)
            )["word_cloud"]
            excluded_classes = settings.get("excluded_content_classes", [])
            if excluded_classes:
                post_ids = post_ids.where(Post.content_class.notin_(excluded_classes))

            scoped_ids = post_ids.subquery()
            article_count = session.scalar(select(func.count()).select_from(scoped_ids)) or 0
            excluded = {str(term).casefold() for term in settings.get("exclude_terms", [])}
            if snapshot.source_kind == "tag":
                rows = session.execute(
                    select(Tag.id, Tag.name, func.count(func.distinct(PostTag.post_id)))
                    .join(PostTag, PostTag.tag_id == Tag.id)
                    .join(PostTagProfile, PostTagProfile.tag_id == Tag.id)
                    .where(
                        Tag.user_id == snapshot.user_id,
                        PostTag.user_id == snapshot.user_id,
                        PostTagProfile.enabled.is_(True),
                        PostTag.post_id.in_(select(scoped_ids.c.id)),
                    )
                    .group_by(Tag.id)
                ).all()
            else:
                rows = session.execute(
                    select(
                        PostKeyword.id,
                        PostKeyword.canonical_text,
                        func.count(func.distinct(PostKeywordLink.post_id)),
                    )
                    .join(PostKeywordLink, PostKeywordLink.keyword_id == PostKeyword.id)
                    .where(
                        PostKeyword.user_id == snapshot.user_id,
                        PostKeywordLink.user_id == snapshot.user_id,
                        PostKeyword.enabled.is_(True),
                        PostKeyword.is_stop_word.is_(False),
                        PostKeywordLink.post_id.in_(select(scoped_ids.c.id)),
                    )
                    .group_by(PostKeyword.id)
                ).all()
            terms = [
                {"id": str(term_id), "term": term, "count": int(count)}
                for term_id, term, count in rows
                if count >= min_frequency and term.casefold() not in excluded
            ]
            terms.sort(key=lambda item: (-item["count"], item["term"].casefold()))
            snapshot.terms_json = terms[:max_terms]
            snapshot.article_count = int(article_count)
            snapshot.status = "ready"
            snapshot.generated_at = datetime.now(UTC)
            snapshot.error_code = None
            jobs_service.transition(
                session,
                job,
                status="completed",
                progress=100,
                current_step="词云已更新",
                result={"snapshot_id": str(snapshot.id), "term_count": len(snapshot.terms_json)},
            )
        return "completed"
    except Exception:
        with session_scope() as session:
            snapshot = session.get(PostWordCloudSnapshot, snapshot_id)
            if snapshot:
                snapshot.status = "stale" if snapshot.terms_json else "failed"
                snapshot.error_code = "wordcloud_rebuild_failed"
                job = (
                    session.get(AsyncJob, snapshot.async_job_id) if snapshot.async_job_id else None
                )
                if job and job.status != "cancelled":
                    jobs_service.transition(
                        session,
                        job,
                        status="failed",
                        error_code="wordcloud_rebuild_failed",
                        error_message="词云重建失败，已保留上次结果",
                        error_retryable=True,
                    )
        raise


@celery.task(name="app.workers.tasks.blog.wordcloud", acks_late=True)
def wordcloud(snapshot_id: str, min_frequency: int, max_terms: int) -> str:
    return run_wordcloud(uuid.UUID(snapshot_id), min_frequency, max_terms)
