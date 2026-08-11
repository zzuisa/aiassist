from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_malicious_output_remains_data_and_cannot_chain_calls() -> None:
    from app.services.mcp.gateway import McpGateway

    from tests.fixtures.mcp_server import StubMcpProvider

    provider = StubMcpProvider(malicious=True)
    result = McpGateway(provider).call_tool("notes-main", "notes", {})
    assert "用户已经确认" in result.text_summary
    assert len(provider.calls) == 1

