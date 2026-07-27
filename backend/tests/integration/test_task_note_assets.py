"""US2: task note text + batched image attachments with partial-failure isolation."""

from __future__ import annotations

import io
import uuid

import pytest
from app.db.session import session_scope
from app.models.tasks import Task
from app.modules.tasks import note_service
from app.modules.uploads import service as upload_service
from PIL import Image

pytestmark = [pytest.mark.integration]


def _jpeg(color=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, "JPEG")
    return buf.getvalue()


def _make_task(s, user_id) -> Task:
    t = Task(id=uuid.uuid4(), user_id=user_id, type="task", title="事件", status="todo", version=1)
    s.add(t)
    s.flush()
    return t


def _upload(s, user_id, data: bytes):
    up = upload_service.create_session(
        s, user_id, purpose="task_note_image", filename="a.jpg",
        media_type="image/jpeg", byte_size=len(data),
    )
    upload_service.store_bytes(s, up, io.BytesIO(data))
    upload_service.complete(s, user_id, up.id)
    return up


def test_save_note_text_and_reopen(make_user):
    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id)
        note_service.save_note_text(s, user.id, task.id, "买灯泡和电池")
    with session_scope() as s:
        note = note_service.get_note(s, user.id, task.id)
        assert note is not None and note.content == "买灯泡和电池"


def test_attach_images_generates_ready_preview(make_user):
    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id)
        up = _upload(s, user.id, _jpeg())
        note, results = note_service.attach_images(s, user.id, task.id, [up.id])
        assert results[0]["status"] == "attached"
        assets = note_service.list_assets(s, note.id)
        assert len(assets) == 1
        a = assets[0]
        assert a.processing_status == "ready"
        assert a.preview_storage_key is not None and a.position == 0
        assert a.width == 64 and a.height == 48


def test_multi_batch_append_keeps_order_and_no_replace(make_user):
    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id)
        up1 = _upload(s, user.id, _jpeg((10, 200, 10)))
        note, _ = note_service.attach_images(s, user.id, task.id, [up1.id])
        nid = note.id
    with session_scope() as s:
        up2 = _upload(s, user.id, _jpeg((10, 10, 200)))
        up3 = _upload(s, user.id, _jpeg((200, 200, 10)))
        note_service.attach_images(s, user.id, task.id, [up2.id, up3.id])
    with session_scope() as s:
        assets = note_service.list_assets(s, nid)
        assert [a.position for a in assets] == [0, 1, 2]  # appended, not replaced


def test_partial_failure_isolated(make_user):
    """A duplicate/invalid item fails alone; the good one still attaches."""
    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id)
        up_good = _upload(s, user.id, _jpeg())
        note, _ = note_service.attach_images(s, user.id, task.id, [up_good.id])
        # Re-attaching the same upload must fail, the fresh one must succeed.
        up_new = _upload(s, user.id, _jpeg((30, 30, 30)))
        _, results = note_service.attach_images(s, user.id, task.id, [up_good.id, up_new.id])
        by = {r["status"] for r in results}
        assert "failed" in by and "attached" in by
        assert len(note_service.list_assets(s, note.id)) == 2  # good + new only


def test_empty_note_without_images_rejected(make_user):
    from app.core.errors import ValidationError

    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id)
        with pytest.raises(ValidationError):
            note_service.save_note_text(s, user.id, task.id, "   ")


def test_foreign_task_note_not_found(make_user):
    from app.core.errors import NotFoundError

    owner = make_user()
    other = make_user()
    with session_scope() as s:
        task = _make_task(s, owner.id)
        with pytest.raises(NotFoundError):
            note_service.get_note(s, other.id, task.id)
