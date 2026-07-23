"""Guard against drift between emitted Pydantic schemas and checked-in contracts.

The JSON Schema contracts under contracts/schemas are the design source; the
Pydantic models in app.services.llm.schemas are the implementation. This test
fails if required fields or additionalProperties policy diverge, catching drift
before it reaches the frontend generated types.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.llm.schemas import CaptureAnalysisV1, VoiceTaskV1

pytestmark = [pytest.mark.contract]

CONTRACTS = Path(__file__).resolve().parents[3] / "specs/001-personal-life-os/contracts/schemas"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


@pytest.mark.parametrize(
    ("model", "contract"),
    [
        (VoiceTaskV1, "voice-task.v1.json"),
        (CaptureAnalysisV1, "capture-analysis.v1.json"),
    ],
)
def test_pydantic_matches_contract_required_and_strictness(model, contract):
    emitted = model.model_json_schema()
    reference = _load(contract)
    # Same required set.
    assert set(emitted["required"]) == set(reference["required"]), (
        f"{contract}: required fields drifted"
    )
    # Both forbid additional properties.
    assert emitted.get("additionalProperties") is False
    assert reference.get("additionalProperties") is False


def test_openapi_types_generation_marker_present():
    """The frontend keeps a generated-types marker so drift is reviewable.

    Full codegen runs in CI; here we assert the placeholder module exists so the
    contract-to-frontend path is wired.
    """
    generated = Path(__file__).resolve().parents[3] / "frontend/src/api/generated/README.md"
    assert generated.exists(), "frontend/src/api/generated marker missing"
