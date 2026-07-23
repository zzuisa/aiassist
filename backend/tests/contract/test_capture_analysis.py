"""Strict capture-analysis.v1: schema, confidence, provenance, no user overwrite."""

from __future__ import annotations

import pytest
from app.services.llm.schemas import CaptureAnalysisV1
from pydantic import ValidationError

pytestmark = [pytest.mark.contract]


def _valid() -> dict:
    return {
        "title": "厨房剪刀",
        "description": "不锈钢多功能厨房剪",
        "capture_type": "item",
        "category": {"name": "厨房工具", "confidence": 0.82},
        "tags": [{"name": "厨房", "confidence": 0.9}],
        "facts": [
            {
                "field": "material",
                "value": "不锈钢",
                "confidence": 0.7,
                "evidence_summary": "图像反光",
            }
        ],
        "needs_user_input": ["购买日期"],
    }


def test_valid_analysis_parses():
    analysis = CaptureAnalysisV1.model_validate(_valid())
    assert analysis.category.confidence == 0.82
    assert analysis.facts[0].field == "material"


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        CaptureAnalysisV1.model_validate({**_valid(), "extra": 1})


def test_confidence_out_of_range_rejected():
    payload = _valid()
    payload["category"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        CaptureAnalysisV1.model_validate(payload)


def test_invalid_fact_field_rejected():
    payload = _valid()
    payload["facts"][0]["field"] = "price"  # not an allowed fact field
    with pytest.raises(ValidationError):
        CaptureAnalysisV1.model_validate(payload)


def test_ai_suggestions_never_touch_user_columns():
    """apply_ai_suggestions writes only *_ai columns."""
    from app.models.captures import Capture
    from app.modules.captures import service

    capture = Capture(type="item", brand_user="用户品牌", title_user="用户标题")
    service.apply_ai_suggestions(
        None,  # type: ignore[arg-type]
        capture,
        {
            "title": "AI 标题",
            "description": "AI 描述",
            "facts": [{"field": "brand", "value": "AI 品牌", "confidence": 0.5}],
        },
        confidence=0.5,
    )
    assert capture.brand_user == "用户品牌"  # untouched
    assert capture.brand_ai == "AI 品牌"
    assert capture.title_user == "用户标题"
    assert capture.title_ai == "AI 标题"
