"""Capture classification/tagging via strict LLM schema; store as suggestions."""

from __future__ import annotations

import uuid

from app.core.observability import get_logger
from app.db.session import session_scope
from app.services.llm.base import LLMError, StructuredRequest
from app.services.llm.gateway import get_llm_gateway
from app.services.llm.schemas import CaptureAnalysisV1
from app.workers.celery_app import celery

log = get_logger("worker.capture_ai")

_SYSTEM = (
    "你根据收藏的用户描述和识别文字，给出标题、分类、标签和不确定的物品属性建议。"
    "所有建议都是推测，缺失信息保持为空，不得编造。只输出符合 capture-analysis.v1 的 JSON。"
)


def analyze_capture(capture_id: uuid.UUID) -> str:
    from app.models.captures import Capture, CaptureAiTag
    from app.modules.captures import service as capture_service

    with session_scope() as s:
        capture = s.get(Capture, capture_id)
        if capture is None or capture.deleted_at is not None:
            return "skipped"
        user_text = "\n".join(
            filter(None, [capture.title_user, capture.description_user, capture.ocr_text])
        )
        try:
            analysis = get_llm_gateway().structured(
                StructuredRequest(
                    scenario="classify_capture",
                    system=_SYSTEM,
                    user=user_text or capture.type,
                    schema=CaptureAnalysisV1,
                )
            )
        except LLMError as exc:
            # AI failure never loses the capture; the original stays viewable.
            log.warning("capture_ai_failed", capture_id=str(capture_id), code=exc.code)
            if capture.processing_status not in ("ready", "needs_input"):
                capture.processing_status = "ready"
            return "failed"

        data = analysis.model_dump(mode="json")
        capture_service.apply_ai_suggestions(
            s, capture, data, confidence=analysis.category.confidence
        )
        # Persist AI tag suggestions (not accepted until the user accepts them).
        for tag in analysis.tags:
            s.add(
                CaptureAiTag(
                    id=uuid.uuid4(),
                    user_id=capture.user_id,
                    capture_id=capture_id,
                    tag_name=tag.name,
                    confidence=tag.confidence,
                )
            )
        return "ready"


@celery.task(name="app.workers.tasks.capture_ai.analyze", bind=True, max_retries=3)
def analyze(self, capture_id: str) -> str:  # type: ignore[no-untyped-def]
    return analyze_capture(uuid.UUID(capture_id))
