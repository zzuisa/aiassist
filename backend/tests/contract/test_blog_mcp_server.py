from __future__ import annotations

import re
import uuid

import pytest
from app.modules.blog_mcp.auth import issue_blog_mcp_token
from app.modules.blog_mcp.server import build_blog_mcp_asgi, build_blog_mcp_server
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.contract]


def _initialize_payload() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "contract-test", "version": "1.0.0"},
        },
    }


def test_blog_mcp_requires_scoped_bearer_token() -> None:
    server = build_blog_mcp_server()
    app = build_blog_mcp_asgi(server)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=_initialize_payload(),
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    assert response.json()["error"] == "invalid_token"


def test_blog_mcp_initializes_and_lists_only_curated_read_tools() -> None:
    server = build_blog_mcp_server()
    app = build_blog_mcp_asgi(server)
    token, _ = issue_blog_mcp_token(uuid.uuid4(), days=1)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app) as client:
        initialized = client.post("/mcp", json=_initialize_payload(), headers=headers)
        listed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={**headers, "MCP-Protocol-Version": "2025-11-25"},
        )

    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "roguelife-blog"
    assert listed.status_code == 200
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names == {
        "blog_get_post",
        "blog_list_categories",
        "blog_list_posts",
        "blog_list_tags",
        "blog_search_posts",
        "blog_timeline",
    }
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) for name in names)
