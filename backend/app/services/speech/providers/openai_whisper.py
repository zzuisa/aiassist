"""OpenAI Whisper transcription adapter."""

from __future__ import annotations

import io

import httpx

from app.core.config import get_settings
from app.services.speech.base import SpeechError, TranscriptionRequest, TranscriptResult


class OpenAIWhisperProvider:
    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult:
        settings = get_settings()
        key = settings.resolved_llm_provider_key
        if not key:
            raise SpeechError("authentication_failed", "OpenAI key not configured")
        base = settings.llm_base_url or "https://api.openai.com/v1"
        model = settings.speech_default_model or "whisper-1"
        try:
            resp = httpx.post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("audio", io.BytesIO(audio), request.media_type)},
                data={"model": model},
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SpeechError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise SpeechError("provider_unavailable", str(exc)) from exc
        if resp.status_code == 429:
            raise SpeechError("rate_limited", "rate limited")
        if resp.status_code >= 400:
            raise SpeechError("provider_unavailable", f"whisper {resp.status_code}")
        return TranscriptResult(text=resp.json().get("text", ""), language=request.language_hint)
