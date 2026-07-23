"""Anthropic structured-output adapter (Messages API)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.llm.base import LLMError


class AnthropicProvider:
    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> str:
        settings = get_settings()
        key = settings.resolved_llm_provider_key
        if not key:
            raise LLMError("authentication_failed", "Anthropic API key not configured")
        base = settings.llm_base_url or "https://api.anthropic.com/v1"
        model = settings.llm_default_model or "claude-sonnet-5"
        try:
            resp = httpx.post(
                f"{base}/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": f"{system}\n只输出符合要求的 JSON，不要额外文本。",
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=60,
            )
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMError("provider_unavailable", str(exc)) from exc
        if resp.status_code == 429:
            raise LLMError("rate_limited", "Anthropic rate limited")
        if resp.status_code == 401:
            raise LLMError("authentication_failed", "Anthropic auth failed")
        if resp.status_code >= 400:
            raise LLMError("provider_unavailable", f"Anthropic {resp.status_code}")
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))
