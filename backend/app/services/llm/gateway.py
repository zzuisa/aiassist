"""LLM gateway: scenario routing + strict structured-output validation.

Business modules call ``structured()`` with a scenario and a strict Pydantic
schema. The gateway selects a provider adapter, obtains raw JSON, validates it
with ``extra='forbid'``, and allows at most one bounded repair attempt. Invalid
output raises ``LLMError('invalid_structured_output')`` and never mutates data.
"""

from __future__ import annotations

import json
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.services.llm.base import LLMError, StructuredRequest

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class StructuredProvider(Protocol):
    """Adapter interface returning raw text for a structured prompt."""

    def complete_json(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> str: ...


class FakeProvider:
    """Deterministic provider for tests and unconfigured deployments.

    It echoes a caller-supplied JSON body embedded in the user prompt after the
    marker ``<<JSON>>``. This lets tests drive exact provider output (including
    malformed output) without a network call, while production uses real adapters.
    """

    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> str:
        marker = "<<JSON>>"
        if marker in user:
            return user.split(marker, 1)[1].strip()
        raise LLMError("provider_unavailable", "No fake JSON payload provided")


def _select_provider(scenario: str) -> StructuredProvider:
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "none":
        return FakeProvider()
    if provider == "openai":
        from app.services.llm.providers.openai import OpenAIProvider

        return OpenAIProvider()
    if provider == "anthropic":
        from app.services.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if provider == "ollama":
        from app.services.llm.providers.ollama import OllamaProvider

        return OllamaProvider()
    raise LLMError("capability_unsupported", f"Unknown provider {provider}")


class LLMGatewayImpl:
    def __init__(self, provider: StructuredProvider | None = None) -> None:
        self._provider = provider

    def structured(self, request: StructuredRequest[T]) -> T:
        provider = self._provider or _select_provider(request.scenario)
        raw = provider.complete_json(
            request.system,
            request.user,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        try:
            return self._validate(raw, request.schema)
        except (ValidationError, json.JSONDecodeError) as first_err:
            if request.repair_attempts <= 0:
                raise LLMError("invalid_structured_output", str(first_err)) from first_err
            # One bounded repair attempt: re-prompt with the validation error,
            # never with additional private entities.
            repair_user = (
                f"{request.user}\n\n上一次输出无法通过校验：{first_err}. "
                "只返回符合 schema 的 JSON。"
            )
            raw2 = provider.complete_json(
                request.system,
                repair_user,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            try:
                return self._validate(raw2, request.schema)
            except (ValidationError, json.JSONDecodeError) as second_err:
                raise LLMError("invalid_structured_output", str(second_err)) from second_err

    @staticmethod
    def _validate(raw: str, schema: type[T]) -> T:
        data = json.loads(raw)
        return schema.model_validate(data)


_default: LLMGatewayImpl | None = None


def get_llm_gateway() -> LLMGatewayImpl:
    global _default
    if _default is None:
        _default = LLMGatewayImpl()
    return _default
