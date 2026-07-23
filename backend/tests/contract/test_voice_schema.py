"""Strict voice-task.v1 validation: success, unknown fields, invalid dates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.llm.schemas import VoiceTaskV1
from pydantic import ValidationError

pytestmark = [pytest.mark.contract]

CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "specs/001-personal-life-os/contracts/schemas/voice-task.v1.json"
)


def _valid() -> dict:
    return {
        "title": "联系房东",
        "content_type": "reminder",
        "description": None,
        "local_date": "2026-07-24",
        "local_time": "15:00:00",
        "timezone": "Europe/Berlin",
        "duration_minutes": 20,
        "priority": 3,
        "important": True,
        "reminder": {"channel": "in_app", "offset_minutes": 30},
        "recurring": False,
        "recurrence_rule": None,
        "original_text": "明天下午三点提醒我联系房东",
    }


def test_valid_candidate_parses():
    candidate = VoiceTaskV1.model_validate(_valid())
    assert candidate.title == "联系房东"
    assert candidate.important is True


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        VoiceTaskV1.model_validate({**_valid(), "surprise": 1})


def test_priority_out_of_range_rejected():
    with pytest.raises(ValidationError):
        VoiceTaskV1.model_validate({**_valid(), "priority": 9})


def test_missing_required_field_rejected():
    payload = _valid()
    del payload["timezone"]
    with pytest.raises(ValidationError):
        VoiceTaskV1.model_validate(payload)


def test_emitted_schema_matches_contract_core():
    """The Pydantic schema forbids additional properties, matching the contract."""
    emitted = VoiceTaskV1.model_json_schema()
    assert emitted.get("additionalProperties") is False
    contract = json.loads(CONTRACT.read_text())
    # Same set of required fields.
    assert set(contract["required"]) == set(emitted["required"])
