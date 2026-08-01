"""Guard against drift between the blog AI/Skill Pydantic models and contracts.

The checked-in JSON Schema contracts under specs/005 are the design source; the
Pydantic models in ``app.services.llm.schemas`` are the implementation. This
test asserts (a) the contracts stay strict + well-formed, (b) the emitted model
schema does not drift from the contract's required/strictness policy, and
(c) the model actually accepts a well-formed candidate and rejects malformed
Provider output (missing required fields, unknown fields, bad enums/versions).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.llm.schemas import (
    BlogEnhancementResultV1,
    BlogOptimizationV1,
    BlogSkillConfigV1,
)
from pydantic import ValidationError

pytestmark = [pytest.mark.contract]

CONTRACTS = (
    Path(__file__).resolve().parents[3] / "specs/005-blog-content-management/contracts/schemas"
)

BLOG_SCHEMAS = [
    "blog-optimization.v1.json",
    "blog-skill-config.v1.json",
    "blog-enhancement.v1.json",
]


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


def _valid_optimization() -> dict:
    """A minimal, fully-populated blog-optimization.v1 candidate.

    Nullable fields carry ``None`` (meaning "unknown", not invented data);
    collections are empty. Every required field is present.
    """
    return {
        "schema_version": "blog-optimization.v1",
        "title": "整理后的标题",
        "subtitle": None,
        "summary": None,
        "markdown": "# 正文\n\n内容。",
        "content_class_suggestion": None,
        "content_type_suggestion": None,
        "category_suggestions": [],
        "tag_suggestions": [],
        "keyword_suggestions": [],
        "occurred_at": None,
        "location": None,
        "project": None,
        "source_summary": None,
        "structured_fields": {},
        "related_post_suggestions": [],
        "claims": [],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Contract shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("contract", BLOG_SCHEMAS)
def test_blog_contract_schema_is_strict_and_wellformed(contract):
    """Every checked-in blog schema forbids extra properties and lists required."""
    reference = _load(contract)
    assert reference.get("additionalProperties") is False, (
        f"{contract}: must forbid additionalProperties"
    )
    assert reference.get("type") == "object"
    assert reference.get("required"), f"{contract}: required set must be non-empty"
    props = set(reference.get("properties", {}))
    missing = set(reference["required"]) - props
    assert not missing, f"{contract}: required fields without properties: {missing}"


# ---------------------------------------------------------------------------
# Model ↔ contract drift
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "contract"),
    [
        (BlogOptimizationV1, "blog-optimization.v1.json"),
        (BlogSkillConfigV1, "blog-skill-config.v1.json"),
        (BlogEnhancementResultV1, "blog-enhancement.v1.json"),
    ],
)
def test_pydantic_matches_contract_required_and_strictness(model, contract):
    """The emitted model schema must match the contract's required set + strictness."""
    emitted = model.model_json_schema()
    reference = _load(contract)
    assert set(emitted["required"]) == set(reference["required"]), (
        f"{contract}: required fields drifted"
    )
    assert emitted.get("additionalProperties") is False
    assert reference.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Malformed Provider output
# ---------------------------------------------------------------------------


def test_valid_candidate_parses():
    model = BlogOptimizationV1.model_validate(_valid_optimization())
    assert model.schema_version == "blog-optimization.v1"


@pytest.mark.parametrize(
    "drop",
    ["schema_version", "title", "markdown", "structured_fields", "warnings"],
)
def test_missing_required_field_is_rejected(drop):
    payload = _valid_optimization()
    del payload[drop]
    with pytest.raises(ValidationError):
        BlogOptimizationV1.model_validate(payload)


def test_unknown_field_is_rejected():
    payload = _valid_optimization()
    payload["hallucinated_field"] = "surprise"
    with pytest.raises(ValidationError):
        BlogOptimizationV1.model_validate(payload)


def test_wrong_schema_version_is_rejected():
    payload = _valid_optimization()
    payload["schema_version"] = "blog-optimization.v2"
    with pytest.raises(ValidationError):
        BlogOptimizationV1.model_validate(payload)


def test_invalid_content_class_enum_is_rejected():
    payload = _valid_optimization()
    payload["content_class_suggestion"] = "definitely-not-a-content-class"
    with pytest.raises(ValidationError):
        BlogOptimizationV1.model_validate(payload)


def test_non_list_collection_is_rejected():
    payload = _valid_optimization()
    payload["tag_suggestions"] = {"not": "a list"}
    with pytest.raises(ValidationError):
        BlogOptimizationV1.model_validate(payload)


def test_orchestrator_envelope_is_strict_and_versioned():
    result = BlogEnhancementResultV1.model_validate(
        {
            "status": "optimized",
            "article_assessment": {
                "information_density": 2,
                "logical_complexity": 1,
                "data_richness": 0,
                "scene_relevance": 0,
                "visual_potential": 0,
                "rewrite_value": 2,
                "evidence_quality": 2,
            },
            "decision": {
                "should_optimize": True,
                "reason": "保留作者意图并进行局部润色",
                "selected_agents": ["editor-agent"],
                "skipped_agents": [],
            },
            "optimized_article": {
                "title": "标题",
                "summary": "摘要",
                "content_markdown": "正文",
            },
            "enhancements": [],
            "quality_report": {
                "author_intent_preserved": True,
                "unsupported_claims": [],
                "removed_low_value_enhancements": [],
                "warnings": [],
            },
            "usage": {
                "agents_called": 1,
                "skills_called": [],
                "visual_items_created": 0,
                "estimated_input_tokens": 10,
                "estimated_output_tokens": 10,
                "estimated_cost": 0,
            },
        }
    )
    assert result.optimized_article.content_markdown == "正文"
