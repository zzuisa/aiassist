from __future__ import annotations

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


class FakePagedRadio:
    def __init__(self):
        self.records = [
            {
                "id": "stt-3",
                "task_id": "task-3",
                "source_url": "https://b23.tv/three",
                "bvid": "BV3",
                "title": "第三条",
                "text": "",
                "selected_version": "original",
                "created_at": 300.0,
            },
            {
                "id": "stt-2",
                "task_id": "task-2",
                "source_url": "https://b23.tv/two",
                "bvid": "BV2",
                "title": "第二条",
                "text": "正文二",
                "selected_version": "original",
                "created_at": 200.0,
            },
            {
                "id": "stt-1",
                "task_id": "task-1",
                "source_url": "https://b23.tv/one",
                "bvid": "BV1",
                "title": "第一条",
                "text": "正文一",
                "selected_version": "original",
                "created_at": 100.0,
            },
        ]

    def list_transcripts(self, *, limit, offset):
        from app.services.radio.client import RadioTranscriptPage

        items = self.records[offset : offset + limit]
        next_offset = offset + len(items)
        has_more = next_offset < len(self.records)
        return RadioTranscriptPage(
            items=items,
            total=len(self.records),
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset if has_more else None,
        )


@requires_db
def test_radio_history_migration_is_paginated_dry_run_and_idempotent(make_user):
    from app.db.session import get_session_factory
    from app.modules.posts.radio_migration import RadioHistoryMigrator

    user = make_user()
    migrator = RadioHistoryMigrator(
        client=FakePagedRadio(),
        session_factory=get_session_factory(),
        user_id=user.id,
    )

    dry = migrator.run(limit=1, dry_run=True)
    assert dry.radio_total == 3
    assert dry.fetched == 3
    assert dry.would_create == 2
    assert dry.missing_body == 1
    assert dry.balanced is True

    first = migrator.run(limit=1)
    assert first.created == 2
    assert first.skipped == 1
    assert first.failed == 0
    assert first.balanced is True

    repeated = migrator.run(limit=2)
    assert repeated.created == 0
    assert repeated.existing == 2
    assert repeated.skipped == 1
    assert repeated.balanced is True

    forced = migrator.run(limit=2, force=True)
    assert forced.updated == 2
    assert forced.skipped == 1
    assert forced.balanced is True
