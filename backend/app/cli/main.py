"""Operational CLI: migrations, admin creation, health checks, outbox publisher.

Usage:
  python -m app.cli.main migrate
  python -m app.cli.main create-admin --email owner@example.com
  python -m app.cli.main healthcheck --url http://localhost:8000/health/live
  python -m app.cli.main outbox-publisher
"""

from __future__ import annotations

import argparse
import getpass
import sys


def cmd_migrate() -> int:
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)
    command.upgrade(cfg, "head")
    print("Migrations applied to head.")
    return 0


def cmd_create_admin(email: str) -> int:
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models.foundation import User
    from app.modules.auth.service import hash_password

    password = getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12:
        print("Password too short.", file=sys.stderr)
        return 2
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 2

    with session_scope() as s:
        existing = s.scalar(select(User).where(User.email == email))
        if existing is not None:
            print("An account with that email already exists.", file=sys.stderr)
            return 1
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=email.split("@")[0],
            notification_preferences={
                "in_app_enabled": True,
                "email_enabled": False,
                "critical_email_enabled": True,
                "quiet_hours_start": None,
                "quiet_hours_end": None,
            },
        )
        s.add(user)
    print(f"Created admin account: {email}")
    return 0


def cmd_healthcheck(url: str) -> int:
    import httpx

    try:
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code == 200:
            return 0
        print(f"Health check failed: {resp.status_code}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Health check error: {exc}", file=sys.stderr)
        return 1


def cmd_outbox_publisher() -> int:
    from app.services.outbox.publisher import run_publisher

    run_publisher()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiassist")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    p_admin = sub.add_parser("create-admin")
    p_admin.add_argument("--email", required=True)
    p_health = sub.add_parser("healthcheck")
    p_health.add_argument("--url", default="http://localhost:8000/health/live")
    sub.add_parser("outbox-publisher")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return cmd_migrate()
    if args.command == "create-admin":
        return cmd_create_admin(args.email)
    if args.command == "healthcheck":
        return cmd_healthcheck(args.url)
    if args.command == "outbox-publisher":
        return cmd_outbox_publisher()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
