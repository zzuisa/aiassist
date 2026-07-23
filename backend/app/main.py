"""FastAPI application factory for the modular monolith."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import ensure_dev_signing_key, get_settings
from app.core.errors import register_exception_handlers
from app.core.observability import TraceContextMiddleware, configure_logging
from app.db.session import get_db
from app.modules.auth.router import router as auth_router
from app.modules.captures.router import router as captures_router
from app.modules.habits.router import router as habits_router
from app.modules.jobs.router import router as jobs_router
from app.modules.notifications.router import router as notifications_router
from app.modules.tasks.calendar_router import router as calendar_router
from app.modules.tasks.router import router as tasks_router
from app.modules.tasks.today import router as today_router
from app.modules.uploads.router import router as uploads_router
from app.modules.voice.router import router as voice_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    ensure_dev_signing_key()
    settings.validate_startup()

    app = FastAPI(title="AI Assist Personal Life OS API", version="1.0.0")
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
    app.include_router(habits_router, prefix=API_PREFIX)
    app.include_router(today_router, prefix=API_PREFIX)
    app.include_router(notifications_router, prefix=API_PREFIX)
    app.include_router(uploads_router, prefix=API_PREFIX)
    app.include_router(voice_router, prefix=API_PREFIX)
    app.include_router(captures_router, prefix=API_PREFIX)

    return app


app = create_app()
