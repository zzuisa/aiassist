"""OpenAI structured-output adapter (Chat Completions with JSON response)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.llm.base import LLMError


class OpenAIProvider:
    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> str:
        settings = get_settings()
        key = settings.resolved_llm_provider_key
        if not key:
            raise LLMError("authentication_failed", "OpenAI API key not configured")
        base = settings.llm_base_url or "https://api.openai.com/v1"
        model = settings.llm_default_model or "gpt-4o-mini"
        try:
            resp = httpx.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=60,
            )
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMError("provider_unavailable", str(exc)) from exc
        if resp.status_code == 429:
            raise LLMError("rate_limited", "OpenAI rate limited")
        if resp.status_code == 401:
            raise LLMError("authentication_failed", "OpenAI auth failed")
        if resp.status_code >= 400:
            raise LLMError("provider_unavailable", f"OpenAI {resp.status_code}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
