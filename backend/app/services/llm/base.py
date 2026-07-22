"""Provider-neutral LLM gateway protocol and stable error categories.

Business modules never import a vendor SDK. Structured operations validate the
provider response against a strict, versioned Pydantic model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Stable provider error. `code` is one of the documented categories."""

    RETRYABLE: ClassVar[set[str]] = {"provider_unavailable", "timeout", "rate_limited"}

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.code in self.RETRYABLE


@dataclass
class EntityRef:
    type: str
    id: str
    version: int | None = None


@dataclass
class ChatRequest:
    scenario: str
    system: str
    user: str
    temperature: float = 0.2
    max_tokens: int = 1024


@dataclass
class ChatResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StructuredRequest[T: BaseModel]:
    scenario: str
    system: str
    user: str
    schema: type[T]
    grounded_refs: list[EntityRef] = field(default_factory=list)
    temperature: float = 0.0
    max_tokens: int = 2048
    repair_attempts: int = 1


class LLMGateway(Protocol):
    def chat(self, request: ChatRequest) -> ChatResponse: ...

    def structured(self, request: StructuredRequest[T]) -> T: ...
