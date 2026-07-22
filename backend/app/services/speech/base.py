"""Provider-neutral speech (transcription) gateway protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol


class SpeechError(Exception):
    RETRYABLE: ClassVar[set[str]] = {"provider_unavailable", "timeout", "rate_limited"}

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.code in self.RETRYABLE


@dataclass
class TranscriptionRequest:
    object_key: str
    media_type: str
    language_hint: str | None = None
    timeout_seconds: int = 120


@dataclass
class TranscriptResult:
    text: str
    language: str | None = None
    duration_seconds: float | None = None


class SpeechGateway(Protocol):
    def transcribe(self, request: TranscriptionRequest) -> TranscriptResult: ...
