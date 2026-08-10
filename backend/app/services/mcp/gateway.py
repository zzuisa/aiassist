"""Synchronous worker-facing MCP façade + FastAPI dependency wiring.

Celery tasks and request handlers call ``McpGateway`` — never the provider or
the SDK directly. This mirrors how ``app/services/llm/gateway.py`` fronts LLM
providers: business code depends only on the provider-neutral protocol in
``base.py``.
"""

from __future__ import annotations

from typing import Any

from app.services.mcp.base import McpCallResult, McpDiscoveryResult, McpProvider
from app.services.mcp.provider import StreamableHttpMcpProvider


class McpGateway:
    """Thin façade over a provider-neutral ``McpProvider``."""

    def __init__(self, provider: McpProvider | None = None) -> None:
        self._provider = provider or StreamableHttpMcpProvider()

    def discover(self, connection_key: str) -> McpDiscoveryResult:
        return self._provider.discover(connection_key)

    def call_tool(
        self,
        connection_key: str,
        remote_name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> McpCallResult:
        return self._provider.call_tool(
            connection_key,
            remote_name,
            arguments,
            idempotency_key=idempotency_key,
        )


_default_gateway: McpGateway | None = None


def get_mcp_gateway() -> McpGateway:
    """FastAPI dependency / worker accessor for the process-wide gateway."""
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = McpGateway()
    return _default_gateway


def set_mcp_gateway(gateway: McpGateway | None) -> None:
    """Test-only override hook (mirrors patterns used for other gateways)."""
    global _default_gateway
    _default_gateway = gateway
