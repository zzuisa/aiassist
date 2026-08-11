from __future__ import annotations

import pytest
from app.services.mcp.gateway import McpGateway

from tests.fixtures.mcp_server import StubMcpProvider

pytestmark = [pytest.mark.contract]


def test_discovery_namespaces_tools_and_uses_cache() -> None:
    provider = StubMcpProvider()
    gateway = McpGateway(provider)
    first = gateway.discover("notes-main")
    second = gateway.discover("notes-main")
    assert first is second
    assert first.tools[0].tool_key == "mcp.notes-main.notes"
    assert "endpoint" not in first.tools[0].__dict__ if hasattr(first.tools[0], "__dict__") else True

