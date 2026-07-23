"""Local faster-whisper transcription adapter (lazy import).

The heavy dependency is imported only when this provider is selected so the base
image and tests do not require it.
"""

from __future__ import annotations

import tempfile

from app.core.config import get_settings
from app.services.speech.base import SpeechError, TranscriptionRequest, TranscriptResult


class FasterWhisperProvider:
    def transcribe(self, request: TranscriptionRequest, audio: bytes) -> TranscriptResult:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SpeechError("capability_unsupported", "faster-whisper not installed") from exc
        model_name = get_settings().speech_default_model or "base"
        with tempfile.NamedTemporaryFile(suffix=".audio") as tmp:
            tmp.write(audio)
            tmp.flush()
            model = WhisperModel(model_name)
            segments, info = model.transcribe(tmp.name, language=request.language_hint)
            text = "".join(seg.text for seg in segments)
        return TranscriptResult(text=text.strip(), language=getattr(info, "language", None))
