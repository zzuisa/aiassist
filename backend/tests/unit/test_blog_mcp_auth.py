from __future__ import annotations

import uuid

import pytest
from app.modules.auth.service import issue_access_token
from app.modules.blog_mcp.auth import (
    BLOG_MCP_READ_SCOPE,
    BlogMcpTokenError,
    decode_blog_mcp_token,
    issue_blog_mcp_token,
)

pytestmark = [pytest.mark.unit]


def test_blog_mcp_token_is_scoped_and_bound_to_user() -> None:
    user_id = uuid.uuid4()
    token, expires_at = issue_blog_mcp_token(user_id, days=7)

    claims = decode_blog_mcp_token(token)

    assert claims["sub"] == str(user_id)
    assert claims["scope"] == [BLOG_MCP_READ_SCOPE]
    assert expires_at.isoformat()


def test_normal_web_access_token_is_rejected_by_blog_mcp() -> None:
    token, _ = issue_access_token(uuid.uuid4(), uuid.uuid4())

    with pytest.raises(BlogMcpTokenError):
        decode_blog_mcp_token(token)

