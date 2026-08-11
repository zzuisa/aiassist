"""Synchronous worker-facing MCP façade + FastAPI dependency wiring.

Celery tasks and request handlers call ``McpGateway`` — never the provider or
the SDK directly. This mirrors how ``app/services/llm/gateway.py`` fronts LLM
providers: business code depends only on the provider-neutral protocol in
``base.py``.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

import jsonschema

from app.services.mcp.base import McpCallResult, McpDiscoveryResult, McpProvider
from app.services.mcp.provider import StreamableHttpMcpProvider


class McpGateway:
    """Thin façade over a provider-neutral ``McpProvider``."""

    def __init__(self, provider: McpProvider | None = None) -> None:
        self._provider = provider or StreamableHttpMcpProvider()
        self._catalog_cache: dict[str, tuple[float, McpDiscoveryResult]] = {}

    def discover(self, connection_key: str) -> McpDiscoveryResult:
        cached = self._catalog_cache.get(connection_key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        result = self._provider.discover(connection_key)
        normalized = []
        for tool in result.tools:
            try:
                jsonschema.Draft202012Validator.check_schema(tool.input_schema)
            except jsonschema.SchemaError:
                normalized.append(
                    replace(
                        tool,
                        tool_key=f"mcp.{connection_key}.{tool.remote_name}",
                        available=False,
                        unavailable_reason="工具参数 schema 不受支持",
                    )
                )
                continue
            normalized.append(replace(tool, tool_key=f"mcp.{connection_key}.{tool.remote_name}"))
        safe_result = replace(result, tools=normalized)
        ttl = result.catalog_ttl_seconds or 300
        self._catalog_cache[connection_key] = (time.monotonic() + ttl, safe_result)
        return safe_result

    def invalidate_catalog(self, connection_key: str | None = None) -> None:
        if connection_key is None:
            self._catalog_cache.clear()
        else:
            self._catalog_cache.pop(connection_key, None)

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
