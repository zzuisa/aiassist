"""Streamable HTTP MCP provider built on the official ``mcp`` Python SDK (v2.x).

This is the ONLY module allowed to import the ``mcp``/``mcp_types``/``httpx2``
packages. Every transport or protocol failure is translated to a stable
``McpError`` from ``base.py`` before it can reach callers — no raw SDK
exception or traceback crosses this boundary. The worker-facing synchronous
facade lives in ``gateway.py``; this module is async internally (the SDK is
async-only) and exposes a small sync surface via ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings, get_settings
from app.core.observability import get_logger
from app.services.mcp.base import (
    McpCallResult,
    McpDiscoveryResult,
    McpError,
    McpToolDescriptor,
)
from app.services.mcp.config import ConnectionSecret, McpSecretsConfig, get_mcp_secrets_config

log = get_logger("mcp.provider")


def _headers(secret: ConnectionSecret) -> dict[str, str]:
    if secret.auth_type == "bearer" and secret.auth_token:
        # Token is bound to this one preconfigured resource; never forwarded
        # from a user-supplied value ("no token passthrough" per plan.md).
        return {"Authorization": f"Bearer {secret.auth_token}"}
    return {}


def _http_client(secret: ConnectionSecret, settings: Settings) -> httpx2.AsyncClient:
    timeout = httpx2.Timeout(
        connect=settings.mcp_connect_timeout_seconds,
        read=settings.mcp_read_timeout_seconds,
        write=settings.mcp_read_timeout_seconds,
        pool=settings.mcp_connect_timeout_seconds,
    )
    return httpx2.AsyncClient(headers=_headers(secret), timeout=timeout)


def _classify_tool_type(annotations: Any) -> str:
    """Best-effort read/write hint. Per the MCP spec, ``ToolAnnotations`` are
    UNTRUSTED SERVER HINTS — a malicious/misconfigured server can claim
    ``read_only_hint=True`` for a destructive tool. This classification is only
    a starting point for the registry's safe manifest; write-eligibility and
    confirmation gating in ``modules/agent/registry.py`` never rely solely on
    it, and the router's structured route/operation_type is the actual policy
    signal used before any mutation can occur."""
    if annotations is not None and getattr(annotations, "read_only_hint", None) is True:
        return "read"
    return "write"


async def _discover_async(secret: ConnectionSecret, settings: Settings) -> McpDiscoveryResult:
    transport = streamable_http_client(secret.url, http_client=_http_client(secret, settings))
    async with Client(transport, read_timeout_seconds=settings.mcp_read_timeout_seconds) as client:
        listing = await client.list_tools()
        tools = []
        for tool in listing.tools:
            policy = secret.tool_policies.get(tool.name)
            reviewed = policy is not None
            if policy is None:
                tool_type = _classify_tool_type(tool.annotations)
                responsibility = (tool.description or "")[:500]
                previewable = False
                reversible = False
            else:
                tool_type = str(policy["type"])
                responsibility = (
                    str(policy.get("responsibility") or "") or (tool.description or "")[:500]
                )
                previewable = bool(policy.get("previewable"))
                reversible = bool(policy.get("reversible"))
            tools.append(
                McpToolDescriptor(
                    tool_key=tool.name,
                    remote_name=tool.name,
                    responsibility=responsibility,
                    tool_type=tool_type,
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                    risk={
                        "reviewed": reviewed,
                        "previewable": previewable,
                        "reversible": reversible,
                    },
                    available=reviewed and (tool_type == "read" or previewable),
                    unavailable_reason=(
                        None
                        if reviewed and (tool_type == "read" or previewable)
                        else "工具尚未通过运维安全审查或无法预览影响范围"
                    ),
                )
            )
    return McpDiscoveryResult(
        tools=tools,
        protocol_version=None,
        catalog_etag=None,
        catalog_ttl_seconds=settings.mcp_catalog_ttl_seconds,
    )


async def _call_tool_async(
    secret: ConnectionSecret,
    settings: Settings,
    remote_name: str,
    arguments: dict[str, Any],
) -> McpCallResult:
    transport = streamable_http_client(secret.url, http_client=_http_client(secret, settings))
    async with Client(transport, read_timeout_seconds=settings.mcp_read_timeout_seconds) as client:
        result = await client.call_tool(remote_name, arguments)
    return _to_call_result(result, settings)


def _to_call_result(result: Any, settings: Settings) -> McpCallResult:
    """Validate size/media before any content reaches the caller. MCP output is
    untrusted data — this function must never let it act as instructions."""
    structured = result.structured_content
    text_parts: list[str] = []
    total_bytes = 0
    for block in result.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", "") or ""
            total_bytes += len(text.encode("utf-8"))
            text_parts.append(text)
        else:
            # Non-text content (images, embedded resources, unknown media) is
            # never forwarded into a model prompt in this version.
            total_bytes += 1024
    truncated = False
    if total_bytes > settings.mcp_max_result_bytes:
        truncated = True
        text_parts = [t[:2000] for t in text_parts]
    if structured is not None:
        import json

        encoded = json.dumps(structured, ensure_ascii=False, default=str).encode("utf-8")
        if len(encoded) > settings.mcp_max_result_bytes:
            truncated = True
            structured = None
    summary = "\n".join(text_parts)[:4000] if text_parts else None
    return McpCallResult(
        is_error=bool(result.is_error),
        structured_content=structured if not truncated else None,
        text_summary=summary,
        truncated=truncated,
    )


def _run_with_retry(coro_factory: Any, *, settings: Settings, config_key: str) -> Any:
    last_error: McpError | None = None
    attempts = settings.mcp_max_retries + 1
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            return asyncio.run(coro_factory())
        except MCPError as exc:
            last_error = McpError(
                "MCP_PROTOCOL_ERROR",
                "MCP server returned a protocol-level error",
                diagnostic={"config_key": config_key, "sdk_code": exc.code},
            )
        except PydanticValidationError as exc:
            # An invalid result is never retried — retrying will not fix a
            # malformed server response.
            raise McpError(
                "MCP_INVALID_RESULT",
                "MCP server returned a result that failed schema validation",
                diagnostic={"config_key": config_key, "errors": exc.error_count()},
            ) from exc
        except httpx2.TimeoutException as exc:
            last_error = McpError(
                "MCP_TIMEOUT",
                "MCP server did not respond in time",
                diagnostic={"config_key": config_key},
            )
            _ = exc
        except httpx2.HTTPError as exc:
            last_error = McpError(
                "MCP_UNAVAILABLE",
                "MCP server is unreachable",
                diagnostic={"config_key": config_key},
            )
            _ = exc
        except Exception as exc:  # final backstop, never leak a raw SDK exception
            last_error = McpError(
                "MCP_PROTOCOL_ERROR",
                "MCP call failed unexpectedly",
                diagnostic={"config_key": config_key, "exception_type": type(exc).__name__},
            )
        log.warning(
            "mcp_call_attempt_failed",
            config_key=config_key,
            attempt=attempt + 1,
            attempts=attempts,
            code=last_error.code if last_error else None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        if not last_error.retryable or attempt == attempts - 1:
            raise last_error
    raise McpError(  # pragma: no cover - loop always returns or raises above
        "MCP_PROTOCOL_ERROR", "MCP call exhausted retries unexpectedly"
    )


class StreamableHttpMcpProvider:
    """Synchronous-facing MCP provider used by ``McpGateway``."""

    def __init__(self, secrets: McpSecretsConfig | None = None) -> None:
        self._secrets = secrets

    def _resolve_secrets(self) -> McpSecretsConfig:
        return self._secrets or get_mcp_secrets_config()

    def discover(self, connection_key: str) -> McpDiscoveryResult:
        settings = get_settings()
        secret = self._resolve_secrets().get_secret(connection_key)
        return _run_with_retry(
            lambda: _discover_async(secret, settings),
            settings=settings,
            config_key=connection_key,
        )

    def call_tool(
        self,
        connection_key: str,
        remote_name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> McpCallResult:
        # idempotency_key is accepted for interface symmetry with the caller's
        # own dedupe bookkeeping; the SDK's HTTP layer has no native concept of
        # it for tool calls in this protocol version.
        del idempotency_key
        settings = get_settings()
        secret = self._resolve_secrets().get_secret(connection_key)
        return _run_with_retry(
            lambda: _call_tool_async(secret, settings, remote_name, arguments),
            settings=settings,
            config_key=connection_key,
        )
