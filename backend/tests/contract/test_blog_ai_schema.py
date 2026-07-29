"""Guard against drift between the blog AI/Skill Pydantic models and contracts.

The checked-in JSON Schema contracts under specs/005 are the design source; the
Pydantic models in app.services.llm.schemas are the implementation. Until the
models land (T023) the model-drift parametrization is skipped, but the schemas
are always structurally validated so the contract-to-frontend path stays wired.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract]

CONTRACTS = (
    Path(__file__).resolve().parents[3]
    / "specs/005-blog-content-management/contracts/schemas"
)

BLOG_SCHEMAS = ["blog-optimization.v1.json", "blog-skill-config.v1.json"]


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


@pytest.mark.parametrize("contract", BLOG_SCHEMAS)
def test_blog_contract_schema_is_strict_and_wellformed(contract):
    """Every checked-in blog schema forbids extra properties and lists required."""
    reference = _load(contract)
    assert reference.get("additionalProperties") is False, (
        f"{contract}: must forbid additionalProperties"
    )
    assert reference.get("type") == "object"
    assert reference.get("required"), f"{contract}: required set must be non-empty"
    # Required fields must all be declared as properties.
    props = set(reference.get("properties", {}))
    missing = set(reference["required"]) - props
    assert not missing, f"{contract}: required fields without properties: {missing}"


@pytest.mark.parametrize(
    ("model_name", "contract"),
    [
        ("BlogOptimizationV1", "blog-optimization.v1.json"),
        ("BlogSkillConfigV1", "blog-skill-config.v1.json"),
    ],
)
def test_pydantic_matches_contract_required_and_strictness(model_name, contract):
    """Once T023 adds the models, their emitted schema must match the contract."""
    schemas = pytest.importorskip("app.services.llm.schemas")
    model = getattr(schemas, model_name, None)
    if model is None:
        pytest.skip(f"{model_name} not implemented yet (T023)")
    emitted = model.model_json_schema()
    reference = _load(contract)
    assert set(emitted["required"]) == set(reference["required"]), (
        f"{contract}: required fields drifted"
    )
    assert emitted.get("additionalProperties") is False
    assert reference.get("additionalProperties") is False
