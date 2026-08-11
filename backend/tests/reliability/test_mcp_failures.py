from __future__ import annotations

import pytest
from app.services.mcp.base import McpError
from app.services.mcp.gateway import McpGateway

from tests.fixtures.mcp_server import StubMcpProvider

pytestmark = [pytest.mark.reliability]


@pytest.mark.parametrize(
    "code", ["MCP_UNAVAILABLE", "MCP_TIMEOUT", "MCP_INVALID_RESULT", "MCP_PROTOCOL_ERROR"]
)
def test_stable_dependency_failures_are_preserved(code: str) -> None:
    gateway = McpGateway(StubMcpProvider(error=McpError(code)))
    with pytest.raises(McpError) as exc:
        gateway.discover("notes-main")
    assert exc.value.code == code
