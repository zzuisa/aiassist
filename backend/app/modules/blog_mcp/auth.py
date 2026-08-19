"""Scoped bearer tokens for the public blog MCP transport.

The normal web application uses same-origin HttpOnly cookies and CSRF. MCP
clients instead need an Authorization header, so this module issues a distinct
JWT type that cannot be accepted by the browser API dependency. Tokens are
short-lived, read-only, and bound to one existing user.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings

BLOG_MCP_AUDIENCE = "aiassist-blog-mcp"
BLOG_MCP_READ_SCOPE = "blog:read"
BLOG_MCP_CLAIM_TYPE = "mcp_blog"
MAX_TOKEN_DAYS = 90


class BlogMcpTokenError(ValueError):
    """Raised when a blog MCP bearer token is absent, invalid, or expired."""


def _signing_key() -> str:
    key = get_settings().resolved_jwt_signing_key
    if not key:
        raise RuntimeError("JWT signing key is not configured")
    return key


def issue_blog_mcp_token(user_id: uuid.UUID, *, days: int = 30) -> tuple[str, datetime]:
    """Issue a read-only MCP token that is rejected by normal web auth."""
    bounded_days = min(max(days, 1), MAX_TOKEN_DAYS)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=bounded_days)
    payload = {
        "sub": str(user_id),
        "aud": BLOG_MCP_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(18),
        "typ": BLOG_MCP_CLAIM_TYPE,
        "scope": [BLOG_MCP_READ_SCOPE],
    }
    token = jwt.encode(payload, _signing_key(), algorithm="HS256")
    return token, expires_at


def decode_blog_mcp_token(token: str) -> dict[str, Any]:
    """Validate a read-only blog MCP token and return its bounded claims."""
    try:
        claims = jwt.decode(
            token,
            _signing_key(),
            algorithms=["HS256"],
            audience=BLOG_MCP_AUDIENCE,
            options={"require": ["sub", "aud", "iat", "exp", "jti", "typ", "scope"]},
        )
    except jwt.PyJWTError as exc:
        raise BlogMcpTokenError("Invalid or expired blog MCP token") from exc
    scopes = claims.get("scope")
    if claims.get("typ") != BLOG_MCP_CLAIM_TYPE or not isinstance(scopes, list):
        raise BlogMcpTokenError("Invalid blog MCP token type")
    if BLOG_MCP_READ_SCOPE not in scopes:
        raise BlogMcpTokenError("Blog MCP token is missing read scope")
    try:
        uuid.UUID(str(claims["sub"]))
    except (TypeError, ValueError) as exc:
        raise BlogMcpTokenError("Invalid blog MCP token subject") from exc
    return claims


def bearer_token_from_headers(headers: dict[str, str] | None) -> str:
    authorization = (headers or {}).get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.casefold() != "bearer" or not token.strip():
        raise BlogMcpTokenError("Bearer token required")
    return token.strip()


def user_id_from_headers(headers: dict[str, str] | None) -> uuid.UUID:
    claims = decode_blog_mcp_token(bearer_token_from_headers(headers))
    return uuid.UUID(str(claims["sub"]))
