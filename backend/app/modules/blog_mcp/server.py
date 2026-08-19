"""Streamable HTTP MCP server exposing curated read-only blog tools."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlsplit

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.foundation import User
from app.modules.blog_mcp.auth import (
    BlogMcpTokenError,
    bearer_token_from_headers,
    decode_blog_mcp_token,
    user_id_from_headers,
)

MCP_MOUNT_PATH = "/api/v1/mcp/blog"
MCP_PROTOCOL_PATH = "/mcp"


class BlogMcpBearerAuthMiddleware:
    """Require a valid scoped token before any MCP method is processed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").casefold(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        try:
            decode_blog_mcp_token(bearer_token_from_headers(headers))
        except BlogMcpTokenError:
            response = JSONResponse(
                {"error": "invalid_token", "message": "A valid blog MCP bearer token is required."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="aiassist-blog-mcp"'},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _owned_user_id(ctx: Context) -> uuid.UUID:
    user_id = user_id_from_headers(dict(ctx.headers or {}))
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None or user.status != "active":
            raise PermissionError("The blog MCP token owner is not active")
    return user_id


def _uuid_or_error(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc


def _bounded_page(cursor: int, limit: int) -> tuple[int, int]:
    return min(max(cursor, 0), 1_000_000), min(max(limit, 1), 100)


def build_blog_mcp_server() -> MCPServer:
    server = MCPServer(
        name="roguelife-blog",
        title="RogueLife 博客管理",
        description="AI Assist 内部博客的只读查询、搜索、时间轴与分类能力。",
        instructions=(
            "所有结果都属于 Bearer Token 绑定的用户。当前服务只允许读取；"
            "不得声称已经创建、修改、删除或发布文章。"
        ),
        version="1.0.0",
    )

    @server.tool(
        name="blog_list_posts",
        title="列出博客文章",
        description="按更新时间列出当前用户的博客文章元数据，不返回正文。",
        structured_output=True,
    )
    def list_posts(
        ctx: Context,
        limit: int = 30,
        cursor: int = 0,
        content_status: str | None = None,
        content_class: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        from app.modules.posts import query_service

        user_id = _owned_user_id(ctx)
        bounded_cursor, bounded_limit = _bounded_page(cursor, limit)
        bounded_search = search.strip()[:200] if search else None
        with session_scope() as session:
            return query_service.list_posts(
                session,
                user_id,
                content_status=content_status,
                content_class=content_class,
                status=status,
                search=bounded_search,
                cursor=bounded_cursor,
                limit=bounded_limit,
            )

    @server.tool(
        name="blog_get_post",
        title="读取博客文章",
        description="按文章 ID 读取当前用户的一篇博客文章及正文。",
        structured_output=True,
    )
    def get_post(ctx: Context, post_id: str) -> dict[str, Any]:
        from app.modules.posts import schemas, service

        user_id = _owned_user_id(ctx)
        parsed_id = _uuid_or_error(post_id, "post_id")
        with session_scope() as session:
            post = service.get_post(session, user_id, parsed_id)
            data = schemas.post_detail_out(session, post).model_dump(mode="json")
            # Source URLs and capture metadata are not required for article reading.
            data.pop("source_summary", None)
            return data

    @server.tool(
        name="blog_search_posts",
        title="搜索博客文章",
        description="在当前用户的博客标题和正文中搜索，返回有界命中摘要。",
        structured_output=True,
    )
    def search_posts(ctx: Context, query: str, limit: int = 30, cursor: int = 0) -> dict[str, Any]:
        from app.modules.posts import query_service

        user_id = _owned_user_id(ctx)
        normalized = query.strip()[:200]
        if not normalized:
            raise ValueError("query is required")
        bounded_cursor, bounded_limit = _bounded_page(cursor, limit)
        with session_scope() as session:
            return query_service.search_posts(
                session,
                user_id,
                normalized,
                cursor=bounded_cursor,
                limit=bounded_limit,
            )

    @server.tool(
        name="blog_timeline",
        title="查看博客时间轴",
        description="按发生时间或创建时间倒序返回当前用户的博客时间轴。",
        structured_output=True,
    )
    def timeline(
        ctx: Context,
        year: int | None = None,
        month: int | None = None,
        limit: int = 30,
        cursor: int = 0,
    ) -> dict[str, Any]:
        from app.modules.posts import query_service

        user_id = _owned_user_id(ctx)
        if year is not None and not 1970 <= year <= 2200:
            raise ValueError("year must be between 1970 and 2200")
        if month is not None and not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        if month is not None and year is None:
            raise ValueError("month requires year")
        bounded_cursor, bounded_limit = _bounded_page(cursor, limit)
        with session_scope() as session:
            return query_service.timeline_posts(
                session,
                user_id,
                year=year,
                month=month,
                cursor=bounded_cursor,
                limit=bounded_limit,
            )

    def _list_taxonomy(ctx: Context, kind: str) -> dict[str, Any]:
        from app.modules.posts import taxonomy_service

        user_id = _owned_user_id(ctx)
        with session_scope() as session:
            items = taxonomy_service.list_items(session, user_id, kind, enabled=True)
        return {"kind": kind, "total": len(items), "items": items[:500]}

    @server.tool(
        name="blog_list_categories",
        title="列出博客分类",
        description="列出当前用户启用的博客分类及使用次数。",
        structured_output=True,
    )
    def list_categories(ctx: Context) -> dict[str, Any]:
        return _list_taxonomy(ctx, "category")

    @server.tool(
        name="blog_list_tags",
        title="列出博客标签",
        description="列出当前用户启用的博客标签及使用次数。",
        structured_output=True,
    )
    def list_tags(ctx: Context) -> dict[str, Any]:
        return _list_taxonomy(ctx, "tag")

    return server


def build_blog_mcp_asgi(server: MCPServer) -> ASGIApp:
    settings = get_settings()
    parsed = urlsplit(settings.app_base_url)
    public_host = parsed.netloc
    public_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            value
            for value in (public_host, "testserver", "backend:8000", "localhost:*", "127.0.0.1:*")
            if value
        ],
        allowed_origins=[value for value in (public_origin,) if value],
    )
    protocol_app = server.streamable_http_app(
        streamable_http_path=MCP_PROTOCOL_PATH,
        json_response=True,
        stateless_http=True,
        max_request_body_size=1_048_576,
        transport_security=transport_security,
    )
    return BlogMcpBearerAuthMiddleware(protocol_app)
