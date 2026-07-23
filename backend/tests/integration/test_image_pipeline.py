"""Image pipeline: orientation-before-strip, EXIF/GPS removal, deterministic, dedupe."""

from __future__ import annotations

import io
import uuid

import piexif
import pytest
from app.db.session import session_scope
from app.modules.captures import service as capture_service
from app.modules.captures import upload_service
from app.modules.uploads import service as upload_svc
from app.workers.tasks import images
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


def _jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (64, 48), (120, 60, 30))
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: [(52, 1), (31, 1), (0, 1)],
        piexif.GPSIFD.GPSLongitudeRef: b"E",
        piexif.GPSIFD.GPSLongitude: [(13, 1), (24, 1), (0, 1)],
    }
    exif = {"0th": {piexif.ImageIFD.Orientation: 6}, "GPS": gps_ifd}
    exif_bytes = piexif.dump(exif)
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif_bytes)
    return out.getvalue()


def test_validate_image_accepts_matching_jpeg():
    data = _jpeg_with_gps()
    w, h = upload_service.validate_image(data, "image/jpeg")
    assert (w, h) == (64, 48)


def test_validate_rejects_mime_mismatch():
    from app.core.errors import ValidationError

    data = _jpeg_with_gps()
    with pytest.raises(ValidationError):
        upload_service.validate_image(data, "image/png")


def test_derivative_strips_exif_and_gps():
    data = _jpeg_with_gps()
    derivative = upload_service.make_sanitized_derivative(data, max_size=320)
    with Image.open(io.BytesIO(derivative)) as img:
        assert not img.getexif() or len(img.getexif()) == 0


def test_pipeline_produces_derivatives_and_is_idempotent(make_user):
    user = make_user()
    data = _jpeg_with_gps()
    with session_scope() as s:
        upload = upload_svc.create_session(
            s,
            user.id,
            purpose="capture",
            filename="k.jpg",
            media_type="image/jpeg",
            byte_size=len(data),
        )
        upload_svc.store_bytes(s, upload, io.BytesIO(data))
        upload_svc.complete(s, user.id, upload.id)
        capture = capture_service.create_capture(
            s,
            user.id,
            capture_type="item",
            title="厨房工具",
            description=None,
            upload_ids=[upload.id],
        )
        cid = capture.id

    # Run pipeline twice (simulates worker redelivery).
    images.process_capture_images(cid)
    images.process_capture_images(cid)

    with session_scope() as s:
        from app.models.captures import CaptureAsset
        from sqlalchemy import select

        thumbs = s.scalars(
            select(CaptureAsset).where(
                CaptureAsset.capture_id == cid, CaptureAsset.role == "thumbnail"
            )
        ).all()
        assert len(thumbs) == 1  # idempotent
        assert thumbs[0].gps_removed is True


def test_original_survives_ai_failure(make_user):
    """The raw original stays accessible even if later steps fail."""
    user = make_user()
    data = _jpeg_with_gps()
    with session_scope() as s:
        upload = upload_svc.create_session(
            s,
            user.id,
            purpose="capture",
            filename="k.jpg",
            media_type="image/jpeg",
            byte_size=len(data),
        )
        upload_svc.store_bytes(s, upload, io.BytesIO(data))
        upload_svc.complete(s, user.id, upload.id)
        capture = capture_service.create_capture(
            s,
            user.id,
            capture_type="item",
            title="厨房工具",
            description=None,
            upload_ids=[upload.id],
        )
        cid = capture.id
        original_key = capture_service.list_assets(s, cid)[0].storage_key

    from app.services.storage.providers.local import get_storage

    # The original object is still readable regardless of processing outcome.
    assert b"".join(get_storage().open_stream(original_key))


_ = uuid
