"""Generic cloud speech adapter placeholder (deployer-configured endpoint)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.speech.base import SpeechError, TranscriptionRequest, TranscriptResult


class CloudSpeechProvider:
    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult:
        settings = get_settings()
        endpoint = settings.llm_base_url
        if not endpoint:
            raise SpeechError("capability_unsupported", "cloud speech endpoint not configured")
        try:
            resp = httpx.post(
                endpoint,
                content=audio,
                headers={"Content-Type": request.media_type},
                timeout=request.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise SpeechError("provider_unavailable", str(exc)) from exc
        if resp.status_code >= 400:
            raise SpeechError("provider_unavailable", f"cloud {resp.status_code}")
        return TranscriptResult(text=resp.json().get("text", ""), language=request.language_hint)
