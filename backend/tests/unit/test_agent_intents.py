"""Extensible intent registration must not require dispatcher changes."""

from __future__ import annotations

import uuid

import pytest
from app.core.errors import ValidationError
from app.modules.agent.intents import IntentRegistry

pytestmark = [pytest.mark.unit]


def test_new_intent_is_dispatched_without_core_branch_changes() -> None:
    registry = IntentRegistry()
    intent_key = f"test.intent.{uuid.uuid4().hex}"

    @registry.register(intent_key)
    def handler(value: str) -> str:
        return f"handled:{value}"

    assert registry.dispatch(intent_key, "payload") == "handled:payload"


def test_unknown_intent_is_a_stable_domain_error() -> None:
    registry = IntentRegistry()

    with pytest.raises(ValidationError, match="Unknown intent") as exc_info:
        registry.dispatch("missing.intent")

    assert exc_info.value.code == "agent_intent_unknown"
