"""Prove MCP endpoint/token values never reach DB models, manifests, logs, or errors."""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid

import pytest

pytestmark = [pytest.mark.security]

_SECRET_URL = "https://mcp.super-secret-internal.example/notes/mcp"
_SECRET_TOKEN = "sk-live-should-never-leak-1234567890"
_SECRETS_JSON = {
    "connections": {
        "notes": {
            "display_name": "Notes MCP",
            "transport": "streamable_http",
            "url": _SECRET_URL,
            "auth": {"type": "bearer", "token": _SECRET_TOKEN},
            "allowed_redirect_hosts": ["mcp.super-secret-internal.example"],
        }
    }
}


@pytest.fixture
def secrets_file(tmp_path):
    path = tmp_path / "mcp-connections.json"
    path.write_text(json.dumps(_SECRETS_JSON), encoding="utf-8")
    return path


def test_get_safe_metadata_never_exposes_url_or_token(secrets_file) -> None:
    from app.services.mcp.config import McpSecretsConfig

    config = McpSecretsConfig.load(secrets_file)
    meta = config.get_safe_metadata("notes")

    dumped = json.dumps(dataclasses.asdict(meta))
    assert _SECRET_URL not in dumped
    assert _SECRET_TOKEN not in dumped
    assert meta.host == "mcp.super-secret-internal.example"
    assert meta.config_key == "notes"
    assert meta.display_name == "Notes MCP"


def test_list_safe_metadata_never_exposes_secrets(secrets_file) -> None:
    from app.services.mcp.config import McpSecretsConfig

    config = McpSecretsConfig.load(secrets_file)
    dumped = json.dumps([dataclasses.asdict(m) for m in config.list_safe_metadata()])
    assert _SECRET_URL not in dumped
    assert _SECRET_TOKEN not in dumped


def test_empty_optional_mcp_secrets_file_is_an_empty_config(tmp_path) -> None:
    """Match deploy.sh's empty placeholder for an unconfigured MCP gateway."""
    from app.services.mcp.config import McpSecretsConfig

    secrets_file = tmp_path / "mcp-connections.json"
    secrets_file.write_text("", encoding="utf-8")

    assert McpSecretsConfig.load(secrets_file).list_config_keys() == []


def test_mcp_connection_model_has_no_secret_bearing_columns() -> None:
    from app.models.agent_conversation import McpConnection

    column_names = {c.name for c in McpConnection.__table__.columns}
    forbidden = {"url", "endpoint", "token", "auth", "auth_token", "connection_string", "secret"}
    assert column_names.isdisjoint(forbidden)
    # config_key is the only thing keyed to the secrets file; it is opaque.
    assert "config_key" in column_names


def test_mcp_tool_snapshot_model_has_no_secret_bearing_columns() -> None:
    from app.models.agent_conversation import McpToolSnapshot

    column_names = {c.name for c in McpToolSnapshot.__table__.columns}
    forbidden = {"url", "endpoint", "token", "auth", "server_instructions"}
    assert column_names.isdisjoint(forbidden)


def test_invalid_secrets_file_error_never_echoes_raw_contents(tmp_path) -> None:
    from app.services.mcp.config import McpConfigError, McpSecretsConfig

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(
        json.dumps(
            {
                "connections": {
                    "notes": {
                        "display_name": "Notes",
                        "transport": "stdio",  # unsupported: must be rejected
                        "url": _SECRET_URL,
                        "auth": {"type": "bearer", "token": _SECRET_TOKEN},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(McpConfigError) as excinfo:
        McpSecretsConfig.load(bad_path)
    assert _SECRET_TOKEN not in str(excinfo.value)
    assert _SECRET_URL not in str(excinfo.value)


def test_provider_call_failure_error_never_echoes_secret(secrets_file, caplog) -> None:
    """A provider failure's McpError (message + diagnostic) must be safe to log
    and safe to surface to a user — no URL, no token, no raw SDK traceback."""
    from app.services.mcp.base import McpError
    from app.services.mcp.config import McpSecretsConfig
    from app.services.mcp.provider import StreamableHttpMcpProvider

    config = McpSecretsConfig.load(secrets_file)
    provider = StreamableHttpMcpProvider(secrets=config)

    with caplog.at_level(logging.WARNING), pytest.raises(McpError) as excinfo:
        provider.discover("notes")

    err = excinfo.value
    assert err.code in McpError.CODES
    dumped = json.dumps({"message": err.message, "diagnostic": err.diagnostic})
    assert _SECRET_TOKEN not in dumped
    assert _SECRET_URL not in dumped
    for record in caplog.records:
        assert _SECRET_TOKEN not in record.getMessage()
        assert _SECRET_URL not in record.getMessage()


def test_mcp_connection_config_key_column_is_bounded() -> None:
    """config_key is documented as an opaque short key, never a URL/token."""
    from app.models.agent_conversation import McpConnection

    config_key_column = McpConnection.__table__.columns["config_key"]
    assert config_key_column.type.length is not None
    assert config_key_column.type.length <= 120


def test_execution_record_redaction_covers_mcp_shaped_params() -> None:
    """MCP tool call arguments digested into ExecutionRecord.params_digest_json
    go through the existing audit redaction, which must catch token-shaped keys."""
    from app.modules.agent.audit import redact_sensitive

    redacted = redact_sensitive(
        {
            "connection_url": _SECRET_URL,
            "auth": {"type": "bearer", "token": _SECRET_TOKEN},
            "arguments": {"query": "hello"},
        }
    )
    dumped = json.dumps(redacted)
    assert _SECRET_TOKEN not in dumped


def test_mcp_tool_grant_scope_json_has_no_secret_columns() -> None:
    from app.models.agent_conversation import McpToolGrant

    column_names = {c.name for c in McpToolGrant.__table__.columns}
    forbidden = {"url", "endpoint", "token", "auth"}
    assert column_names.isdisjoint(forbidden)


def test_unknown_config_key_raises_without_echoing_the_lookup(secrets_file) -> None:
    from app.services.mcp.config import McpConfigError, McpSecretsConfig

    config = McpSecretsConfig.load(secrets_file)
    unknown_key = str(uuid.uuid4())
    with pytest.raises(McpConfigError) as excinfo:
        config.get_safe_metadata(unknown_key)
    assert unknown_key in str(excinfo.value)
    assert _SECRET_TOKEN not in str(excinfo.value)
    assert _SECRET_URL not in str(excinfo.value)
