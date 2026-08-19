from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.security]


def test_public_plan_schema_has_no_private_execution_fields() -> None:
    from app.modules.agent.planning_schemas import AgentPlanView

    schema_text = json.dumps(AgentPlanView.model_json_schema()).casefold()
    for forbidden in (
        "arguments_json",
        "payload_json",
        "system_instruction",
        "prompt",
        "skill_instruction",
        "chain_of_thought",
        "credential",
        "endpoint",
    ):
        assert forbidden not in schema_text
