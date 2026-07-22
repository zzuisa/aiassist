"""Shared pytest fixtures.

Integration tests run against a REAL PostgreSQL database (never SQLite) so that
citext, JSONB, constraints, ``FOR UPDATE SKIP LOCKED`` and concurrency behave as
in production. Point ``TEST_DATABASE_URL`` at a disposable database; the schema
is created once per session by running Alembic to head.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest

# Configure environment BEFORE importing app modules that read settings.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SIGNING_KEY", "test-signing-key-not-secret")

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aiassist:testpass@localhost:55432/aiassist_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def _database_available() -> bool:
    import psycopg

    try:
        dsn = TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        conn = psycopg.connect(dsn, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _database_available(),
    reason="TEST_DATABASE_URL PostgreSQL is not reachable",
)


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations() -> None:
    if not _database_available():
        pytest.skip("No test database available", allow_module_level=False)
        return
    from alembic import command
    from alembic.config import Config
    from app.db.session import reset_engine

    reset_engine()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session() -> Generator:
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clean_tables(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Truncate business tables between DB-touching tests for isolation."""
    yield
    if not _database_available():
        return
    from app.db.session import get_session_factory
    from sqlalchemy import text

    session = get_session_factory()()
    try:
        session.execute(
            text(
                "TRUNCATE users, refresh_sessions, categories, tags, outbox_events, "
                "consumer_receipts, idempotency_records, async_jobs, async_job_events, "
                "activity_logs RESTART IDENTITY CASCADE"
            )
        )
        session.commit()
    finally:
        session.close()


@pytest.fixture
def make_user():
    """Factory creating a persisted user with an Argon2id password hash."""
    from app.db.session import session_scope
    from app.models.foundation import User
    from app.modules.auth.service import hash_password

    created: list[uuid.UUID] = []

    def _make(email: str | None = None, password: str = "correct horse battery staple") -> User:
        with session_scope() as s:
            user = User(
                email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
                password_hash=hash_password(password),
                display_name="Test User",
                notification_preferences={
                    "in_app_enabled": True,
                    "email_enabled": False,
                    "critical_email_enabled": True,
                    "quiet_hours_start": None,
                    "quiet_hours_end": None,
                },
            )
            s.add(user)
            s.flush()
            uid = user.id
            created.append(uid)
            s.expunge(user)
            return user

    return _make


@pytest.fixture
def client():
    """FastAPI TestClient against the real test database."""
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as c:
        yield c
