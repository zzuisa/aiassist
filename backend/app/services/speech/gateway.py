"""Speech gateway: provider routing for transcription.

Adapters: OpenAI Whisper, local faster-whisper, and a generic cloud adapter. A
Fake provider serves tests and unconfigured deployments by reading a transcript
embedded in the object key metadata via the injected reader.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.config import get_settings
from app.services.speech.base import SpeechError, TranscriptionRequest, TranscriptResult


@runtime_checkable
class TranscribeProvider(Protocol):
    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult: ...


class FakeSpeechProvider:
    """Interprets the audio bytes as UTF-8 text (tests write text as 'audio')."""

    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult:
        try:
            text = audio.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise SpeechError("content_rejected", "audio not decodable") from exc
        if not text:
            raise SpeechError("content_rejected", "empty transcript")
        return TranscriptResult(text=text, language=request.language_hint or "zh")


def _select_provider() -> TranscribeProvider:
    provider = get_settings().speech_provider
    if provider == "none":
        return FakeSpeechProvider()
    if provider == "openai":
        from app.services.speech.providers.openai_whisper import OpenAIWhisperProvider

        return OpenAIWhisperProvider()
    if provider == "faster_whisper":
        from app.services.speech.providers.faster_whisper import FasterWhisperProvider

        return FasterWhisperProvider()
    if provider == "cloud":
        from app.services.speech.providers.cloud import CloudSpeechProvider

        return CloudSpeechProvider()
    raise SpeechError("capability_unsupported", f"Unknown speech provider {provider}")


class SpeechGatewayImpl:
    def __init__(self, provider: TranscribeProvider | None = None) -> None:
        self._provider = provider

    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult:
        provider = self._provider or _select_provider()
        return provider.transcribe(request, audio)


_default: SpeechGatewayImpl | None = None


def get_speech_gateway() -> SpeechGatewayImpl:
    global _default
    if _default is None:
        _default = SpeechGatewayImpl()
    return _default
