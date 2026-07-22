"""Provider-neutral mail gateway protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MailError(Exception):
    """Stable mail error. `permanent=True` means do not retry (5xx / bounce)."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        self.permanent = permanent
        super().__init__(message)


@dataclass
class MailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


@dataclass
class MailResult:
    provider_message_id: str | None
    accepted: bool


class MailGateway(Protocol):
    def send(self, message: MailMessage) -> MailResult: ...
