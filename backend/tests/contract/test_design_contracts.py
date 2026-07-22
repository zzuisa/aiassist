"""Validate the design contracts: OpenAPI, AsyncAPI and all JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

pytestmark = [pytest.mark.contract]

CONTRACTS = Path(__file__).resolve().parents[3] / "specs/001-personal-life-os/contracts"


def test_openapi_is_valid_yaml_and_openapi_31() -> None:
    doc = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text())
    assert doc["openapi"].startswith("3.1")
    assert "/settings" in doc["paths"], "settings endpoint must exist (Phase 0 reconcile)"
    assert "/auth/login" in doc["paths"]
    assert "/events/jobs" in doc["paths"]


def test_openapi_all_refs_resolve() -> None:
    text = (CONTRACTS / "openapi.yaml").read_text()
    doc = yaml.safe_load(text)
    import re

    refs = set(re.findall(r"#/components/(\w+)/([A-Za-z0-9_]+)", text))
    for section, name in refs:
        assert name in doc["components"].get(section, {}), f"missing #/components/{section}/{name}"


def test_asyncapi_is_valid_yaml() -> None:
    doc = yaml.safe_load((CONTRACTS / "events.asyncapi.yaml").read_text())
    assert "asyncapi" in doc
    assert "channels" in doc


@pytest.mark.parametrize(
    "schema_file",
    ["voice-task.v1.json", "capture-analysis.v1.json", "schedule-preview.v1.json"],
)
def test_json_schemas_are_valid_draft_2020_12(schema_file: str) -> None:
    schema = json.loads((CONTRACTS / "schemas" / schema_file).read_text())
    # Raises SchemaError if the schema itself is malformed.
    Draft202012Validator.check_schema(schema)


def test_voice_task_schema_rejects_unknown_and_accepts_valid() -> None:
    schema = json.loads((CONTRACTS / "schemas/voice-task.v1.json").read_text())
    validator = Draft202012Validator(schema)
    valid = {
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
    assert list(validator.iter_errors(valid)) == []
    # Unknown field must be rejected (additionalProperties: false).
    invalid = dict(valid, surprise="nope")
    assert list(validator.iter_errors(invalid))
