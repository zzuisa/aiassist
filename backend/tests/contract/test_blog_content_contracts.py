"""Contract parse + drift guards for spec 005 (T008).

Ensures the OpenAPI, AsyncAPI and JSON Schema artifacts under specs/005 parse
cleanly and stay structurally coherent, and that the checked-in JSON Schemas
agree with the strict Pydantic models that implement them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.contract]

SPEC_DIR = Path(__file__).resolve().parents[3] / "specs/005-blog-content-management/contracts"
SCHEMA_DIR = SPEC_DIR / "schemas"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def test_openapi_parses_and_declares_paths():
    doc = yaml.safe_load((SPEC_DIR / "openapi.yaml").read_text())
    assert isinstance(doc, dict)
    assert str(doc.get("openapi", "")).startswith("3."), "OpenAPI 3.x required"
    assert doc.get("paths"), "openapi.yaml must declare paths"


def test_openapi_operations_exist_in_runtime_application():
    """Every designed operation must still be mounted with the same method/path."""
    from app.main import app

    contract = yaml.safe_load((SPEC_DIR / "openapi.yaml").read_text())
    runtime = app.openapi()["paths"]
    missing: list[str] = []
    for path, path_item in contract["paths"].items():
        runtime_path = f"/api/v1{path}"
        actual_methods = set(runtime.get(runtime_path, {})) & HTTP_METHODS
        for method in set(path_item) & HTTP_METHODS:
            if method not in actual_methods:
                missing.append(f"{method.upper()} {runtime_path}")
    assert not missing, f"OpenAPI operations missing from runtime: {missing}"


def test_asyncapi_parses_and_declares_channels():
    doc = yaml.safe_load((SPEC_DIR / "events.asyncapi.yaml").read_text())
    assert isinstance(doc, dict)
    assert str(doc.get("asyncapi", "")).startswith("2.") or str(doc.get("asyncapi", "")).startswith(
        "3."
    ), "AsyncAPI 2.x/3.x required"
    assert doc.get("channels"), "asyncapi must declare channels"


def test_asyncapi_addresses_and_event_names_match_outbox_implementation():
    """Guard the durable event name and routing key pairs used at append sites."""
    doc = yaml.safe_load((SPEC_DIR / "events.asyncapi.yaml").read_text())
    expected = {
        "blogSourceExtract": ("blog.parse", "blog.parse"),
        "blogOptimize": ("blog.optimize", "blog.optimize"),
        "blogSearchRefresh": ("post.updated", "search.index.post.updated"),
        "blogKeywordRebuild": ("blog.keyword_recompute", "blog.keyword.recompute"),
        "blogWordCloudRebuild": ("blog.wordcloud", "blog.wordcloud.rebuild"),
    }
    source_root = Path(__file__).resolve().parents[2] / "app/modules/posts"
    implementation = "\n".join(path.read_text() for path in source_root.glob("*.py"))
    for channel_name, (event_type, routing_key) in expected.items():
        channel = doc["channels"][channel_name]
        assert channel["address"] == routing_key
        message_ref = next(iter(channel["messages"].values()))["$ref"]
        message_name = message_ref.rsplit("/", 1)[-1]
        assert doc["components"]["messages"][message_name]["name"] == event_type
        assert f'"{event_type}"' in implementation, f"Outbox event drifted: {event_type}"
        assert f'"{routing_key}"' in implementation, f"Outbox route drifted: {routing_key}"


@pytest.mark.parametrize(
    "name",
    ["blog-optimization.v1.json", "blog-skill-config.v1.json"],
)
def test_json_schema_is_wellformed(name):
    schema = json.loads((SCHEMA_DIR / name).read_text())
    assert schema.get("type") == "object"
    assert schema.get("additionalProperties") is False
    assert schema.get("required"), f"{name}: required must be non-empty"
    props = set(schema.get("properties", {}))
    assert not (set(schema["required"]) - props), f"{name}: required without property"


@pytest.mark.parametrize(
    ("model_name", "schema_name"),
    [
        ("BlogOptimizationV1", "blog-optimization.v1.json"),
        ("BlogSkillConfigV1", "blog-skill-config.v1.json"),
    ],
)
def test_pydantic_model_matches_json_schema(model_name, schema_name):
    from app.services.llm import schemas as llm_schemas

    model = getattr(llm_schemas, model_name)
    emitted = model.model_json_schema()
    reference = json.loads((SCHEMA_DIR / schema_name).read_text())
    assert set(emitted["required"]) == set(reference["required"]), "required drifted"
    assert emitted.get("additionalProperties") is False
