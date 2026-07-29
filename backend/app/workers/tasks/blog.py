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
