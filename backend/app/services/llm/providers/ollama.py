"""Ollama structured-output adapter (local model server, no API key)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.llm.base import LLMError


class OllamaProvider:
    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> str:
        settings = get_settings()
        base = settings.llm_base_url or "http://localhost:11434"
        model = settings.llm_default_model or "llama3.1"
        try:
            resp = httpx.post(
                f"{base}/api/chat",
                json={
                    "model": model,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=120,
            )
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMError("provider_unavailable", str(exc)) from exc
        if resp.status_code >= 400:
            raise LLMError("provider_unavailable", f"Ollama {resp.status_code}")
        return resp.json()["message"]["content"]
