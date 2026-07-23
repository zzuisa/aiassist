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
