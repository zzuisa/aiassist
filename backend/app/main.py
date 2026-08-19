"""FastAPI application factory for the modular monolith."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import ensure_dev_signing_key, get_settings
from app.core.errors import register_exception_handlers
from app.core.observability import TraceContextMiddleware, configure_logging
from app.db.session import get_db
from app.modules.agent.router import router as agent_router
from app.modules.ai_config.router import router as ai_config_router
from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.blog_mcp.server import (
    MCP_MOUNT_PATH,
    build_blog_mcp_asgi,
    build_blog_mcp_server,
)
from app.modules.captures.router import router as captures_router
from app.modules.habits.router import router as habits_router
from app.modules.jobs.router import router as jobs_router
from app.modules.notifications.router import router as notifications_router
from app.modules.posts.ai_router import ai_router as blog_ai_router
from app.modules.posts.ai_router import optimize_router as blog_optimize_router
from app.modules.posts.capture_router import captures_router as blog_captures_router
from app.modules.posts.capture_router import sources_router as blog_sources_router
from app.modules.posts.query_router import query_router as blog_query_router
from app.modules.posts.router import private_router as posts_router
from app.modules.posts.router import public_router as public_router
from app.modules.posts.settings_router import router as blog_settings_router
from app.modules.posts.skill_router import skill_router as blog_skill_router
from app.modules.posts.taxonomy_router import router as blog_taxonomy_router
from app.modules.search.router import router as search_router
from app.modules.settings.router import router as settings_router
from app.modules.tasks.calendar_router import router as calendar_router
from app.modules.tasks.note_router import router as task_note_router
from app.modules.tasks.plan_router import router as task_plan_router
from app.modules.tasks.router import router as tasks_router
from app.modules.tasks.today import router as today_router
from app.modules.uploads.router import router as uploads_router
from app.modules.voice.router import router as voice_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, service="backend")
    ensure_dev_signing_key()
    settings.validate_startup()

    blog_mcp_server = build_blog_mcp_server()
    blog_mcp_app = build_blog_mcp_asgi(blog_mcp_server)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with blog_mcp_server.session_manager.run():
            yield

    app = FastAPI(
        title="AI Assist Personal Life OS API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(TraceContextMiddleware)
    register_exception_handlers(app)

    # --- Health endpoints (unauthenticated liveness/readiness) ---
    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def health_ready(db: Session = Depends(get_db)) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}

    @app.get("/health/dependencies")
    def health_dependencies(
        _: object = Depends(get_current_user),
    ) -> dict[str, str]:
        s = get_settings()
        return {
            "mail": s.mail_status(),
            "llm": s.llm_status(),
            "speech": s.speech_status(),
            "storage": s.storage_status(),
        }

    # --- Business routers ---
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(jobs_router, prefix=API_PREFIX)
    app.include_router(tasks_router, prefix=API_PREFIX)
    app.include_router(calendar_router, prefix=API_PREFIX)
    app.include_router(task_note_router, prefix=API_PREFIX)
    app.include_router(task_plan_router, prefix=API_PREFIX)
    app.include_router(habits_router, prefix=API_PREFIX)
    app.include_router(today_router, prefix=API_PREFIX)
    app.include_router(notifications_router, prefix=API_PREFIX)
    app.include_router(uploads_router, prefix=API_PREFIX)
    app.include_router(voice_router, prefix=API_PREFIX)
    app.include_router(captures_router, prefix=API_PREFIX)
    app.include_router(search_router, prefix=API_PREFIX)
    app.include_router(posts_router, prefix=API_PREFIX)
    app.include_router(public_router, prefix=API_PREFIX)
    app.include_router(blog_captures_router, prefix=API_PREFIX)
    app.include_router(blog_sources_router, prefix=API_PREFIX)
    app.include_router(blog_skill_router, prefix=API_PREFIX)
    app.include_router(blog_taxonomy_router, prefix=API_PREFIX)
    app.include_router(blog_ai_router, prefix=API_PREFIX)
    app.include_router(blog_optimize_router, prefix=API_PREFIX)
    app.include_router(blog_query_router, prefix=API_PREFIX)
    app.include_router(blog_settings_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(ai_config_router, prefix=API_PREFIX)
    app.include_router(assistant_router, prefix=API_PREFIX)
    app.include_router(settings_router, prefix=API_PREFIX)
    app.mount(MCP_MOUNT_PATH, blog_mcp_app, name="blog-mcp")

    return app


app = create_app()
