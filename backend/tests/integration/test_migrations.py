"""Migration integrity against a real PostgreSQL database."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

pytestmark = [pytest.mark.integration]


def test_head_has_expected_foundation_tables(db_session) -> None:
    insp = inspect(db_session.get_bind())
    tables = set(insp.get_table_names())
    for expected in [
        "users",
        "refresh_sessions",
        "categories",
        "tags",
        "outbox_events",
        "consumer_receipts",
        "idempotency_records",
        "async_jobs",
        "async_job_events",
        "activity_logs",
    ]:
        assert expected in tables, f"missing table {expected}"


def test_citext_and_pgtrgm_extensions_present(db_session) -> None:
    rows = db_session.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    assert "citext" in rows
    assert "pg_trgm" in rows


def test_no_model_drift_against_head() -> None:
    """`alembic check` must report no pending autogenerate operations."""
    import io
    from contextlib import redirect_stdout

    from alembic import command
    from alembic.config import Config
    from alembic.util.exc import CommandError
    from app.core.config import get_settings

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            command.check(cfg)
    except CommandError as exc:  # pragma: no cover - fails loudly on drift
        pytest.fail(f"Model drift detected: {exc}")


def test_email_is_case_insensitive_unique(db_session, make_user) -> None:
    import uuid

    from app.models.foundation import User
    from app.modules.auth.service import hash_password
    from sqlalchemy.exc import IntegrityError

    email = f"Mixed-{uuid.uuid4().hex[:6]}@Example.com"
    make_user(email=email)
    with pytest.raises(IntegrityError):
        db_session.add(
            User(
                email=email.lower(),
                password_hash=hash_password("another password value"),
                display_name="dup",
                notification_preferences={},
            )
        )
        db_session.flush()
