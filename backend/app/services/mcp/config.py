"""Validated, read-only loading of the operator MCP secrets file.

Endpoints, tokens, and connection strings live ONLY in the JSON file at
``Settings.mcp_secrets_path`` (see ``deploy/secrets/mcp-connections.example.json``),
keyed by an opaque ``config_key``. This module is the single place allowed to
read that file. Everything it exposes to the rest of the app is either:

* the opaque ``config_key`` string, or
* ``ConnectionSafeMetadata`` (display name, transport, host — never a full URL,
  path, query string, or credential), or
* a ``ConnectionSecret`` handed only to ``provider.py`` inside this same
  package to actually open a connection.

No other module may import ``ConnectionSecret`` or read the secrets file
directly. Logs, DB rows, Pydantic response schemas, and LLM prompts must only
ever see ``config_key`` + safe metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings, get_settings

ALLOWED_TRANSPORTS = frozenset({"streamable_http"})
ALLOWED_AUTH_TYPES = frozenset({"none", "bearer"})
ALLOWED_URL_SCHEMES = frozenset({"https", "http"})


class McpConfigError(Exception):
    """Raised for a structurally invalid secrets file or bad config_key."""


@dataclass(frozen=True, slots=True)
class ConnectionSecret:
    """Everything needed to open a connection. NEVER log, store, or return this
    outside ``app/services/mcp/``."""

    config_key: str
    display_name: str
    transport: str
    url: str
    auth_type: str
    auth_token: str | None
    allowed_redirect_hosts: frozenset[str]
    tool_policies: dict[str, dict[str, Any]]
    auto_grant: bool


@dataclass(frozen=True, slots=True)
class ConnectionSafeMetadata:
    """Fields safe to place in DB rows, API responses, logs, or LLM prompts."""

    config_key: str
    display_name: str
    transport: str
    host: str
    auto_grant: bool = False


def _host_of(url: str) -> str:
    host = urlsplit(url).hostname
    return host or ""


def _validate_entry(config_key: str, raw: Any) -> ConnectionSecret:
    if not isinstance(raw, dict):
        raise McpConfigError(f"MCP connection '{config_key}' must be an object")
    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise McpConfigError(f"MCP connection '{config_key}' is missing display_name")
    transport = raw.get("transport")
    if transport not in ALLOWED_TRANSPORTS:
        raise McpConfigError(
            f"MCP connection '{config_key}' has unsupported transport {transport!r}; "
            f"only {sorted(ALLOWED_TRANSPORTS)} is supported"
        )
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        raise McpConfigError(f"MCP connection '{config_key}' is missing url")
    parsed = urlsplit(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        raise McpConfigError(f"MCP connection '{config_key}' has an invalid url")

    auth = raw.get("auth") or {}
    if not isinstance(auth, dict):
        raise McpConfigError(f"MCP connection '{config_key}' has an invalid auth block")
    auth_type = auth.get("type", "none")
    if auth_type not in ALLOWED_AUTH_TYPES:
        raise McpConfigError(
            f"MCP connection '{config_key}' has unsupported auth type {auth_type!r}"
        )
    auth_token = auth.get("token")
    if auth_type == "bearer" and (not isinstance(auth_token, str) or not auth_token.strip()):
        raise McpConfigError(f"MCP connection '{config_key}' bearer auth requires a token")
    if auth_type == "none":
        auth_token = None

    raw_redirect_hosts = raw.get("allowed_redirect_hosts", [])
    if not isinstance(raw_redirect_hosts, list) or not all(
        isinstance(h, str) and h.strip() for h in raw_redirect_hosts
    ):
        raise McpConfigError(
            f"MCP connection '{config_key}' allowed_redirect_hosts must be a list of hostnames"
        )
    # The connection's own host is always an implicitly allowed "redirect" target
    # (i.e. staying on the same host is never a privilege escalation).
    allowed_redirect_hosts = frozenset({*raw_redirect_hosts, parsed.hostname})

    raw_policies = raw.get("tool_policies", {})
    if not isinstance(raw_policies, dict):
        raise McpConfigError(f"MCP connection '{config_key}' tool_policies must be an object")
    tool_policies: dict[str, dict[str, Any]] = {}
    for tool_name, policy in raw_policies.items():
        if not isinstance(tool_name, str) or not isinstance(policy, dict):
            raise McpConfigError(f"MCP connection '{config_key}' has an invalid tool policy")
        tool_type = policy.get("type")
        if tool_type not in {"read", "write"}:
            raise McpConfigError(
                f"MCP connection '{config_key}' tool '{tool_name}' requires reviewed type"
            )
        tool_policies[tool_name] = {
            "type": tool_type,
            "responsibility": str(policy.get("responsibility") or "")[:500],
            "previewable": bool(policy.get("previewable", False)),
            "reversible": bool(policy.get("reversible", False)),
        }

    auto_grant = raw.get("auto_grant", False)
    if not isinstance(auto_grant, bool):
        raise McpConfigError(f"MCP connection '{config_key}' auto_grant must be a boolean")

    return ConnectionSecret(
        config_key=config_key,
        display_name=display_name.strip(),
        transport=transport,
        url=url,
        auth_type=auth_type,
        auth_token=auth_token,
        allowed_redirect_hosts=allowed_redirect_hosts,
        tool_policies=tool_policies,
        auto_grant=auto_grant,
    )


class McpSecretsConfig:
    """Validated, in-memory view of the operator MCP secrets file."""

    def __init__(self, connections: dict[str, ConnectionSecret]) -> None:
        self._connections = connections

    @classmethod
    def load(cls, path: Path) -> McpSecretsConfig:
        try:
            raw_text = path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            raise McpConfigError("MCP secrets file is unreadable or not valid JSON") from exc
        # ``deploy.sh`` deliberately creates an empty placeholder when MCP is
        # not configured so Compose's file-backed secret source remains valid.
        # Treat that placeholder exactly like an absent optional configuration;
        # otherwise every non-fast-path conversation would fail before routing.
        if not raw_text.strip():
            return cls.empty()
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise McpConfigError("MCP secrets file is unreadable or not valid JSON") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("connections"), dict):
            raise McpConfigError("MCP secrets file must have a top-level 'connections' object")
        connections: dict[str, ConnectionSecret] = {}
        for config_key, entry in raw["connections"].items():
            if not isinstance(config_key, str) or not config_key.strip():
                raise McpConfigError("MCP connection keys must be non-empty strings")
            connections[config_key] = _validate_entry(config_key, entry)
        return cls(connections)

    @classmethod
    def empty(cls) -> McpSecretsConfig:
        return cls({})

    def list_config_keys(self) -> list[str]:
        return sorted(self._connections)

    def get_secret(self, config_key: str) -> ConnectionSecret:
        """Return the connection secret. Callers outside app/services/mcp/ MUST NOT
        call this — use ``get_safe_metadata`` instead."""
        secret = self._connections.get(config_key)
        if secret is None:
            raise McpConfigError(f"Unknown MCP config_key: {config_key}")
        return secret

    def get_safe_metadata(self, config_key: str) -> ConnectionSafeMetadata:
        secret = self.get_secret(config_key)
        return ConnectionSafeMetadata(
            config_key=secret.config_key,
            display_name=secret.display_name,
            transport=secret.transport,
            host=_host_of(secret.url),
            auto_grant=secret.auto_grant,
        )

    def list_safe_metadata(self) -> list[ConnectionSafeMetadata]:
        return [self.get_safe_metadata(key) for key in self.list_config_keys()]

    def is_redirect_allowed(self, config_key: str, target_host: str) -> bool:
        """Whether following a redirect to ``target_host`` is permitted for this
        connection — enforced by the provider before it follows any redirect."""
        secret = self.get_secret(config_key)
        return target_host in secret.allowed_redirect_hosts


def load_mcp_secrets_config(settings: Settings | None = None) -> McpSecretsConfig:
    """Load (uncached) the current MCP secrets file, or an empty config when
    unconfigured. Never raises for a missing file — only for a malformed one."""
    settings = settings or get_settings()
    path = settings.mcp_secrets_path
    if path is None:
        return McpSecretsConfig.empty()
    return McpSecretsConfig.load(path)


@lru_cache
def _cached_config(mtime_ns: int, path_str: str) -> McpSecretsConfig:
    return McpSecretsConfig.load(Path(path_str))


def get_mcp_secrets_config() -> McpSecretsConfig:
    """Return a config, reloaded automatically whenever the secrets file changes
    (keyed on mtime), and cached otherwise to avoid re-parsing on every call."""
    settings = get_settings()
    path = settings.mcp_secrets_path
    if path is None:
        return McpSecretsConfig.empty()
    return _cached_config(path.stat().st_mtime_ns, str(path))


def reset_mcp_secrets_cache() -> None:
    """Test-only: clear the cached config (mirrors ``reload_settings``)."""
    _cached_config.cache_clear()


def list_safe_mcp_metadata() -> list[ConnectionSafeMetadata]:
    """Public non-secret view used by persistence/bootstrap code."""
    return get_mcp_secrets_config().list_safe_metadata()
