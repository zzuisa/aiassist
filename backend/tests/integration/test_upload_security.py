"""Upload security: size, magic bytes, MIME mismatch, pixel bomb, ownership."""

from __future__ import annotations

import io

import pytest
from app.core.errors import ValidationError
from app.db.session import session_scope
from app.modules.captures import upload_service
from app.modules.uploads import service as upload_svc
from PIL import Image

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    from app.core.config import reload_settings
    from app.services.storage.providers.local import reset_storage

    reload_settings()
    reset_storage()
    yield
    reset_storage()


def _png(size=(32, 32)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


def test_declared_size_over_limit_rejected(make_user):
    user = make_user()
    with session_scope() as s, pytest.raises(ValidationError) as exc:
        upload_svc.create_session(
            s,
            user.id,
            purpose="capture",
            filename="big.jpg",
            media_type="image/jpeg",
            byte_size=999_999_999,
        )
    assert exc.value.status == 413


def test_unsupported_image_type_rejected(make_user):
    user = make_user()
    with session_scope() as s, pytest.raises(ValidationError) as exc:
        upload_svc.create_session(
            s,
            user.id,
            purpose="capture",
            filename="x.gif",
            media_type="image/gif",
            byte_size=100,
        )
    assert exc.value.status == 415


def test_magic_bytes_mismatch_rejected():
    # PNG bytes declared as JPEG must fail content sniffing.
    with pytest.raises(ValidationError):
        upload_service.validate_image(_png(), "image/jpeg")


def test_corrupt_image_rejected():
    with pytest.raises(ValidationError):
        upload_service.validate_image(b"\xff\xd8\xff not-a-real-jpeg", "image/jpeg")


def test_pixel_bomb_rejected(monkeypatch):
    monkeypatch.setenv("UPLOAD_IMAGE_MAX_PIXELS", "1024")
    from app.core.config import reload_settings

    reload_settings()
    with pytest.raises(ValidationError):
        upload_service.validate_image(_png((200, 200)), "image/png")


def test_upload_ownership_enforced(make_user):
    owner = make_user()
    other = make_user()
    from app.core.errors import NotFoundError

    with session_scope() as s:
        upload = upload_svc.create_session(
            s,
            owner.id,
            purpose="capture",
            filename="k.png",
            media_type="image/png",
            byte_size=len(_png()),
        )
        uid = upload.id
    with session_scope() as s, pytest.raises(NotFoundError):
        upload_svc.get_owned(s, other.id, uid)


def test_storage_key_traversal_rejected(tmp_path):
    from app.services.storage.providers.local import LocalStorage

    storage = LocalStorage(str(tmp_path / "assets"))
    with pytest.raises(ValidationError):
        storage.put_stream("../escape", io.BytesIO(b"x"), max_bytes=10)
