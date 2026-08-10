"""Idempotent migration of Radio transcript history into blog posts."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.blog import PostSource
from app.models.posts import Post, PostRevision
from app.modules.posts import capture_service
from app.modules.posts import service as post_service
from app.services.radio.client import RadioClient


@dataclass
class MigrationItem:
    record_id: str
    outcome: str
    reason: str | None = None
    post_id: str | None = None


@dataclass
class MigrationReport:
    radio_total: int = 0
    fetched: int = 0
    eligible: int = 0
    created: int = 0
    updated: int = 0
    existing: int = 0
    would_create: int = 0
    would_update: int = 0
    skipped: int = 0
    missing_body: int = 0
    failed: int = 0
    dry_run: bool = False
    force: bool = False
    balanced: bool = True
    items: list[MigrationItem] = field(default_factory=list)

    def finalize(self) -> None:
        accounted = (
            self.created
            + self.updated
            + self.existing
            + self.would_create
            + self.would_update
            + self.skipped
            + self.failed
        )
        self.balanced = self.fetched == accounted

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [asdict(item) for item in self.items]
        return data


def _record_text(record: dict[str, Any]) -> str:
    value = record.get("text")
    return value.strip() if isinstance(value, str) else ""


def _record_title(record: dict[str, Any], record_id: str) -> str:
    for value in (record.get("title"), record.get("bvid")):
        if isinstance(value, str) and value.strip():
            return value.strip()[:240]
    return f"B站转写记录-{record_id}"[:240]


def _record_time(record: dict[str, Any]) -> datetime:
    created_at = record.get("created_at")
    try:
        return datetime.fromtimestamp(float(created_at), tz=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def find_migrated_source(session: Session, user_id: uuid.UUID, record_id: str) -> PostSource | None:
    return session.scalar(
        select(PostSource).where(
            PostSource.user_id == user_id,
            PostSource.external_system == "radio",
            PostSource.external_record_id == record_id,
        )
    )


def migrate_record(
    session: Session,
    *,
    user_id: uuid.UUID,
    record: dict[str, Any],
    force: bool,
) -> MigrationItem:
    raw_id = record.get("id")
    record_id = raw_id.strip() if isinstance(raw_id, str) else ""
    if not record_id:
        return MigrationItem("<missing>", "skipped", "missing_record_id")
    text = _record_text(record)
    if not text:
        return MigrationItem(record_id, "skipped", "missing_body")

    existing = find_migrated_source(session, user_id, record_id)
    if existing is not None and not force:
        return MigrationItem(
            record_id,
            "existing",
            "external_record_id_exists",
            str(existing.post_id) if existing.post_id else None,
        )

    title = _record_title(record, record_id)
    source_url = record.get("source_url")
    source_url = source_url.strip() if isinstance(source_url, str) else ""
    timestamp = _record_time(record)
    metadata = {
        "url_type": "bilibili",
        "migration_source": "radio",
        "bvid": record.get("bvid"),
        "selected_version": record.get("selected_version") or "original",
    }

    if existing is not None:
        post = session.get(Post, existing.post_id) if existing.post_id else None
        if post is None:
            return MigrationItem(record_id, "failed", "existing_post_missing")
        post.title = title
        post.markdown = text
        post.content_status = "triage"
        revision = post_service.new_revision(
            session,
            post,
            text,
            "import",
            post.current_revision_id,
            change_summary=f"强制同步 Radio 转写记录 {record_id}",
        )
        revision.applied_at = datetime.now(UTC)
        post.current_revision_id = revision.id
        post.version += 1
        existing.original_url = source_url or existing.original_url
        existing.original_title = title
        existing.original_text = text
        existing.normalized_markdown = text
        existing.external_task_id = str(record.get("task_id") or "") or None
        existing.metadata_json = metadata
        existing.status = "completed"
        existing.error_code = None
        existing.error_message = None
        return MigrationItem(record_id, "updated", post_id=str(post.id))

    post = capture_service._create_post(
        session,
        user_id,
        title=title,
        markdown=text,
        content_status="triage",
        content_class="media",
        language="zh-CN",
        content_type_id=None,
    )
    source = capture_service._add_source(
        session,
        user_id,
        post,
        source_type="url" if source_url else "file",
        status="completed",
        detected_format="plain",
        original_url=source_url or None,
        source_site="Bilibili",
        original_title=title,
        original_text=text,
        normalized_markdown=text,
        metadata_json=metadata,
        external_system="radio",
        external_record_id=record_id,
        external_task_id=str(record.get("task_id") or "") or None,
        extracted_at=timestamp,
    )
    # Radio has no updated_at field; use its only timestamp for both values.
    post.created_at = timestamp
    post.updated_at = timestamp
    source.created_at = timestamp
    source.updated_at = timestamp
    source.captured_at = timestamp
    created_revision = session.get(PostRevision, post.current_revision_id)
    if created_revision is not None:
        created_revision.created_at = timestamp
    return MigrationItem(record_id, "created", post_id=str(post.id))


class RadioHistoryMigrator:
    def __init__(
        self,
        *,
        client: RadioClient,
        session_factory: sessionmaker[Session],
        user_id: uuid.UUID,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._user_id = user_id

    def _fetch_records(
        self,
        *,
        limit: int,
        start_id: str | None,
        max_records: int | None,
    ) -> tuple[int, list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        offset = 0
        total = 0
        start_found = start_id is None
        seen_offsets: set[int] = set()
        while True:
            if offset in seen_offsets:
                raise RuntimeError("Radio pagination repeated an offset")
            seen_offsets.add(offset)
            page = self._client.list_transcripts(limit=limit, offset=offset)
            total = page.total
            for record in page.items:
                if not start_found:
                    start_found = record.get("id") == start_id
                    if not start_found:
                        continue
                records.append(record)
                if max_records is not None and len(records) >= max_records:
                    return total, records
            if not page.has_more:
                break
            if page.next_offset is None or page.next_offset <= offset:
                raise RuntimeError("Radio pagination did not advance")
            offset = page.next_offset
        if start_id is not None and not start_found:
            raise RuntimeError(f"start record not found: {start_id}")
        return total, records

    def run(
        self,
        *,
        limit: int = 100,
        dry_run: bool = False,
        force: bool = False,
        start_id: str | None = None,
        max_records: int | None = None,
    ) -> MigrationReport:
        total, records = self._fetch_records(
            limit=max(1, min(limit, 200)),
            start_id=start_id,
            max_records=max_records,
        )
        report = MigrationReport(
            radio_total=total,
            fetched=len(records),
            dry_run=dry_run,
            force=force,
        )
        for record in records:
            record_id = str(record.get("id") or "<missing>")
            text = _record_text(record)
            if text:
                report.eligible += 1
            if dry_run:
                with self._session_factory() as session:
                    if not text:
                        item = MigrationItem(record_id, "skipped", "missing_body")
                    elif find_migrated_source(session, self._user_id, record_id) is not None:
                        item = MigrationItem(
                            record_id,
                            "would_update" if force else "existing",
                            "dry_run_force" if force else "external_record_id_exists",
                        )
                    else:
                        item = MigrationItem(record_id, "would_create", "dry_run")
            else:
                session = self._session_factory()
                try:
                    item = migrate_record(
                        session,
                        user_id=self._user_id,
                        record=record,
                        force=force,
                    )
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    existing = find_migrated_source(session, self._user_id, record_id)
                    if existing is not None:
                        item = MigrationItem(
                            record_id,
                            "existing",
                            "concurrent_external_record_id_exists",
                            str(existing.post_id) if existing.post_id else None,
                        )
                    else:
                        item = MigrationItem(record_id, "failed", "integrity_error")
                except Exception as exc:
                    session.rollback()
                    item = MigrationItem(
                        record_id,
                        "failed",
                        f"{type(exc).__name__}: {str(exc)[:200]}",
                    )
                finally:
                    session.close()
            report.items.append(item)
            if item.outcome == "created":
                report.created += 1
            elif item.outcome == "updated":
                report.updated += 1
            elif item.outcome == "existing":
                report.existing += 1
            elif item.outcome == "would_create":
                report.would_create += 1
            elif item.outcome == "would_update":
                report.would_update += 1
            elif item.outcome == "skipped":
                report.skipped += 1
                if item.reason == "missing_body":
                    report.missing_body += 1
            else:
                report.failed += 1
        report.finalize()
        return report
