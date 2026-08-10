"""Provider-neutral MCP connection, discovery, call, error, and result types.

Business and worker code only ever imports names from this module (plus the
synchronous ``McpGateway`` facade in ``gateway.py``) — never a vendor SDK type.
This keeps the official ``mcp`` Python SDK an implementation detail of
``provider.py`` and gives tests a trivial fake to substitute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol


class McpError(Exception):
    """Stable, closed-set MCP failure. Never carries a raw SDK traceback."""

    RETRYABLE: ClassVar[set[str]] = {"MCP_UNAVAILABLE", "MCP_TIMEOUT"}
    CODES: ClassVar[set[str]] = {
        "MCP_UNAVAILABLE",
        "MCP_TIMEOUT",
        "MCP_INVALID_RESULT",
        "MCP_PROTOCOL_ERROR",
        "MCP_UNKNOWN_CONNECTION",
        "MCP_UNKNOWN_TOOL",
        "MCP_RESULT_TOO_LARGE",
    }

    def __init__(
        self, code: str, message: str = "", *, diagnostic: dict[str, Any] | None = None
    ) -> None:
        if code not in self.CODES:
            raise ValueError(f"Unknown McpError code: {code}")
        self.code = code
        self.message = message or code
        # Diagnostic is for logs only; callers must never surface it verbatim to
        # a model prompt or an end user without redaction.
        self.diagnostic = diagnostic or {}
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.code in self.RETRYABLE


@dataclass(frozen=True, slots=True)
class McpToolDescriptor:
    """One safe, discovered tool description — never endpoint/auth/instructions."""

    tool_key: str
    remote_name: str
    responsibility: str
    tool_type: str  # "read" | "write"
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    available: bool = True
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class McpDiscoveryResult:
    tools: list[McpToolDescriptor] = field(default_factory=list)
    protocol_version: str | None = None
    catalog_etag: str | None = None


@dataclass(frozen=True, slots=True)
class McpCallResult:
    """A size/media-checked, structurally validated tool result."""

    is_error: bool
    structured_content: Any = None
    text_summary: str | None = None
    truncated: bool = False


class McpConnectionHandle(Protocol):
    """Opaque handle a provider returns; callers never see endpoint/auth."""


class McpProvider(Protocol):
    """Synchronous-facing provider-neutral MCP boundary.

    Implementations (see ``provider.py``) own all async SDK usage internally
    and must translate every transport/protocol failure into ``McpError``.
    """

    def discover(self, connection_key: str) -> McpDiscoveryResult: ...

    def call_tool(
        self,
        connection_key: str,
        remote_name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> McpCallResult: ...
