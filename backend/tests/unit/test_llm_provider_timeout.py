"""LLM providers use the configurable long-read timeout without becoming unbounded."""

from __future__ import annotations

from types import SimpleNamespace

import httpx


def test_openai_provider_uses_configured_connect_and_read_timeouts(monkeypatch) -> None:
    from app.services.llm.providers import http as timeout_module
    from app.services.llm.providers import openai

    settings = SimpleNamespace(
        resolved_llm_provider_key="test-key",
        llm_base_url="https://provider.example/v1",
        llm_default_model="test-model",
        llm_connect_timeout_seconds=10.0,
        llm_read_timeout_seconds=300.0,
    )
    monkeypatch.setattr(openai, "get_settings", lambda: settings)
    monkeypatch.setattr(timeout_module, "get_settings", lambda: settings)
    captured: dict = {}

    def fake_post(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": '{"ok":true}'}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    assert openai.OpenAIProvider().complete_json("system", "user", temperature=0, max_tokens=8)
    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 10.0
    assert timeout.read == 300.0


def test_llm_timeout_defaults_are_bounded() -> None:
    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.llm_connect_timeout_seconds == 10.0
    assert settings.llm_read_timeout_seconds == 300.0
    assert settings.llm_max_output_tokens == 6144
