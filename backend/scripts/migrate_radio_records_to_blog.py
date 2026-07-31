#!/usr/bin/env python3
"""Migrate all paginated Radio transcripts into the AI Assist blog."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from app.core.config import _read_secret_file, get_settings
from app.db.session import get_session_factory
from app.models.foundation import User
from app.modules.posts.radio_migration import RadioHistoryMigrator
from app.services.radio.client import RadioClient
from sqlalchemy import select


def _resolve_user(user_id: str | None, user_email: str | None) -> uuid.UUID:
    factory = get_session_factory()
    with factory() as session:
        if user_id:
            user = session.get(User, uuid.UUID(user_id))
        elif user_email:
            user = session.scalar(select(User).where(User.email == user_email))
        else:
            users = list(session.scalars(select(User).where(User.status == "active")).all())
            if len(users) != 1:
                raise SystemExit(
                    "Specify --user-id or --user-email when active user count is not one"
                )
            user = users[0]
        if user is None:
            raise SystemExit("Target user not found")
        return user.id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--password-file")
    parser.add_argument("--user-id")
    parser.add_argument("--user-email")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--start-id")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--report-file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()
    base_url = args.base_url or settings.radio_service_base_url
    password = (
        _read_secret_file(args.password_file)
        if args.password_file
        else settings.resolved_radio_service_password
    )
    if not base_url:
        raise SystemExit("Radio base URL is not configured")
    user_id = _resolve_user(args.user_id, args.user_email)
    client = RadioClient(
        base_url=base_url,
        password=password,
        connect_timeout=settings.radio_service_connect_timeout_seconds,
        read_timeout=settings.radio_service_read_timeout_seconds,
    )
    report = RadioHistoryMigrator(
        client=client,
        session_factory=get_session_factory(),
        user_id=user_id,
    ).run(
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
        start_id=args.start_id,
        max_records=args.max_records,
    )
    payload = report.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.report_file:
        Path(args.report_file).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if report.balanced and report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
